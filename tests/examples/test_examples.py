"""The files in examples/ are what the guide shows, so each one is run for real: served the way `python file.py` would
serve it, then driven through a run, and what the dashboard would show is checked."""
import json
import runpy
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import uvicorn
from fastapi.testclient import TestClient

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.main import create_app

EXAMPLES = Path(__file__).parents[2] / "examples"
COLUMNS = ["chat_id", "turn_no", "type", "question", "expected_sql"]
JUDGE = lambda question, expected, generated, checks: {"sql_marks": 8}   # noqa: E731
SCHEMA_ORDERS = "orders(id, customer_id, amount, status, created_at)"


@pytest.fixture
def serve_example(tmp_path, monkeypatch):
    """Run an example file as a script, but catch the app it would serve instead of starting a server."""
    monkeypatch.chdir(tmp_path)
    caught = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **options: caught.update(app=app))
    monkeypatch.setattr("nl2sql_evalkit.launcher.configure_logging", lambda config: None)
    monkeypatch.setattr("nl2sql_evalkit.launcher.llm_client.load_litellm", lambda: None)
    monkeypatch.setattr("nl2sql_evalkit.launcher.threading.Timer", lambda *args, **options: SimpleNamespace(start=lambda: None))

    def serve(name, fake_judge=True):
        runpy.run_path(str(EXAMPLES / name), run_name="__main__")
        app = caught["app"]
        if fake_judge:                                  # no model is called: an example's own judge_fn is kept
            app.state.manager._judge_fn = app.state.manager._judge_fn or JUDGE
            app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
        return app

    yield serve
    if "app" in caught:
        caught["app"].state.store.close()


@pytest.fixture
def served_function(tmp_path):
    """An app serving a function that is defined in an example file."""
    apps = []

    def build(fn, config_options=None, **options):
        config = Config(data_dir=tmp_path / f"store{len(apps)}", require_login=False, **(config_options or {}))
        app = create_app(config, fn=fn, judge_fn=options.pop("judge_fn", JUDGE), **options)
        app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
        apps.append(app)
        return app

    yield build
    for app in apps:
        app.state.store.close()


def evaluate(app, questions, case_type="answer", extra=None) -> list[dict]:
    """Run (chat_id, turn_no, question, expected) rows and return the saved result rows."""
    frame = pd.DataFrame([(chat, turn, case_type, question, expected) for chat, turn, question, expected in questions], columns=COLUMNS)
    for name, values in (extra or {}).items():
        frame[name] = values
    run = app.state.manager.start("v1", frame, "example")
    deadline = time.time() + 30
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert run.status == "completed", run.error
    return app.state.store.get("v1")["rows"]


def steps_of(row: dict) -> list[str]:
    return list(row["node_timings"])


# ---- function_shapes.py -----------------------------------------------------------------------------------------

def test_function_shapes_example_is_served(serve_example):
    app = serve_example("function_shapes.py")
    rows = evaluate(app, [("c1", 1, "Total sales per region", "SELECT 1"), ("c1", 2, "And only the large ones?", "SELECT 1")])
    assert "-- follows up on: Total sales per region" in rows[1]["generated_answer"]
    assert rows[1]["sql_checks"]["syntax_ok"] and rows[1]["sql_checks"]["read_only"]


def test_each_of_the_shapes_works(served_function):
    shapes = runpy.run_path(str(EXAMPLES / "function_shapes.py"))
    only = evaluate(served_function(shapes["answer_only"]), [("c1", 1, "Sales?", "SELECT 1")])
    assert only[0]["status"] == "ok" and only[0]["sql_checks"]["tables_used"] == ["orders", "customers"]

    history = evaluate(served_function(shapes["answer_with_history"]), [("c1", 1, "Sales?", "x"), ("c1", 2, "Large ones?", "x")])
    assert "follows up" not in history[0]["generated_answer"] and "follows up on: Sales?" in history[1]["generated_answer"]

    shapes["SESSIONS"].clear()
    session = evaluate(served_function(shapes["answer_in_session"]), [("c1", 1, "a?", "x"), ("c1", 2, "b?", "x"), ("c2", 1, "c?", "x")])
    assert [r["generated_answer"].splitlines()[0] for r in session] == ["-- message 1 of this chat", "-- message 2 of this chat", "-- message 1 of this chat"]


