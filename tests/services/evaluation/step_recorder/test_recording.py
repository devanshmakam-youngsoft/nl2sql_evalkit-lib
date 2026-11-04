"""Step recording: steps from any thread, what each step keeps, and the limits on what is kept."""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.main import create_app
from nl2sql_evalkit.services.evaluation import step_recorder


def run_question(body, detail="all"):
    """What the runner does around one call of the developer's function."""
    step_recorder.begin_question(detail)
    try:
        body()
    finally:
        step_recorder.end_question()
    return step_recorder.collect_question()


@pytest.fixture(autouse=True)
def default_limits(monkeypatch):
    monkeypatch.setitem(step_recorder.LIMITS, "value", 1000)
    monkeypatch.setitem(step_recorder.LIMITS, "schema", 20000)


# ---- steps and notes from any thread --------------------------------------------------------------------

def test_steps_started_in_a_thread_pool_are_recorded_with_their_outputs():
    def search(name, delay):
        with step_recorder.step(name) as s:
            time.sleep(delay)
            s.output = f"text from {name}"

    def body():
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda args: search(*args), [("index_a", 0.05), ("index_b", 0.01)]))

    got = run_question(body)
    steps = {s["name"]: s for s in got["steps"]}
    assert set(steps) == {"index_a", "index_b"}
    assert steps["index_a"]["elapsed"] >= 0.05 and steps["index_b"]["output"] == "text from index_b"


def test_notes_from_a_thread_reach_the_question():
    def body():
        with ThreadPoolExecutor(1) as pool:
            pool.submit(lambda: step_recorder.note("intent", "billing")).result()

    assert run_question(body)["flags"] == {"intent": "billing"}


def test_steps_are_listed_in_the_order_they_started_not_the_order_they_finished():
    def body():
        first, second = step_recorder.step("first"), step_recorder.step("second")      # started in this order...
        with second:
            pass
        with first:                                                              # ...finished in the other
            pass

    assert [s["name"] for s in run_question(body)["steps"]] == ["first", "second"]


def test_a_step_that_finishes_after_its_question_is_over_does_not_land_in_the_next_one():
    step_recorder.begin_question("all")
    late = step_recorder.step("late")
    late.__enter__()
    step_recorder.end_question()
    assert step_recorder.collect_question()["steps"] == []

    step_recorder.begin_question("all")
    late.__exit__(None, None, None)                  # the slow thread from question 1 ends during question 2
    step_recorder.end_question()
    assert step_recorder.collect_question()["steps"] == []


def test_async_steps_run_together_are_all_recorded():
    async def work(name):
        with step_recorder.step(name):
            await asyncio.sleep(0.01)

    async def main():
        await asyncio.gather(work("a"), work("b"))

    assert {s["name"] for s in run_question(lambda: asyncio.run(main()))["steps"]} == {"a", "b"}


def test_nothing_is_recorded_outside_an_evaluation_run():
    with step_recorder.step("outside") as s:
        s.output = "x"
    step_recorder.note("k", "v")
    assert step_recorder.collect_question() == {"steps": [], "flags": {}}


def test_detail_modes_keep_what_they_promise():
    def body():
        with step_recorder.step("quiet"):
            pass
        with step_recorder.step("loud") as s:
            s.output = "written"

    assert {s["name"] for s in run_question(body, "selected")["steps"]} == {"loud"}
    off = run_question(body, "off")["steps"]
    assert {s["name"] for s in off} == {"quiet", "loud"} and all(set(s) == {"name", "elapsed"} for s in off)


# ---- what a step keeps ---------------------------------------------------------------------------------

def test_a_decorated_step_keeps_its_inputs_and_its_return_value():
    @step_recorder.step("pick_tables")
    def pick_tables(question):
        return "orders, customers"

    entry = run_question(lambda: pick_tables("Who ordered?"))["steps"][0]
    assert entry["inputs"] == {"question": "Who ordered?"} and entry["output"] == "orders, customers"


def test_a_context_manager_keeps_the_output_it_is_given():
    def body():
        with step_recorder.step("write_sql") as s:
            s.output = "SELECT 1"

    assert run_question(body)["steps"][0]["output"] == "SELECT 1"


# ---- the limits ----------------------------------------------------------------------------------------

def test_shown_values_are_cut_with_a_marker_saying_how_much_is_missing():
    @step_recorder.step("step")
    def long_output(text):
        return text

    steps = run_question(lambda: long_output("x" * 1500))["steps"]
    assert steps[0]["output"] == "x" * 1000 + "… (+500 more characters)"
    assert steps[0]["inputs"]["text"].endswith("(+500 more characters)")


def test_the_limit_can_be_set():
    step_recorder.configure(max_step_value_chars=7)
    try:
        assert step_recorder.LIMITS["value"] == 7
    finally:
        step_recorder.configure(max_step_value_chars=1000)


