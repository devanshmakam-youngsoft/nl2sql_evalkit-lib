"""A run scores each reply: basic checks first (no model is asked about a reply that fails one), then the judge, and the tables
and columns score comes from the checks."""
import time

import pandas as pd
import pytest

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.core.exceptions import JudgeError
from nl2sql_evalkit.services.db_services import EvalStore
from nl2sql_evalkit.services.evaluation.evaluation_runner import RunManager
from nl2sql_evalkit.services.evaluation.sql_judge import SqlGrade

COLUMNS = ["chat_id", "turn_no", "type", "question", "expected_sql", "expected_tables", "expected_columns"]
GOLD = "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region"
REPLIES = {
    "good": "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region",
    "no join": "SELECT region, SUM(amount) FROM orders GROUP BY region",
    "no sql": "I am not sure which table to use.",
    "broken": "SELECT region FROM",
    "drops": "DROP TABLE orders",
    "vague": "Which customers do you mean by best?",
    "writes": "DELETE FROM orders",
}


class FakeJudge:
    """Stands in for the model: scores 9 and remembers what it was asked about."""

    def __init__(self, fail=False):
        self.asked, self.fail = [], fail

    def grade_sql(self, question, case, reply, checks):
        if self.fail:
            raise JudgeError("the model is down")
        self.asked.append((question, case["type"]))
        return SqlGrade(sql_marks=9, sql_comment="Looks right.", suggestion="Add a LIMIT.")

    def summarize_run(self, stats):
        return None


@pytest.fixture
def store(tmp_path):
    s = EvalStore(Config(data_dir=tmp_path).store_path)
    yield s
    s.close()


def run_cases(store, tmp_path, cases, judge=None, fn=None, **options):
    """Run (name, type, expected_sql, tables, columns) cases; the assistant answers with REPLIES[name]."""
    config = Config(data_dir=tmp_path, **options)
    manager = RunManager(config, store, fn or (lambda question: REPLIES[question]))
    manager._llm_judge = judge or FakeJudge()
    frame = pd.DataFrame([(f"c{i}", 1, kind, name, sql, tables, columns) for i, (name, kind, sql, tables, columns) in enumerate(cases)], columns=COLUMNS)
    run = manager.start("v1", frame, "test set")
    deadline = time.time() + 20
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert run.status == "completed", run.error
    saved = store.get("v1")
    return {r["question"]: r for r in saved["rows"]}, saved["summary"], manager.judge


def test_a_good_reply_is_judged_and_gets_its_reason_suggestion_and_tables_score(store, tmp_path):
    rows, _, judge = run_cases(store, tmp_path, [("good", "answer", GOLD, "orders, customers", "region, amount")])
    row = rows["good"]
    assert (row["sql_marks"], row["sql_remarks"], row["sql_suggestion"]) == (9, "Looks right.", "Add a LIMIT.")
    assert (row["schema_marks"], row["status"]) == (10, "ok") and row["generated_sql"] == REPLIES["good"]
    assert row["sql_checks"]["syntax_ok"] and row["sql_checks"]["read_only"] and row["sql_checks"]["joins_match"]
    assert judge.asked == [("good", "answer")]


def test_missing_tables_lower_the_tables_score_and_a_missing_join_is_in_the_checks(store, tmp_path):
    rows, _, _ = run_cases(store, tmp_path, [("no join", "answer", GOLD, "orders, customers", "region, amount")])
    row = rows["no join"]
    assert row["schema_marks"] == 8 and "Missing tables: customers" in row["schema_remarks"]
    assert row["sql_checks"]["joins_match"] is False and row["sql_checks"]["tables_missing"] == ["customers"]


@pytest.mark.parametrize("name, why", [
    ("no sql", "did not return any SQL"), ("broken", "does not parse as postgres"), ("drops", "not read-only"),
])
def test_a_reply_that_fails_a_basic_check_scores_zero_without_asking_the_model(store, tmp_path, name, why):
    rows, _, judge = run_cases(store, tmp_path, [(name, "answer", GOLD, "orders", "")])
    row = rows[name]
    assert row["sql_marks"] == 0 and why in row["sql_remarks"] and row["sql_suggestion"] and row["schema_marks"] == 0
    assert judge.asked == [] and row["status"] == "ok"


