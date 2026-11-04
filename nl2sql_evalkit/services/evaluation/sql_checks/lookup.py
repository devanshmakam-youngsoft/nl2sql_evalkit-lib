"""The schema lookup score: did the tables and columns the assistant looked at include the ones the test case expects."""
import re

from nl2sql_evalkit.core.constants import CLARIFY, REFUSE, parse_type
from nl2sql_evalkit.services.evaluation.sql_checks.checks import split_names


def _has_word(text: str, word: str) -> bool:
    """Whether ``word`` appears in ``text`` as a whole identifier, ignoring case (``order`` is not found in ``orders``)."""
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", text, re.IGNORECASE) is not None


def _column_found(schema: str, expected: str) -> bool:
    """An expected ``table.column`` counts when the column is named in the schema, and also the table when one was written."""
    table, _, column = expected.rpartition(".")
    table = table.rpartition(".")[2]                 # schema.table.column -> table
    return _has_word(schema, column) and (not table or _has_word(schema, table))


def schema_lookup(schema_context: str, expected_tables="", expected_columns="", case_type="answer") -> dict:
    """How much of what the test case expects the recorded schema contained.

    The result has ``graded`` (False when there is nothing to grade: no schema was recorded, the case asks the assistant
    to clarify or refuse, or it expects no tables or columns), ``tables_found``, ``tables_missing``, ``columns_found``,
    ``columns_missing``, ``marks`` (0 to 10, or None) and ``remarks`` (one plain sentence, empty when not graded).
    Each kind that was expected counts equally, as in the tables and columns score.
    """
    wanted_tables, wanted_columns = split_names(expected_tables), split_names(expected_columns)
    result = {"graded": False, "tables_found": [], "tables_missing": [], "columns_found": [], "columns_missing": [],
              "marks": None, "remarks": ""}
    if not str(schema_context or "").strip() or parse_type(case_type) in (CLARIFY, REFUSE) or not (wanted_tables or wanted_columns):
        return result

    result["tables_found"] = [t for t in wanted_tables if _has_word(schema_context, t.rpartition(".")[2])]
    result["tables_missing"] = [t for t in wanted_tables if t not in result["tables_found"]]
    result["columns_found"] = [c for c in wanted_columns if _column_found(schema_context, c)]
    result["columns_missing"] = [c for c in wanted_columns if c not in result["columns_found"]]

    shares = []
    if wanted_tables:
        shares.append(len(result["tables_found"]) / len(wanted_tables))
    if wanted_columns:
        shares.append(len(result["columns_found"]) / len(wanted_columns))
    result["graded"] = True
    result["marks"] = round(10 * sum(shares) / len(shares))
    notes = []
    if result["tables_missing"]:
        notes.append("table" + ("s " if len(result["tables_missing"]) > 1 else " ") + ", ".join(result["tables_missing"]))
    if result["columns_missing"]:
        notes.append("column" + ("s " if len(result["columns_missing"]) > 1 else " ") + ", ".join(result["columns_missing"]))
    result["remarks"] = (
        "The schema the assistant looked at did not include " + " or ".join(notes) + "." if notes
        else "The schema the assistant looked at included every expected table and column."
    )
    return result