def test_a_vector_is_summarised_not_stored():
    @step_recorder.step("embed")
    def embed(q):
        return [0.1] * 1536

    assert run_question(lambda: embed("q"))["steps"][0]["output"] == "[1536 numbers]"
    assert step_recorder.display_text([1, 2, 3]) == "[1, 2, 3]"           # a short list is shown as it is


# ---- through the runner --------------------------------------------------------------------------------

def make_manager(tmp_path, fn):
    app = create_app(Config(data_dir=tmp_path / "data", require_login=False, eval_secret="s"), fn=fn, generation_llm=lambda m: "{}")
    return app.state.manager


def test_a_step_that_ran_several_times_has_its_time_added_up(tmp_path):
    def fn(question):
        with ThreadPoolExecutor(2) as pool:                    # the same search, on two indexes at once
            list(pool.map(lambda _: _timed_search(), range(2)))
        with step_recorder.step("llm"):
            time.sleep(0.01)
        return "answer"

    def _timed_search():
        with step_recorder.step("search") as s:
            time.sleep(0.05)
            s.output = "chunk"

    answer, elapsed, timings, _, outputs, _, _, _ = make_manager(tmp_path, fn)._call_fn("q", [], "s1")
    assert answer == "answer" and list(timings) == ["search", "llm"]
    assert timings["search"] >= 0.1 and timings["llm"] >= 0.01        # both searches counted, not just the last
    assert outputs["search"] == "chunk"


def test_the_runner_applies_the_configured_limits(tmp_path):
    config = Config(data_dir=tmp_path / "data", require_login=False, eval_secret="s", step_value_chars=30)
    app = create_app(config, fn=lambda q: "a", generation_llm=lambda m: "{}")
    assert step_recorder.LIMITS["value"] == 30
    step_recorder.configure(max_step_value_chars=1000)
    del app


# ---- the schema a step looked at -------------------------------------------------------------------------

def test_a_step_can_say_which_schema_it_looked_at():
    def body():
        with step_recorder.step("schema_lookup") as s:
            s.schema = ["orders(id, amount)", "customers(id, name)"]

    step = run_question(body)["steps"][0]
    assert step["schema"] == "orders(id, amount)\ncustomers(id, name)"


def test_a_decorated_function_returns_its_schema_when_declared_so():
    @step_recorder.step("schema_lookup", schema=True)
    def pick_tables(question):
        return {"orders": ["id", "amount"], "customers": {"id": "int", "name": "text"}}

    @step_recorder.step("rewrite")
    def rewrite(question):
        return question.lower()

    got = run_question(lambda: (pick_tables("q"), rewrite("Q")))["steps"]
    assert got[0]["schema"] == "orders(id, amount)\ncustomers(id int, name text)"
    assert got[1]["schema"] == ""                       # a step that did not declare one has none
    assert got[0]["output"].startswith("{")             # the return value is still shown as the step's output


def test_lists_of_table_descriptions_are_written_out_as_lines():
    from nl2sql_evalkit.services.evaluation.step_recorder.schema_text import schema_text

    assert schema_text([{"table": "orders", "columns": ["id", {"name": "amount", "type": "numeric"}]}, "customers(id)"]) \
        == "orders(id, amount numeric)\ncustomers(id)"
    assert schema_text(None) == "" and schema_text("orders(id)") == "orders(id)"


def test_the_schemas_of_several_steps_are_joined_each_once_and_cut_at_the_limit():
    def body():
        for name, text in (("a", "orders(id)"), ("b", "customers(id)"), ("c", "orders(id)")):
            with step_recorder.step(name) as s:
                s.schema = text

    steps = run_question(body)["steps"]
    assert step_recorder.joined_schema(steps) == "orders(id)\n\ncustomers(id)"
    assert step_recorder.joined_schema([{"name": "x", "elapsed": 0.0}]) == ""         # none declared: nothing recorded
    step_recorder.configure(max_schema_chars=10)
    try:
        assert step_recorder.joined_schema(steps) == "orders(id)… (+15 more characters)"
    finally:
        step_recorder.configure(max_schema_chars=20000)


def test_a_schema_is_kept_in_selected_mode_and_dropped_when_no_content_is_recorded():
    def body():
        with step_recorder.step("schema_lookup") as s:
            s.schema = "orders(id)"
        with step_recorder.step("plain"):
            pass

    assert [s["name"] for s in run_question(body, "selected")["steps"]] == ["schema_lookup"]
    assert all("schema" not in s for s in run_question(body, "off")["steps"])


def test_the_runner_hands_the_joined_schema_back(tmp_path):
    def fn(question):
        with step_recorder.step("schema_lookup") as s:
            s.schema = "orders(id)"
        return "SELECT 1"

    *_, schema, _ = make_manager(tmp_path, fn)._call_fn("q", [], "s1")
    assert schema == "orders(id)"