def test_a_vague_question_answered_with_a_question_is_judged_but_with_sql_it_scores_zero(store, tmp_path):
    rows, _, judge = run_cases(store, tmp_path, [("vague", "clarify", "", "", ""), ("good", "clarify", "", "", "")])
    assert rows["vague"]["sql_marks"] == 9 and rows["vague"]["schema_marks"] is None
    assert rows["good"]["sql_marks"] == 0 and "ask a clarifying question" in rows["good"]["sql_remarks"]
    assert judge.asked == [("vague", "clarify")]


def test_a_harmful_question_must_be_declined(store, tmp_path):
    rows, _, judge = run_cases(store, tmp_path, [("writes", "refuse", "", "", ""), ("vague", "refuse", "", "", "")])
    assert rows["writes"]["sql_marks"] == 0 and "decline" in rows["writes"]["sql_remarks"]
    assert rows["vague"]["sql_marks"] == 9 and judge.asked == [("vague", "refuse")]


def test_the_dialect_decides_whether_the_sql_passes_the_gate(store, tmp_path):
    cases = [("SELECT TOP 5 a FROM t", "answer", "", "t", "")]
    rows, _, _ = run_cases(store, tmp_path, cases, fn=lambda q: q, dialect="tsql")
    assert rows["SELECT TOP 5 a FROM t"]["sql_marks"] == 9


def test_a_function_that_fails_scores_zero_and_is_a_failed_question(store, tmp_path):
    def broken(question):
        raise ConnectionError("down")

    rows, summary, judge = run_cases(store, tmp_path, [("good", "answer", GOLD, "orders", "")], fn=broken)
    assert rows["good"]["status"] == "generation_failed" and rows["good"]["sql_marks"] == 0 and judge.asked == []
    assert summary["failed_rows"] == 1


def test_a_judge_that_fails_marks_the_question_grading_failed_and_keeps_the_checks(store, tmp_path):
    rows, _, _ = run_cases(store, tmp_path, [("good", "answer", GOLD, "orders, customers", "")], judge=FakeJudge(fail=True))
    row = rows["good"]
    assert row["status"] == "grading_failed" and row["sql_checks"]["syntax_ok"] and row["schema_marks"] == 10


def test_a_custom_judge_function_is_given_the_checks_and_can_add_a_suggestion(store, tmp_path):
    seen = []

    def judge_fn(question, expected_sql, reply, checks):
        seen.append((question, expected_sql, reply, sorted(checks)[:2]))
        return {"sql_marks": 6, "sql_comment": "Fine.", "suggestion": "Name the columns."}

    config = Config(data_dir=tmp_path)
    manager = RunManager(config, store, lambda q: REPLIES[q], judge_fn=judge_fn)
    manager._llm_judge = FakeJudge()
    frame = pd.DataFrame([("c0", 1, "answer", "good", GOLD, "orders", "")], columns=COLUMNS)
    run = manager.start("v1", frame, "test set")
    while run.status == "running":
        time.sleep(0.05)
    row = store.get("v1")["rows"][0]
    assert (row["sql_marks"], row["sql_suggestion"]) == (6, "Name the columns.") and seen[0][:3] == ("good", GOLD, REPLIES["good"])


def test_the_summary_counts_what_the_checks_found(store, tmp_path):
    cases = [(name, "answer", GOLD, "orders, customers", "") for name in ("good", "no join", "no sql", "broken", "drops")]
    cases += [("vague", "clarify", "", "", ""), ("writes", "refuse", "", "", "")]
    _, summary, _ = run_cases(store, tmp_path, cases)
    assert summary["scores"]["checks"] == {
        "answers": 5, "no_sql": 1, "syntax_failed": 1, "not_read_only": 1, "tables_missing": 1, "columns_missing": 0,
        "joins_differ": 1, "declines": 2, "declines_with_sql": 1,
    }
    assert summary["scores"]["tiers"] == {"high": 3, "mid": 0, "low": 4}