def test_dict_async_and_renamed_parameters_are_understood(served_function):
    shapes = runpy.run_path(str(EXAMPLES / "function_shapes.py"))
    chat = [("c1", 1, "Sales?", "x"), ("c1", 2, "And large ones?", "x")]
    assert evaluate(served_function(shapes["answer_as_dict"]), chat[:1])[0]["generated_answer"].startswith("SELECT c.region")
    assert evaluate(served_function(shapes["answer_async"]), chat[:1])[0]["generated_answer"].startswith("SELECT c.region")
    renamed = served_function(shapes["answer_with_other_names"], config_options={"history_params": ["past_chats"]})
    assert evaluate(renamed, chat)[1]["generated_answer"].startswith("-- I can see 1 earlier turns.")
    openai = served_function(shapes["answer_with_openai_history"], config_options={"history_format": "openai"})
    assert [r["generated_answer"].splitlines()[0] for r in evaluate(openai, chat)][1] == "-- earlier you asked: Sales?"


# ---- steps_two_ways.py ------------------------------------------------------------------------------------------

def test_the_two_step_styles_record_the_same_steps_and_the_same_sql(served_function):
    module = runpy.run_path(str(EXAMPLES / "steps_two_ways.py"))
    question = [("c1", 1, "How many orders are there?", "SELECT COUNT(*) FROM orders")]
    blocks = evaluate(served_function(module["pipeline_with_blocks"]), question)[0]
    decorated = evaluate(served_function(module["pipeline_with_decorators"]), question)[0]

    assert steps_of(blocks) == steps_of(decorated) == ["schema_lookup", "llm"]
    assert blocks["generated_answer"] == decorated["generated_answer"] == "SELECT COUNT(*) FROM orders"
    # the difference between them: decorators record the inputs and outputs for you
    assert decorated["step_inputs"]["schema_lookup"] == {"question": "How many orders are there?"}
    assert decorated["step_outputs"]["schema_lookup"] == SCHEMA_ORDERS
    assert blocks["step_inputs"]["schema_lookup"] == {} and blocks["flags"]["tables_given"] == SCHEMA_ORDERS


def test_steps_two_ways_example_is_served(serve_example):
    rows = evaluate(serve_example("steps_two_ways.py"), [("c1", 1, "How many customers are there?", "SELECT COUNT(*) FROM customers")])
    assert rows[0]["generated_answer"] == "SELECT COUNT(*) FROM customers" and rows[0]["sql_marks"] == 8


# ---- text_to_sql_pipeline.py ------------------------------------------------------------------------------------

def test_text_to_sql_pipeline_records_each_stage(serve_example):
    rows = evaluate(serve_example("text_to_sql_pipeline.py"), [("c1", 1, "How many products are there?", "SELECT COUNT(*) FROM products")])
    row = rows[0]
    assert steps_of(row) == ["rewrite", "schema_lookup", "llm", "self_check"]
    assert row["generated_answer"] == "SELECT COUNT(*) FROM products" and row["flags"]["tables_given"] == "products"
    assert row["sql_checks"]["tables_used"] == ["products"]


# ---- langgraph_agent.py -----------------------------------------------------------------------------------------

def test_steps_inside_langgraph_nodes_are_recorded(serve_example):
    pytest.importorskip("langgraph")
    row = evaluate(serve_example("langgraph_agent.py"), [("c1", 1, "How many orders are there?", "SELECT COUNT(*) FROM orders")])[0]
    assert steps_of(row) == ["rewrite", "schema_lookup", "llm"]
    assert row["step_inputs"]["rewrite"] == {"question": "How many orders are there?"}
    assert row["generated_answer"] == "SELECT COUNT(*) FROM orders"


# ---- declining_assistant.py -------------------------------------------------------------------------------------

def test_an_assistant_that_declines_is_scored_on_the_decline_and_on_clear_questions(serve_example):
    app = serve_example("declining_assistant.py")
    rows = evaluate(app, [("c1", 1, "Show me the best customers", ""), ("c2", 1, "Delete all orders from 2023", "")], case_type="clarify")
    assert [r["sql_checks"]["returned_sql"] for r in rows] == [False, False] and [r["sql_marks"] for r in rows] == [8, 8]
    assert [r["flags"]["triage"] for r in rows] == ["vague", "unsafe"] and steps_of(rows[0]) == ["triage"]
    answer = evaluate(app, [("c3", 1, "Orders per status", "SELECT status, COUNT(*) FROM orders GROUP BY status")], case_type="answer")
    assert answer[0]["sql_checks"]["returned_sql"] and answer[0]["flags"]["triage"] == "clear"


# ---- custom_judge.py and custom_judge_prompt.py -----------------------------------------------------------------

