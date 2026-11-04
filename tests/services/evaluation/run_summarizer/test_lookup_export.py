"""The Excel report carries the schema columns only when a step recorded a schema."""
import io

import openpyxl

from nl2sql_evalkit.services.evaluation.run_summarizer import build_results_workbook


def headers(rows, summary=None):
    data = {"summary": {"version": "1", **(summary or {})}, "rows": rows}
    sheet = openpyxl.load_workbook(io.BytesIO(build_results_workbook(data)))["Results"]
    return [cell.value for cell in sheet[1]], [[cell.value for cell in row] for row in sheet.iter_rows(min_row=2)]


ROW = {"chat_id": "c", "turn_no": 1, "type": "answer", "status": "ok", "question": "q", "sql_marks": 7}


def test_the_schema_columns_are_in_the_report_when_a_schema_was_recorded():
    names, body = headers([{**ROW, "schema_context": "orders(id)", "lookup_marks": 5, "lookup_remarks": "Missed table customers.",
                            "sql_cause": "schema_lookup"}])
    assert {"lookup_marks", "lookup_remarks", "schema_context", "sql_cause"} <= set(names)
    row = dict(zip(names, body[0]))
    assert row["schema_context"] == "orders(id)" and row["lookup_marks"] == 5 and row["sql_cause"] == "schema_lookup"


def test_the_report_is_unchanged_when_no_schema_was_recorded():
    names, _ = headers([{**ROW, "schema_context": ""}])
    assert "lookup_marks" not in names and "schema_context" not in names


def test_the_reply_columns_are_in_the_report_only_when_a_reply_was_scored():
    names, body = headers([{**ROW, "reply_style": "Friendly", "reply_text": "Hi there.", "reply_marks": 8,
                            "reply_remarks": "Good.", "reply_suggestion": "Add a number."}], {"avg_reply_marks": 8})
    assert {"reply_style", "reply_text", "reply_marks", "reply_remarks", "reply_suggestion"} <= set(names)
    row = dict(zip(names, body[0]))
    assert row["reply_text"] == "Hi there." and row["reply_marks"] == 8 and row["reply_suggestion"] == "Add a number."


def test_the_report_is_unchanged_when_no_reply_was_scored_even_though_replies_are_kept():
    names, _ = headers([{**ROW, "reply_text": "Hi there."}])
    assert not {"reply_style", "reply_text", "reply_marks"} & set(names)
