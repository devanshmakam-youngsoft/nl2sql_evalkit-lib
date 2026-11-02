"""The checks on one reply: they read the SQL and compare it with what the test case expects. Nothing is run."""
import re

from nl2sql_evalkit.core.constants import CLARIFY, REFUSE, parse_type
from nl2sql_evalkit.services.evaluation.sql_checks.analysis import (
    columns_used,
    join_keys,
    parse_statements,
    read_only_problem,
    tables_used,
)
from nl2sql_evalkit.services.evaluation.sql_checks.reply import split_reply


def split_names(text) -> list[str]:
    """``"orders, Customers"`` -> ``["orders", "customers"]``: lower-cased, split on commas, semicolons and pipes."""
    seen: dict[str, None] = {}
    for part in re.split(r"[,;|\n]", str(text or "")):
        name = part.strip().strip("`\"[]").lower()
        if name and name != "nan":
            seen.setdefault(name)
    return list(seen)


def _column_present(expected: str, used: list[str], star: bool) -> bool:
    """Whether an expected ``table.column`` or ``column`` is among the columns used (``SELECT *`` is given the benefit of the doubt)."""
    if star:
        return True
    table, _, column = expected.rpartition(".")
    table = table.rpartition(".")[2]                 # schema.table.column -> table
    for item in used:
        used_table, _, used_column = item.rpartition(".")
        if used_column == column and (not table or not used_table or used_table == table):
            return True
    return False


def check_sql(reply, *, dialect: str, expected_sql="", expected_tables="", expected_columns="") -> dict:
    """Run every check that applies to one reply and return the findings.

    A value of ``None`` means the check did not apply (no SQL to read, or nothing expected to compare with).

    Keys: ``sql`` and ``message`` (the reply split into its SQL and its plain text), ``returned_sql``, ``syntax_ok`` and
    ``syntax_error``, ``read_only`` and ``read_only_problem``, ``tables_used``, ``columns_used``, ``star`` (the query
    selects ``*``), ``tables_missing``, ``columns_missing``, and ``joins_match`` with ``joins_missing`` and ``joins_extra``
    (the pairs of columns the expected SQL joins on that this query does not, and the other way round).
    """
    sql, message = split_reply(reply)
    checks: dict = {
        "sql": sql, "message": message, "returned_sql": bool(sql),
        "syntax_ok": None, "syntax_error": "", "read_only": None, "read_only_problem": "",
        "tables_used": [], "columns_used": [], "star": False,
        "tables_missing": None, "columns_missing": None,
        "joins_match": None, "joins_missing": [], "joins_extra": [],
    }
    if not sql:
        return checks

    statements, error = parse_statements(sql, dialect)
    checks["syntax_ok"], checks["syntax_error"] = not error, error
    if error:
        return checks

    problem = read_only_problem(statements)
    checks["read_only"], checks["read_only_problem"] = not problem, problem
    if problem:
        return checks                                # nothing more is read from SQL that must never run
    checks["tables_used"] = tables_used(statements)
    checks["columns_used"], checks["star"] = columns_used(statements)

    wanted_tables, wanted_columns = split_names(expected_tables), split_names(expected_columns)
    if wanted_tables:
        used = {t.rpartition(".")[2] for t in checks["tables_used"]}
        checks["tables_missing"] = [t for t in wanted_tables if t.rpartition(".")[2] not in used]
    if wanted_columns:
        checks["columns_missing"] = [c for c in wanted_columns if not _column_present(c, checks["columns_used"], checks["star"])]

    gold, gold_error = parse_statements(str(expected_sql or ""), dialect) if str(expected_sql or "").strip() else ([], "no expected SQL")
    if gold and not gold_error:
        wanted, got = join_keys(gold), join_keys(statements)
        checks["joins_missing"] = [pair for pair in wanted if pair not in got]
        checks["joins_extra"] = [pair for pair in got if pair not in wanted]
        checks["joins_match"] = not checks["joins_missing"] and not checks["joins_extra"]
    return checks


def schema_use_marks(checks: dict, expected_tables="", expected_columns="", case_type="answer") -> tuple[int | None, str]:
    """The tables and columns score (0 to 10) with a sentence saying why, or ``(None, "")`` when nothing was expected.

    Each kind that was expected counts equally: the share of the expected tables found, the share of the expected columns
    found. No SQL, or SQL that does not parse, scores 0 when something was expected.
    """
    wanted_tables, wanted_columns = split_names(expected_tables), split_names(expected_columns)
    if parse_type(case_type) in (CLARIFY, REFUSE) or not (wanted_tables or wanted_columns):
        return None, ""
    if not checks["returned_sql"]:
        return 0, "No SQL was returned, so none of the expected tables and columns were used."
    if checks["syntax_ok"] is False or checks["read_only"] is False:
        return 0, "The SQL could not be used (it does not parse or is not read-only), so none of the expected tables and columns count."
    shares, notes = [], []
    if wanted_tables:
        missing = checks["tables_missing"] or []
        shares.append((len(wanted_tables) - len(missing)) / len(wanted_tables))
        notes.append("Missing tables: " + ", ".join(missing) if missing else "Used all the expected tables")
    if wanted_columns:
        missing = checks["columns_missing"] or []
        shares.append((len(wanted_columns) - len(missing)) / len(wanted_columns))
        notes.append("Missing columns: " + ", ".join(missing) if missing else "Used all the expected columns")
    return round(10 * sum(shares) / len(shares)), "; ".join(notes) + "."


def gate(checks: dict, case_type, dialect: str) -> tuple[int, str, str] | None:
    """A mark of 0 with its reason and a suggestion when the reply fails a basic check, so the model is not asked.

    ``None`` means the reply passed the gates and is for the judge to score. An ``answer`` case fails without SQL, with SQL
    that does not parse, and with SQL that is not read-only; a ``clarify`` or ``refuse`` case fails with any SQL at all.
    """
    kind = parse_type(case_type)
    if kind in (CLARIFY, REFUSE):
        if checks["returned_sql"]:
            what = "ask a clarifying question" if kind == CLARIFY else "decline"
            return 0, f"The assistant returned SQL where it should {what}.", \
                f"Make the assistant {what} for questions like this one instead of writing a query."
        return None
    if not checks["returned_sql"]:
        return 0, "The assistant did not return any SQL.", "Check that the function returns the query, or the key it is under."
    if checks["syntax_ok"] is False:
        return 0, f"The SQL does not parse as {dialect}: {checks['syntax_error']}.", \
            f"Fix the syntax, and check the dialect is {dialect} (serve(dialect=...))."
    if checks["read_only"] is False:
        return 0, f"The SQL is not read-only: {checks['read_only_problem']}.", \
            "Only allow a single SELECT: reject or rewrite anything that changes data before it reaches the database."
    return None
