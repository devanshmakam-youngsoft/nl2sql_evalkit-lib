"""The reply score: the written reply is read out of what the assistant returned and scored against a reply style, only
for a question that has one."""
import time

import pandas as pd
import pytest

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.core.exceptions import JudgeError
from nl2sql_evalkit.services.db_services import EvalStore
from nl2sql_evalkit.services.evaluation.evaluation_runner import RunManager
from nl2sql_evalkit.services.evaluation.evaluation_runner.function_adapter import reply_text_of
from nl2sql_evalkit.services.evaluation.sql_judge import ReplyGrade, SqlGrade

COLUMNS = ["chat_id", "turn_no", "type", "question", "expected_sql", "expected_tables", "expected_columns", "reply_style"]
KEYS = ["sql", "query", "answer", "response", "output", "result", "text", "content", "message"]
REPLY_KEYS = ["summary", "response", "reply", "message", "explanation", "final_response"]
STYLE = "Friendly, two sentences"

REPLIES = {
    "totals": {"sql": "SELECT region, SUM(amount) FROM orders GROUP BY region", "summary": "Here are your totals. The north leads."},
    "sql only": "SELECT region FROM orders",
    "fenced": "Here you go.\n```sql\nSELECT region FROM orders\n```",
    "vague": "Which customers do you mean by best?",
    "no reply": {"sql": "SELECT region FROM orders", "summary": ""},
}


class FakeJudge:
    """Scores the SQL 9 and the reply 8, and remembers what it was asked about the reply."""

    def __init__(self, fail=False):
        self.fail, self.replies = fail, []

    def grade_sql(self, question, case, reply, checks, schema_context="", lookup=None):
        return SqlGrade(sql_marks=9, sql_comment="Looks right.", suggestion="")

    def grade_reply(self, question, reply_style, reply_text, sql="", case_type="answer"):
        if self.fail:
            raise JudgeError("the model is down")
        self.replies.append((question, reply_style, reply_text, sql, case_type))
        return ReplyGrade(reply_marks=8, reply_comment="Friendly enough.", suggestion="Say how many.")

    def summarize_run(self, stats):
        return None


@pytest.fixture
def store(tmp_path):
    s = EvalStore(Config(data_dir=tmp_path).store_path)
    yield s
    s.close()


def run_cases(store, tmp_path, cases, judge=None, fn=None, **hooks):
    """Run (name, type, style) cases; ``hooks`` are options for the config (``reply_style``...) or RunManager hooks."""
    manager_hooks = {k: hooks.pop(k) for k in ("reply_judge_fn",) if k in hooks}
    manager = RunManager(Config(data_dir=tmp_path, **hooks), store, fn or (lambda question: REPLIES[question]), **manager_hooks)
    manager._llm_judge = judge or FakeJudge()
    frame = pd.DataFrame([(f"c{i}", 1, kind, name, "", "orders", "", style) for i, (name, kind, style) in enumerate(cases)], columns=COLUMNS)
    run = manager.start("v1", frame, "test set")
    deadline = time.time() + 20
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert run.status == "completed", run.error
    saved = store.get("v1")
    return {r["question"]: r for r in saved["rows"]}, saved["summary"], manager.judge


# ---- reading the reply -------------------------------------------------------------------------------------

@pytest.mark.parametrize("result, answer, expected", [
    ({"sql": "SELECT 1", "summary": "One row."}, "SELECT 1", "One row."),
    ({"sql": "SELECT 1", "message": " Done. ", "explanation": "x"}, "SELECT 1", "Done."),       # the first reply key wins
    ({"response": "Which one do you mean?"}, "Which one do you mean?", "Which one do you mean?"),  # a message sent alone
    ({"sql": "", "message": "I cannot do that."}, "I cannot do that.", "I cannot do that."),
    ({"sql": "SELECT 1"}, "SELECT 1", ""),                                                      # SQL alone: no written reply
    ("SELECT 1", "SELECT 1", ""),
    ("Here you go.\n```sql\nSELECT 1\n```", "Here you go.\n```sql\nSELECT 1\n```", "Here you go."),
    ({"sql": "SELECT 1", "summary": "  "}, "SELECT 1", ""),
])
def test_the_written_reply_is_the_reply_key_after_the_sql_or_the_text_around_it(result, answer, expected):
    assert reply_text_of(result, KEYS, REPLY_KEYS, answer) == expected


def test_a_reply_is_read_from_an_object_and_a_pydantic_model():
    class Out:
        sql = "SELECT 1"
        summary = "One row."

    class Model:
        def model_dump(self):
            return {"sql": "SELECT 1", "reply": "Hi."}

    assert reply_text_of(Out(), KEYS, REPLY_KEYS, "SELECT 1") == "One row."
    assert reply_text_of(Model(), KEYS, REPLY_KEYS, "SELECT 1") == "Hi."


# ---- scoring it ----------------------------------------------------------------------------------------------

def test_a_reply_with_a_style_is_judged_and_gets_its_reason_and_suggestion(store, tmp_path):
    rows, summary, judge = run_cases(store, tmp_path, [("totals", "answer", STYLE)])
    row = rows["totals"]
    assert (row["reply_marks"], row["reply_remarks"], row["reply_suggestion"]) == (8, "Friendly enough.", "Say how many.")
    assert row["reply_style"] == STYLE and row["reply_text"] == "Here are your totals. The north leads."
    assert judge.replies == [("totals", STYLE, "Here are your totals. The north leads.", REPLIES["totals"]["sql"], "answer")]
    assert row["generated_sql"] == REPLIES["totals"]["sql"] and row["sql_marks"] == 9        # the SQL is scored as before
    assert summary["avg_reply_marks"] == 8 and summary["scores"]["reply_marks"] == 8
    assert summary["scores"]["checks"]["reply_graded"] == 1 and summary["scores"]["checks"]["reply_weak"] == 0


