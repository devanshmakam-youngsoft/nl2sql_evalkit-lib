"""One compact score per test case, so any two versions can be compared on the cases they share."""
import hashlib

from nl2sql_evalkit.utils.score_math import is_nan


def case_key(chat_id, turn_no, question, expected_sql, expected_tables="", expected_columns="") -> str:
    """Identifies one test case *as it was asked*: the same chat, turn, question and expectations.

    Versions are compared on cases with the same key, so a case whose question or expected SQL, tables or columns
    were edited between two runs is not mistaken for the same test."""
    raw = "\x1f".join(str(part).strip() for part in (chat_id, turn_no, question, expected_sql, expected_tables, expected_columns))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_case_scores(rows: list[dict]) -> list[dict]:
    """The compact per-case scores of one run, saved on its summary so any two versions can later be
    compared on the cases they share: {k: case key, a: answer marks, m: material marks, t: seconds,
    ok: answered and graded, g: the groups the case belonged to when it ran}."""
    out = []
    for r in rows:
        t = r.get("total_time_taken")
        out.append({
            "k": case_key(r.get("chat_id", ""), r.get("turn_no", 1), r.get("question", ""), r.get("expected_sql", ""),
                         r.get("expected_tables", ""), r.get("expected_columns", "")),
            "a": r.get("answer_marks"),
            "m": r.get("material_marks"),
            "t": None if t is None or is_nan(t) else t,
            "ok": r.get("status") == "ok",
            "g": list(r.get("groups") or []),
        })
    return out
