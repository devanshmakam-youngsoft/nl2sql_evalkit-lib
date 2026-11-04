"""The facts about a run that the judge reads before writing its findings."""
import statistics

from nl2sql_evalkit.utils import summary_nodes


def _checks_line(checks: dict) -> str:
    """What the checks on the SQL found, as one plain sentence."""
    if not checks.get("answers") and not checks.get("declines"):
        return "no checks ran"
    parts = []
    if checks.get("answers"):
        found = [f"{checks[key]} {label}" for key, label in (
            ("no_sql", "returned no SQL"), ("syntax_failed", "did not parse"), ("not_read_only", "were not read-only"),
            ("tables_missing", "left out an expected table"), ("columns_missing", "left out an expected column"),
            ("joins_differ", "joined differently from the expected SQL")) if checks.get(key)]
        parts.append(f"of {checks['answers']} questions that should get SQL: " + (", ".join(found) if found else "none had a problem"))
    if checks.get("lookup_graded"):
        parts.append(f"in {checks.get('lookup_missed', 0)} of {checks['lookup_graded']} questions the schema the assistant looked at "
                     "did not include an expected table or column")
    if checks.get("declines"):
        parts.append(f"{checks.get('declines_with_sql', 0)} of {checks['declines']} questions that should be declined or "
                     "clarified got SQL instead")
    return "; ".join(parts)


def stats_for_llm(summary: dict, rows: list[dict]) -> str:
    """Return a run's scores, timings and three lowest-scoring rows as the plain text the judge summarises.

    Args:
        summary: The run summary as built by ``build_summary`` plus its ``group_stats``.
        rows: The per-question result rows of the same run.
    """
    by_type: dict[str, list[float]] = {}
    for r in rows:
        if r.get("sql_marks") is not None:
            by_type.setdefault(r["type"], []).append(r["sql_marks"])
    type_line = ", ".join(f"{t}: {statistics.fmean(v):.1f} over {len(v)} rows" for t, v in by_type.items())
    worst = sorted((r for r in rows if r.get("sql_marks") is not None), key=lambda r: r["sql_marks"])[:3]
    worst_lines = "\n".join(
        f"- [{r['sql_marks']}/10] {r['question'][:100]} :: {str(r.get('sql_remarks'))[:160]}"
        + (f" (cause: {r['sql_cause'].replace('_', ' ')})" if r.get("sql_cause") not in (None, "", "none") else "")
        for r in worst
    )
    total_time = summary.get("avg_total_time") or 0
    nodes = ", ".join(
        f"{n['name']}={n['avg']}s" + (f" ({n['avg'] / total_time:.0%} of the response time)" if total_time else "")
        for n in summary_nodes(summary)
    )
    group_line = ", ".join(
        f"{g}: SQL {st['avg_sql_marks']}, tables and columns {st['avg_schema_marks']} over {st['total_rows']} rows"
        for g, st in (summary.get("group_stats") or {}).items()
    ) or "n/a"
    scores = summary.get("scores") or {}
    tiers = scores.get("tiers") or {}
    return (
        f"Score tiers (SQL): {tiers.get('high', 0)} high (8+), {tiers.get('mid', 0)} middling (5-7), {tiers.get('low', 0)} low (<5)\n"
        f"By group: {group_line}\nChecks: {_checks_line(scores.get('checks') or {})}\n"
        f"Rows: {summary['total_rows']} (failed: {summary['failed_rows']})\n"
        f"Avg SQL marks: {summary['avg_sql_marks']}/10, avg tables and columns marks: {summary['avg_schema_marks']}/10"
        + (f", avg schema lookup marks: {summary['avg_lookup_marks']}/10" if summary.get("avg_lookup_marks") is not None else "") + "\n"
        f"Avg end-to-end time: {summary['avg_total_time']}s; time per step: {nodes}\n"
        f"SQL marks by type: {type_line}\nLowest scoring rows:\n{worst_lines}"
    )