def test_without_a_style_nothing_is_asked_about_the_reply(store, tmp_path):
    rows, summary, judge = run_cases(store, tmp_path, [("totals", "answer", "")])
    row = rows["totals"]
    assert "reply_marks" not in row and "reply_style" not in row and row["reply_text"] == "Here are your totals. The north leads."
    assert judge.replies == [] and summary["avg_reply_marks"] is None
    assert summary["scores"]["checks"]["reply_graded"] == 0


def test_the_default_style_from_serve_applies_and_a_test_case_style_wins(store, tmp_path):
    rows, _, judge = run_cases(store, tmp_path, [("totals", "answer", ""), ("fenced", "answer", "Formal")], reply_style="Short")
    assert rows["totals"]["reply_style"] == "Short" and rows["fenced"]["reply_style"] == "Formal"
    assert [(q, style) for q, style, *_ in judge.replies] == [("totals", "Short"), ("fenced", "Formal")]


def test_a_reply_that_is_not_there_scores_0_without_asking_the_model(store, tmp_path):
    rows, summary, judge = run_cases(store, tmp_path, [("sql only", "answer", STYLE), ("no reply", "answer", STYLE)])
    for name in ("sql only", "no reply"):
        assert rows[name]["reply_marks"] == 0 and rows[name]["reply_remarks"] == "The assistant returned no written reply."
        assert rows[name]["reply_suggestion"]
    assert judge.replies == []
    assert summary["avg_reply_marks"] == 0 and summary["scores"]["checks"]["reply_weak"] == 2


def test_the_message_of_a_question_back_is_the_reply_and_the_case_type_goes_to_the_judge(store, tmp_path):
    rows, _, judge = run_cases(store, tmp_path, [("vague", "clarify", STYLE)])
    assert rows["vague"]["reply_text"] == REPLIES["vague"] and rows["vague"]["reply_marks"] == 8
    assert judge.replies == [("vague", STYLE, REPLIES["vague"], "", "clarify")]


def test_a_text_around_fenced_sql_is_the_reply(store, tmp_path):
    rows, _, judge = run_cases(store, tmp_path, [("fenced", "answer", STYLE)])
    assert rows["fenced"]["reply_text"] == "Here you go." and judge.replies[0][3] == "SELECT region FROM orders"


def test_reply_keys_can_be_changed(store, tmp_path):
    fn = lambda q: {"sql": "SELECT 1 FROM orders", "narrative": "Done.", "summary": "ignored"}  # noqa: E731
    rows, _, _ = run_cases(store, tmp_path, [("q", "answer", STYLE)], fn=fn, reply_keys=["narrative"])
    assert rows["q"]["reply_text"] == "Done."


def test_a_custom_reply_judge_replaces_the_model_and_is_clamped(store, tmp_path):
    seen = []

    def reply_judge_fn(question, reply_style, reply_text, sql):
        seen.append((question, reply_style, reply_text, sql))
        return {"reply_marks": 14, "reply_comment": "Mine."}

    judge = FakeJudge()
    rows, _, _ = run_cases(store, tmp_path, [("totals", "answer", STYLE)], judge=judge, reply_judge_fn=reply_judge_fn)
    assert rows["totals"]["reply_marks"] == 10 and rows["totals"]["reply_remarks"] == "Mine." and rows["totals"]["reply_suggestion"] == ""
    assert seen == [("totals", STYLE, "Here are your totals. The north leads.", REPLIES["totals"]["sql"])] and judge.replies == []


def test_a_custom_reply_judge_that_raises_is_a_problem_on_the_row_not_a_crash(store, tmp_path):
    def broken(question, reply_style, reply_text, sql):
        raise RuntimeError("boom")

    rows, _, _ = run_cases(store, tmp_path, [("totals", "answer", STYLE)], reply_judge_fn=broken)
    assert rows["totals"]["reply_marks"] == 0 and rows["totals"]["status"] == "ok" and rows["totals"]["reply_remarks"]


def test_a_judge_that_cannot_grade_the_reply_marks_the_question_failed_and_the_run_carries_on(store, tmp_path):
    rows, summary, _ = run_cases(store, tmp_path, [("totals", "answer", STYLE), ("sql only", "answer", "")], judge=FakeJudge(fail=True))
    assert rows["totals"]["status"] == "grading_failed" and rows["totals"]["error_message"] and "reply_marks" not in rows["totals"]
    assert rows["totals"]["sql_marks"] == 9                                  # the SQL was graded before the reply failed
    assert rows["sql only"]["status"] == "ok" and summary["failed_rows"] == 1


def test_a_failed_question_with_a_style_gets_reply_marks_0(store, tmp_path):
    def broken(question):
        raise RuntimeError("down")

    rows, _, judge = run_cases(store, tmp_path, [("totals", "answer", STYLE)], fn=broken)
    assert rows["totals"]["status"] == "generation_failed" and rows["totals"]["reply_marks"] == 0 and judge.replies == []
