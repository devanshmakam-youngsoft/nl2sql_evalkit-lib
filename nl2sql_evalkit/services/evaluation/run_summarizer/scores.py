"""The detailed scores of one run."""
import math

from nl2sql_evalkit.core.constants import ANSWER, is_declining, parse_type
from nl2sql_evalkit.utils import column_of, is_nan, mean_of


def build_scores(rows: list[dict]) -> dict:
    """The detailed scores of one run, saved on its summary so every later comparison reads them
    instead of recomputing from receipts: overall averages, score tiers, per-question-type
    averages, response-time spread and what the checks on the SQL found."""
    graded = [r for r in rows if r.get("sql_marks") is not None]
    marks = [r["sql_marks"] for r in graded]
    times = sorted(t for t in column_of(rows, "total_time_taken") if t is not None and not is_nan(t))
    by_type: dict[str, list[dict]] = {}
    for r in graded:
        by_type.setdefault(str(r.get("type") or "unknown"), []).append(r)
    answers = [r for r in rows if r.get("sql_checks") and parse_type(r.get("type")) == ANSWER]
    declines = [r for r in rows if r.get("sql_checks") and is_declining(r.get("type"))]
    looked_up = [r for r in rows if (r.get("schema_lookup") or {}).get("graded")]
    return {
        "graded_rows": len(graded),
        "sql_marks": mean_of(marks),
        "schema_marks": mean_of(column_of(rows, "schema_marks")),
        "lookup_marks": mean_of(column_of(rows, "lookup_marks")),
        "tiers": {
            "high": sum(1 for m in marks if m >= 8),
            "mid": sum(1 for m in marks if 5 <= m < 8),
            "low": sum(1 for m in marks if m < 5),
        },
        "by_type": {
            t: {
                "rows": len(rs),
                "sql_marks": mean_of(column_of(rs, "sql_marks")),
                "schema_marks": mean_of(column_of(rs, "schema_marks")),
                "lookup_marks": mean_of(column_of(rs, "lookup_marks")),
            }
            for t, rs in by_type.items()
        },
        "time": {
            "avg": mean_of(times, 3),
            "p95": round(times[max(0, math.ceil(0.95 * len(times)) - 1)], 3) if times else None,
        },
        "checks": {
            "answers": len(answers),
            "no_sql": sum(1 for r in answers if not r["sql_checks"]["returned_sql"]),
            "syntax_failed": sum(1 for r in answers if r["sql_checks"]["syntax_ok"] is False),
            "not_read_only": sum(1 for r in answers if r["sql_checks"]["read_only"] is False),
            "tables_missing": sum(1 for r in answers if r["sql_checks"]["tables_missing"]),
            "columns_missing": sum(1 for r in answers if r["sql_checks"]["columns_missing"]),
            "joins_differ": sum(1 for r in answers if r["sql_checks"]["joins_match"] is False),
            "declines": len(declines),
            "declines_with_sql": sum(1 for r in declines if r["sql_checks"]["returned_sql"]),
            "lookup_graded": len(looked_up),
            "lookup_missed": sum(1 for r in looked_up if r["schema_lookup"]["tables_missing"] or r["schema_lookup"]["columns_missing"]),
        },
    }