def test_a_custom_judge_function_replaces_the_ai_judge(serve_example):
    app = serve_example("custom_judge.py")
    assert app.state.manager._judge_fn.__name__ == "strict_about_joins"
    same = "SELECT region, SUM(amount) FROM orders GROUP BY region"
    joined = "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region"
    rows = evaluate(app, [("c1", 1, "Sales per region?", same), ("c2", 1, "Sales per customer region?", joined)])
    assert [r["sql_marks"] for r in rows] == [10, 4]
    assert "customers.id = orders.customer_id" in rows[1]["sql_remarks"] and rows[1]["sql_suggestion"]


def test_the_other_judges_in_the_example_grade_as_described():
    judges = runpy.run_path(str(EXAMPLES / "custom_judge.py"))
    same, star, joins = judges["same_as_expected"], judges["no_select_star"], judges["strict_about_joins"]
    assert same("q", "SELECT a FROM t", "select a  from t;", {})["sql_marks"] == 10
    assert same("q", "SELECT a FROM t", "SELECT b FROM t", {})["sql_marks"] == 3
    assert star("q", "", "SELECT * FROM t", {"star": True})["sql_marks"] == 4
    assert star("q", "", "SELECT a FROM t", {"star": False})["sql_marks"] == 10
    assert joins("q", "", "SELECT 1", {"joins_match": None})["sql_marks"] == 8


def test_a_custom_rubric_gets_the_reply_format_added(serve_example):
    app = serve_example("custom_judge_prompt.py", fake_judge=False)
    prompt = app.state.manager.judge._grader_prompt
    assert "finance team" in prompt and "Respond ONLY with a JSON object" in prompt
    assert app.state.config.summary_prompt.startswith("You are reviewing one test run") and app.state.config.judge_model == "openai/gpt-4o-mini"


# ---- metrics_and_hooks.py ---------------------------------------------------------------------------------------

def test_extra_metrics_columns_and_the_completion_hook(serve_example, capsys):
    app = serve_example("metrics_and_hooks.py")
    rows = evaluate(app, [("c1", 1, "Sales?", "SELECT region, SUM(amount) FROM orders GROUP BY region")], extra={"difficulty": ["easy"]})
    assert rows[0]["word_overlap"] == 1.0 and rows[0]["length_ratio"] == 1.0 and rows[0]["difficulty"] == "easy"
    deadline = time.time() + 5
    while "SQL score" not in capsys.readouterr().out and time.time() < deadline:
        time.sleep(0.05)
    assert app.state.config.column_map == {"user_query": "question", "gold_answer": "expected_sql"}


# ---- call_existing_api.py ---------------------------------------------------------------------------------------

