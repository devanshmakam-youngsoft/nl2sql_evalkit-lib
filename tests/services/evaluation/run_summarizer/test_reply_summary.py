"""The reply score in the run's scores, its groups, the plain-text facts the findings are written from and the fallback advice."""
from datetime import datetime, timezone

from nl2sql_evalkit.services.evaluation.run_summarizer import build_scores, build_summary
from nl2sql_evalkit.services.evaluation.sql_judge import stats_for_llm
from nl2sql_evalkit.services.evaluation.sql_judge.fallback_insights import default_suggestions

ROWS = [
    {"status": "ok", "type": "answer", "sql_marks": 9, "reply_marks": 8, "total_time_taken": 1.0, "groups": ["Sales"], "question": "a"},
    {"status": "ok", "type": "answer", "sql_marks": 6, "reply_marks": 3, "total_time_taken": 1.0, "groups": ["Sales"], "question": "b"},
    {"status": "ok", "type": "clarify", "sql_marks": 7, "total_time_taken": 1.0, "groups": ["Vague"], "question": "c"},
]


def test_the_reply_score_is_averaged_over_the_questions_that_had_one_and_weak_ones_are_counted():
    scores = build_scores(ROWS)
    assert scores["reply_marks"] == 5.5
    assert scores["checks"]["reply_graded"] == 2 and scores["checks"]["reply_weak"] == 1
    assert scores["by_type"]["answer"]["reply_marks"] == 5.5 and scores["by_type"]["clarify"]["reply_marks"] is None


def test_the_summary_carries_the_average_and_none_when_nothing_was_scored():
    summary = build_summary("v1", ROWS, datetime.now(timezone.utc), "set")
    assert summary["avg_reply_marks"] == 5.5
    plain = build_summary("v1", [{k: v for k, v in r.items() if k != "reply_marks"} for r in ROWS], datetime.now(timezone.utc), "set")
    assert plain["avg_reply_marks"] is None and plain["scores"]["checks"]["reply_graded"] == 0


def test_the_findings_are_told_about_weak_replies():
    summary = build_summary("v1", ROWS, datetime.now(timezone.utc), "set")
    text = stats_for_llm({**summary, "group_stats": {}}, ROWS)
    assert "1 of 2 written replies scored under 5" in text and "avg written reply marks: 5.5/10" in text
    assert any("requested style" in s for s in default_suggestions(summary, ROWS))


def test_the_reply_average_is_a_score_and_never_read_as_a_pipeline_step():
    from nl2sql_evalkit.utils import summary_nodes

    rows = [{**r, "node_timings": {"llm": 0.5}} for r in ROWS]
    summary = build_summary("v1", rows, datetime.now(timezone.utc), "set")
    assert summary["avg_reply_marks"] == 5.5
    assert [n["name"] for n in summary_nodes(summary)] == ["llm"]
