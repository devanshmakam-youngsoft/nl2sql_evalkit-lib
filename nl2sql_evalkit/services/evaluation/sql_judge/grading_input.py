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


def _schema_block(schema_context: str, lookup: dict | None, limit: int) -> str:
    """What the assistant looked at before writing the SQL, and whether it held the expected tables and columns."""
    text = schema_context.strip()
    if not text:
        return ""
    if limit and len(text) > limit:
        text = f"{text[:limit]}\u2026 (+{len(text) - limit} more characters)"
    block = f"\n\nSchema the assistant looked at (the tables and columns it had when it wrote the SQL):\n{text}"
    if lookup and lookup.get("graded"):
        block += (
            "\nChecks on that schema:\n"
            f"- expected tables missing from it: {_missing_line(lookup.get('tables_missing') if lookup.get('tables_missing') is not None else [])}\n"
            f"- expected columns missing from it: {_missing_line(lookup.get('columns_missing') if lookup.get('columns_missing') is not None else [])}"
        )
    return block


def grading_input(question: str, case_type: str, expected_sql: str, expected_tables: str, expected_columns: str,
                  reply: str, checks: dict, dialect: str, schema_context: str = "", lookup: dict | None = None,
                  schema_chars: int = 6000) -> str:
    """The user message for the judge: the question, what the test case expects, the reply and the checks already done.

    When the assistant recorded the schema it looked at, that is added too (cut to ``schema_chars``) with what the lookup
    check found, so the judge can say whether a wrong query comes from the lookup or from the SQL.
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
        + _schema_block(schema_context, lookup, schema_chars)
    )