@pytest.fixture
def fake_bot():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            reply = json.dumps({"reply": f"echo: {body['message']}"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/chat", received
    server.shutdown()


def test_an_already_deployed_bot_is_evaluated_over_http(serve_example, monkeypatch, fake_bot):
    url, received = fake_bot
    monkeypatch.setenv("BOT_URL", url)
    app = serve_example("call_existing_api.py")
    rows = evaluate(app, [("c1", 1, "Hi?", "x"), ("c1", 2, "And?", "x")])
    assert [r["generated_answer"] for r in rows] == ["echo: Hi?", "echo: And?"]
    assert received[0]["session_id"] == received[1]["session_id"] != ""
    assert steps_of(rows[0]) == ["http_call"]


# ---- test_cases.csv ---------------------------------------------------------------------------------------------

def test_the_sample_test_case_file_imports_as_described(served_function):
    app = served_function(lambda question: "x")
    client = TestClient(app)
    sample = (EXAMPLES / "test_cases.csv").read_bytes()
    preview = client.post("/api/test-cases/import/preview", files={"file": ("test_cases.csv", sample, "text/csv")}).json()
    assert preview["counts"]["new"] == 5 and not preview["problems"]
    client.post("/api/test-cases/import", files={"file": ("test_cases.csv", sample, "text/csv")}).raise_for_status()

    cases = {c["question"]: c for c in client.get("/api/test-cases").json()}
    assert len(cases) == 5
    assert cases["Show me the best customers"]["type"] == "clarify" and cases["Delete all orders from 2023"]["type"] == "refuse"
    follow_up = cases["And only for the north region?"]
    assert (follow_up["chat_id"], follow_up["turn_no"], follow_up["expected_columns"]) == ("sales-1", 2, "region, amount")
    assert cases["Total sales per region"]["expected_tables"] == "orders, customers"
    assert cases["How many orders are still open?"]["expected_sql"].startswith("SELECT COUNT(*)")
    assert sorted(g["name"] for g in client.get("/api/groups").json()) == ["Attacks", "Orders", "Sales", "Vague"]


# ---- shared_pipeline.py, production_app.py, eval_entry.py -------------------------------------------------------

@pytest.fixture
def example_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    for name in ("shared_pipeline", "production_app"):
        sys.modules.pop(name, None)
    yield
    for name in ("shared_pipeline", "production_app"):
        sys.modules.pop(name, None)


def test_production_runs_the_same_pipeline_with_steps_doing_nothing(example_modules):
    from nl2sql_evalkit.services.evaluation.step_recorder.recorder import current_recorder

    import production_app
    reply = TestClient(production_app.app).post("/chat", json={"message": "How many customers are there?"}).json()
    assert reply == {"reply": "SELECT COUNT(*) FROM customers"}
    assert current_recorder() is None


def test_the_evaluation_entry_records_the_same_pipeline(example_modules, serve_example):
    row = evaluate(serve_example("eval_entry.py"), [("c1", 1, "How many customers are there?", "SELECT COUNT(*) FROM customers")])[0]
    assert steps_of(row) == ["schema_lookup", "llm"] and row["generated_answer"] == "SELECT COUNT(*) FROM customers"


# ---- tool_agent.py ----------------------------------------------------------------------------------------------

def test_an_agent_loop_adds_up_repeated_steps(serve_example):
    row = evaluate(serve_example("tool_agent.py"), [("c1", 1, "Total per order status", "SELECT status, SUM(amount) FROM orders GROUP BY status")])[0]
    assert steps_of(row) == ["llm", "list_tables", "describe_table"]
    assert row["flags"]["tools_used"] == "list_tables, describe_table"
    assert row["generated_answer"] == "SELECT status, SUM(amount) FROM orders GROUP BY status"


# ---- langchain_chain.py -----------------------------------------------------------------------------------------

def test_steps_in_parallel_langchain_branches_are_recorded(serve_example):
    pytest.importorskip("langchain_core")
    row = evaluate(serve_example("langchain_chain.py"), [("c1", 1, "How many orders are there?", "SELECT COUNT(*) FROM orders")])[0]
    assert steps_of(row)[0] == "rewrite" and steps_of(row)[-2:] == ["schema_lookup", "llm"]
    assert {"name_match", "column_match"} <= set(steps_of(row))
    assert row["generated_answer"] == "SELECT COUNT(*) FROM orders"


# ---- team_setup.py ----------------------------------------------------------------------------------------------

def test_the_team_setup_example_is_a_valid_configuration(serve_example):
    config = serve_example("team_setup.py").state.config
    assert config.dialect == "postgres" and config.eval_users == "alice:pw-for-alice,bob:pw-for-bob" and config.eval_secret == "change-me"
    assert (config.sql_weight, config.schema_weight, config.recommendation_tolerance, config.max_response_time) == (0.7, 0.3, 0.2, 8.0)
    assert config.generator_model == "ollama/llama3" and config.logs_dir == Path("evals/logs") and config.store_path == Path("evals/store.json")


# ---- ci_gate.py -------------------------------------------------------------------------------------------------

@pytest.fixture
def running_server(tmp_path):
    """A real server on a free port, with a group of test cases, the way ci_gate.py meets it."""
    config = Config(data_dir=tmp_path / "ci_store", require_login=False)
    app = create_app(config, fn=lambda question: "SELECT amount FROM refunds", judge_fn=JUDGE)
    app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
    store = app.state.store
    group = store.create_group("Billing")
    store.import_into_group(group, pd.DataFrame([("c1", 1, "answer", "Refunds?", "30 days")], columns=COLUMNS))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)
    store.close()


@pytest.mark.parametrize("minimum,exit_code", [("7", 0), ("9", 1)])
def test_the_ci_script_passes_or_fails_the_build_on_the_sql_score(running_server, monkeypatch, minimum, exit_code, capsys):
    monkeypatch.setenv("EVAL_URL", running_server)
    monkeypatch.setenv("EVAL_MINIMUM", minimum)
    monkeypatch.setenv("EVAL_VERSION", f"ci-{minimum}")
    script = runpy.run_path(str(EXAMPLES / "ci_gate.py"), run_name="ci_gate")
    script["POLL_SECONDS"] = 0.2
    assert script["run_gate"]() == exit_code
    assert "SQL score 8" in capsys.readouterr().out


# ---- versions_workflow.py ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("with_columns", ["0", "1"])
def test_the_same_assistant_gives_a_different_version_when_one_setting_changes(serve_example, monkeypatch, with_columns):
    monkeypatch.setenv("WITH_COLUMNS", with_columns)
    row = evaluate(serve_example("versions_workflow.py"), [("c1", 1, "Sales per region?", "SELECT 1")])[0]
    assert row["sql_checks"]["star"] == (with_columns == "0")      # version 1 only knows the table names, so it selects everything
    assert row["sql_checks"]["tables_used"] == (["orders"] if with_columns == "0" else ["orders", "customers"])
