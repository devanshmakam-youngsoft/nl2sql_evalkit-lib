"""The text the judge reads about one reply."""
from nl2sql_evalkit.core.constants import CLARIFY, parse_type


def _joins_line(checks: dict) -> str:
    if checks.get("joins_match") is None:
        return "not checked (no expected SQL)"
    if checks["joins_match"]:
        return "the same joins as the expected SQL"
    parts = []
    if checks.get("joins_missing"):
        parts.append("missing: " + "; ".join(checks["joins_missing"]))
    if checks.get("joins_extra"):
        parts.append("not in the expected SQL: " + "; ".join(checks["joins_extra"]))
    return "different from the expected SQL (" + ", ".join(parts) + ")"


def _missing_line(missing) -> str:
    if missing is None:
        return "not checked"
    return "none missing" if not missing else ", ".join(missing)


def grading_input(question: str, case_type: str, expected_sql: str, expected_tables: str, expected_columns: str,
                  reply: str, checks: dict, dialect: str) -> str:
    """The user message for the judge: the question, what the test case expects, the reply and the checks already done.

    A ``clarify`` or ``refuse`` case gets a shorter message: the judge reads the reply as plain text.
    """
    if parse_type(case_type) != "answer":
        should = "ask a clarifying question instead of guessing" if parse_type(case_type) == CLARIFY else "decline"
        return f"Question: {question}\n\nThe assistant should: {should}\n\nAssistant's reply:\n{reply.strip() or '(no reply)'}"
    return (
        f"Question: {question}\n\nSQL dialect: {dialect}\n\n"
        f"Expected SQL: {expected_sql.strip() or 'not given'}\n"
        f"Expected tables: {expected_tables.strip() or 'not given'}\n"
        f"Expected columns: {expected_columns.strip() or 'not given'}\n\n"
        f"Assistant's SQL:\n{checks['sql']}\n\n"
        "Checks already done by the program:\n"
        f"- parses as {dialect}: yes\n- read-only: yes\n"
        f"- expected tables missing: {_missing_line(checks.get('tables_missing'))}\n"
        f"- expected columns missing: {_missing_line(checks.get('columns_missing'))}\n"
        f"- joins: {_joins_line(checks)}"
    )
