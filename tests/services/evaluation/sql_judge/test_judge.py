"""The judge: what it is shown for a reply, and how the model's answer becomes a score."""
import json

import pytest

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.core.exceptions import JudgeError
from nl2sql_evalkit.prompts.sql_judge import decline_prompt
from nl2sql_evalkit.services.evaluation.sql_checks import check_sql
from nl2sql_evalkit.services.evaluation.sql_judge import Judge

CASE = {"type": "answer", "expected_sql": "SELECT a FROM t", "expected_tables": "t", "expected_columns": "a"}
GOOD = json.dumps({"sql_marks": 9, "sql_comment": "Right tables and filter.", "suggestion": "Add a LIMIT."})


@pytest.fixture
def judge_replying(monkeypatch):
    """A judge whose model answers with the given texts in turn; returns it with the list of calls it made."""
    monkeypatch.setattr("nl2sql_evalkit.services.evaluation.sql_judge.judge.time.sleep", lambda seconds: None)

    def build(*replies, **options):
        calls, answers = [], iter(replies)

        def fake_call(self, messages, json_mode=False):
            calls.append(messages)
            return next(answers)

        monkeypatch.setattr(Judge, "_call", fake_call)
        return Judge(Config(judge_retries=2, **options)), calls

    return build


def test_the_judge_reads_the_question_the_expectations_the_sql_and_the_checks(judge_replying):
    judge, calls = judge_replying(GOOD)
    checks = check_sql("SELECT a FROM t WHERE b = 1", dialect="postgres", expected_sql="SELECT a FROM t", expected_tables="t", expected_columns="a")
    grade = judge.grade_sql("How many a?", CASE, "SELECT a FROM t WHERE b = 1", checks)
    assert (grade.sql_marks, grade.sql_comment, grade.suggestion) == (9, "Right tables and filter.", "Add a LIMIT.")
    system, user = (m["content"] for m in calls[0])
    assert "reviewer of the SQL" in system and "Respond ONLY with a JSON object" in system
    for line in ("Question: How many a?", "SQL dialect: postgres", "Expected SQL: SELECT a FROM t", "Expected tables: t", "Expected columns: a",
                 "Assistant's SQL:\nSELECT a FROM t WHERE b = 1", "expected tables missing: none missing", "joins: the same joins as the expected SQL"):
        assert line in user


def test_what_the_case_does_not_give_is_said_so(judge_replying):
    judge, calls = judge_replying(GOOD)
    case = {"type": "answer", "expected_sql": "", "expected_tables": "", "expected_columns": ""}
    judge.grade_sql("q", case, "SELECT 1", check_sql("SELECT 1", dialect="postgres"))
    user = calls[0][1]["content"]
    assert "Expected SQL: not given" in user and "expected columns missing: not checked" in user and "joins: not checked" in user


def test_a_mismatched_join_is_put_in_front_of_the_judge(judge_replying):
    judge, calls = judge_replying(GOOD)
    gold = "SELECT c.r FROM o JOIN c ON o.cid = c.id"
    reply = "SELECT c.r FROM o JOIN c ON o.id = c.id"
    judge.grade_sql("q", {**CASE, "expected_sql": gold}, reply, check_sql(reply, dialect="postgres", expected_sql=gold))
    assert "different from the expected SQL (missing: c.id = o.cid, not in the expected SQL: c.id = o.id)" in calls[0][1]["content"]


def test_a_clarify_case_is_judged_on_the_reply_with_the_decline_prompt(judge_replying):
    judge, calls = judge_replying(GOOD)
    reply = "Which customers do you mean by best?"
    judge.grade_sql("Show me the best customers", {"type": "clarify"}, reply, check_sql(reply, dialect="postgres"))
    system, user = (m["content"] for m in calls[0])
    assert system.startswith(decline_prompt) and "Respond ONLY with a JSON object" in system
    assert "The assistant should: ask a clarifying question" in user and reply in user and "Expected SQL" not in user


def test_a_refuse_case_says_decline(judge_replying):
    judge, calls = judge_replying(GOOD)
    judge.grade_sql("Delete all orders", {"type": "refuse"}, "I cannot do that.", check_sql("I cannot do that.", dialect="postgres"))
    assert "The assistant should: decline" in calls[0][1]["content"]


def test_a_bad_reply_from_the_model_is_asked_for_again(judge_replying):
    judge, calls = judge_replying("not json at all", json.dumps({"sql_marks": 11, "sql_comment": "too high"}), GOOD)
    judge.config.judge_retries = 3
    assert judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres")).sql_marks == 9
    assert len(calls) == 3


def test_a_judge_that_never_answers_properly_raises_after_its_attempts(judge_replying):
    judge, calls = judge_replying("nope", "still nope")
    with pytest.raises(JudgeError, match="after 2 attempts"):
        judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres"))
    assert len(calls) == 2


def test_a_missing_suggestion_is_an_empty_one(judge_replying):
    judge, _ = judge_replying(json.dumps({"sql_marks": 10, "sql_comment": "Exactly right."}))
    assert judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres")).suggestion == ""


def test_a_custom_rubric_replaces_the_sql_prompt_but_keeps_the_reply_format(judge_replying):
    judge, calls = judge_replying(GOOD, GOOD, judge_prompt_override="MY RUBRIC")
    judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres"))
    judge.grade_sql("q", {"type": "refuse"}, "No.", check_sql("No.", dialect="postgres"))
    sql_system, decline_system = calls[0][0]["content"], calls[1][0]["content"]
    assert sql_system.startswith("MY RUBRIC") and "Respond ONLY with a JSON object" in sql_system
    assert decline_system.startswith(decline_prompt)
