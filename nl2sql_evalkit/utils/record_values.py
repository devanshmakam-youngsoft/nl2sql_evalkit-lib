"""Small helpers for ids and values stored records share."""
import math
import uuid

from nl2sql_evalkit.core.constants import ANSWER, parse_type


def new_group_id() -> str:
    """Return a new random test case group ID such as ``grp_1a2b3c4d``."""
    return "grp_" + uuid.uuid4().hex[:8]


def clean_cell(val) -> str:
    """A cell value as clean text: a NaN or None becomes an empty string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def expectation_problem(case_type: str, expected_sql, expected_tables, expected_columns) -> str | None:
    """Why a test case cannot be saved as it stands, or None. An ``answer`` case has to say what it expects:
    the SQL, the tables or the columns (any of them). A ``clarify`` or ``refuse`` case expects no SQL at all."""
    if parse_type(case_type) == ANSWER and not any(clean_cell(v) for v in (expected_sql, expected_tables, expected_columns)):
        return "An answer question needs at least one of expected_sql, expected_tables or expected_columns"
    return None
