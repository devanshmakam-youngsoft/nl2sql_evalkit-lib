"""Scoring and choosing among versions that have already been put on the same footing."""
from __future__ import annotations

from typing import Iterable


def mean_of_present(values: Iterable) -> float | None:
    """Return the mean of the values that are not ``None``, or ``None`` if there are none."""
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def overall_quality(view: dict, sql_weight: float, schema_weight: float, use_schema: bool) -> float | None:
    """Return the overall score of one version's ``view``, or ``None`` if its answers were not graded.

    The score is the weighted mean of the SQL and the tables-and-columns marks. When ``use_schema`` is false, the
    tables-and-columns mark is missing or the weights do not add up to a positive number, it is the answer mark alone.
    """
    answer, schema_use = view["answer"], view["schema_use"]
    if answer is None:
        return None
    total = sql_weight + schema_weight
    if not use_schema or schema_use is None or total <= 0:
        return answer
    return (sql_weight * answer + schema_weight * schema_use) / total


def empty_result(
    sql_weight: float, schema_weight: float, tolerance: float, max_time: float | None, considered: int,
    min_quality: float = 0.0,
) -> dict:
    """Return the recommendation result with nothing chosen yet, ready for the comparison to fill in.

    The comparison paths add the keys ``_all`` and ``_views``, which ``choose_best`` removes again.

    Args:
        sql_weight: Weight of the answer score, echoed in the result's ``weights``.
        schema_weight: Weight of the context score, echoed in the result's ``weights``.
        tolerance: Overall-score points within which versions tie; echoed in the result.
        max_time: Response-time ceiling in seconds, or None for no ceiling; echoed in the result.
        considered: How many versions took part in the comparison.
        min_quality: Overall score a version needs to be recommended; echoed in the result.
    """
    return {
        "best": None, "reason": "", "fastest": None, "runner_up": None, "latest_gap": None,
        # the newest run against the recommended one, when both were compared; and what was recommended before it ran
        "latest_vs_best": None, "previous_best": None,
        # nothing reached min_quality: no recommendation, but the best so far is named
        "min_quality": min_quality, "below_minimum": False, "best_so_far": None,
        "not_comparable": [], "not_comparable_detail": {}, "not_comparable_scores": {}, "excluded": [], "excluded_detail": {},
        "budget_miss": False, "basis": "weighted", "basis_note": "",
        "weights": {"answer": sql_weight, "schema_use": schema_weight},
        "tolerance": tolerance, "max_time": max_time, "qualities": {}, "considered": considered,
        # what the comparison was actually made on
        "compared_cases": None, "partial": [], "scores": {},
    }


def _delta(latest: float | None, best: float | None) -> float | None:
    """Return ``latest - best`` rounded to 3 decimals, or ``None`` if either is missing."""
    return None if latest is None or best is None else round(latest - best, 3)


def choose_best(
    best_pool: list[dict], result: dict, *, sql_weight, schema_weight, tolerance, max_time, latest, min_quality: float = 0.0,
) -> dict:
    """Shared by both comparison paths: from versions with ``answer``/``schema_use``/``time``/``idx`` pick the winner."""
    eligible = best_pool
    have_schema = [x for x in eligible if x["schema_use"] is not None]
    use_schema = bool(eligible) and len(have_schema) == len(eligible) and schema_weight > 0
    if not use_schema:
        result["basis"] = "answer_only"
        result["weights"] = {"answer": 1.0, "schema_use": 0.0}
        if have_schema and len(have_schema) != len(eligible) and schema_weight > 0:
            missing = ", ".join(f"v{x['version']}" for x in eligible if x["schema_use"] is None)
            result["basis_note"] = (
                f"Context quality was not graded for {missing}, so versions are compared on answer quality only."
            )
    else:
        total = sql_weight + schema_weight
        result["weights"] = {"answer": sql_weight / total, "schema_use": schema_weight / total}

    for x in result.pop("_all"):
        x["q"] = overall_quality(x, sql_weight, schema_weight, use_schema)
    result["qualities"] = {x["version"]: (round(x["q"], 3) if x["q"] is not None else None) for x in result["_views"]}
    result["scores"] = {
        x["version"]: {
            "answer": x["answer"], "schema_use": x["schema_use"], "time": x["time"], "cases": x.get("cases"),
            "quality": round(x["q"], 3) if x["q"] is not None else None,
        }
        for x in result["_views"] if x["answer"] is not None
    } if result["compared_cases"] is not None else {}
    result.pop("_views")
    if not eligible:
        return result

    speed = lambda x: x["time"] if x["time"] is not None else float("inf")
    fits = eligible if max_time is None else [x for x in eligible if speed(x) <= max_time]
    if not fits:
        result["fastest"] = min(eligible, key=speed)["version"]
        result["budget_miss"] = True
        return result

    top = max(x["q"] for x in fits)
    if top < min_quality:
        leader = max(fits, key=lambda x: (x["q"], -speed(x), x["idx"]))
        result.update(
            below_minimum=True, best_so_far={"version": leader["version"], "quality": round(leader["q"], 3)},
            reason=f"No version scores {min_quality:g} or more yet; v{leader['version']} is the best so far ({leader['q']:.1f}).",
        )
        return result
    tied = [x for x in fits if x["q"] >= top - tolerance and x["q"] >= min_quality]
    # fastest of the tied versions; then higher quality; then the newer run
    best = min(tied, key=lambda x: (speed(x), -x["q"], -x["idx"]))

    if len(fits) == 1:
        reason = "Only version run on this question set."
    elif len(tied) == 1:
        reason = f"Highest overall score of {len(fits)} comparable versions."
    else:
        others = ", ".join(f"v{x['version']}" for x in tied if x is not best)
        reason = f"Overall score is within {tolerance:g} of the top (also {others}) and it is the fastest of those."

    fastest = min(fits, key=speed)
    rest = [x for x in fits if x is not best]
    runner_up = min(rest, key=lambda x: (-x["q"], speed(x))) if rest else None
    gap = best["q"] - latest["q"] if latest in fits and latest is not best else 0

    versus = None
    if latest in fits and latest is not best:
        versus = {
            "version": latest["version"], "answer": _delta(latest["answer"], best["answer"]),
            "schema_use": _delta(latest["schema_use"], best["schema_use"]) if use_schema else None,
            "time": _delta(latest["time"], best["time"]), "quality": _delta(latest["q"], best["q"]),
        }
    result.update(
        latest_vs_best=versus,
        best=best["version"], reason=reason,
        fastest=fastest["version"] if fastest is not best else None,
        runner_up=runner_up["version"] if runner_up else None,
        latest_gap={"version": latest["version"], "gap": round(gap, 3)} if gap > tolerance else None,
    )
    return result


def version_view(summary: dict, group: str | None) -> dict | None:
    """The scores of one run, overall or for one group. None if the run did not cover the group."""
    if group is None:
        return {
            "rows": summary.get("total_rows", 0),
            "failed": summary.get("failed_rows", 0),
            "answer": summary.get("avg_sql_marks"),
            "schema_use": summary.get("avg_schema_marks"),
            "time": summary.get("avg_total_time"),
        }
    stats = (summary.get("group_stats") or {}).get(group)
    if not stats:
        return None
    time = stats.get("avg_total_time")
    return {
        "rows": stats.get("total_rows", 0),
        "failed": stats.get("failed_rows", summary.get("failed_rows", 0)),
        "answer": stats.get("avg_sql_marks"),
        "schema_use": stats.get("avg_schema_marks"),
        "time": time if time is not None else summary.get("avg_total_time"),
    }
