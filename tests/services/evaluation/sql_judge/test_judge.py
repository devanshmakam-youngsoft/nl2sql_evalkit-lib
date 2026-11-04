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


# ---- the schema the assistant looked at, and why a query is wrong ---------------------------------------------

LOOKUP = {"graded": True, "tables_found": ["t"], "tables_missing": ["approvals"], "columns_found": [], "columns_missing": ["a"]}


def test_the_schema_the_assistant_looked_at_and_what_it_lacked_are_put_in_front_of_the_judge(judge_replying):
    judge, calls = judge_replying(GOOD)
    checks = check_sql("SELECT a FROM t", dialect="postgres", expected_tables="t", expected_columns="a")
    judge.grade_sql("q", CASE, "SELECT a FROM t", checks, schema_context="t(id, b)", lookup=LOOKUP)
    system, user = (m["content"] for m in calls[0])
    assert "Schema the assistant looked at" in user and "t(id, b)" in user
    assert "expected tables missing from it: approvals" in user and "expected columns missing from it: a" in user
    assert "Schema the assistant looked at" in system and "schema_lookup" in system       # the rubric asks for a cause


def test_nothing_is_said_about_a_schema_that_was_not_recorded(judge_replying):
    judge, calls = judge_replying(GOOD)
    judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres"))
    assert "Schema the assistant looked at" not in calls[0][1]["content"]


def test_a_long_schema_is_cut_for_the_judge_with_a_marker(judge_replying):
    judge, calls = judge_replying(GOOD, judge_schema_chars=20)
    judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres"), schema_context="x" * 50, lookup=None)
    assert "x" * 20 + "\u2026 (+30 more characters)" in calls[0][1]["content"]


def test_a_reply_that_should_not_hold_sql_is_not_shown_the_schema(judge_replying):
    judge, calls = judge_replying(GOOD)
    judge.grade_sql("q", {"type": "refuse"}, "No.", check_sql("No.", dialect="postgres"), schema_context="t(id)")
    assert "t(id)" not in calls[0][1]["content"]


@pytest.mark.parametrize("given, expected", [
    ("schema_lookup", "schema_lookup"), ("Schema-Lookup", "schema_lookup"), ("SQL", "sql"), ("both", "both"),
    ("retrieval", "schema_lookup"), ("none", "none"), ("the lookup, mostly", "none"), (None, "none"), (7, "none"),
])
def test_the_cause_is_read_leniently_and_defaults_to_none(judge_replying, given, expected):
    reply = {"sql_marks": 3, "sql_comment": "Wrong table.", "suggestion": "Fix it."}
    if given is not None:
        reply["cause"] = given
    judge, _ = judge_replying(json.dumps(reply))
    assert judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres")).cause == expected


def test_a_grade_without_a_cause_still_parses(judge_replying):
    judge, _ = judge_replying(GOOD)
    assert judge.grade_sql("q", CASE, "SELECT a FROM t", check_sql("SELECT a FROM t", dialect="postgres")).cause == "none"


def test_the_run_findings_mention_schema_lookups_that_missed_something():
    from nl2sql_evalkit.services.evaluation.sql_judge import stats_for_llm
    from nl2sql_evalkit.services.evaluation.sql_judge.fallback_insights import default_suggestions

    summary = {
        "total_rows": 4, "failed_rows": 0, "avg_sql_marks": 6.0, "avg_schema_marks": 8.0, "avg_lookup_marks": 5.0, "avg_total_time": 1.0,
        "scores": {"tiers": {}, "checks": {"answers": 4, "lookup_graded": 4, "lookup_missed": 3}},
    }
    rows = [{"type": "answer", "question": "q", "sql_marks": 2, "sql_remarks": "Wrong table.", "sql_cause": "schema_lookup"}]
    text = stats_for_llm(summary, rows)
    assert "in 3 of 4 questions the schema the assistant looked at did not include an expected table or column" in text
    assert "avg schema lookup marks: 5.0/10" in text and "(cause: schema lookup)" in text
    assert any("looked at often lacked an expected table or column" in s for s in default_suggestions(summary, rows))
