"""The text the judge reads about one written reply."""
from nl2sql_evalkit.core.constants import parse_type

_EXPECTED = {
    "answer": "write SQL for the question (the written reply goes with it)",
    "clarify": "ask a clarifying question instead of guessing (the reply is that question)",
    "refuse": "decline (the reply is the refusal)",
}


def reply_input(question: str, reply_style: str, reply_text: str, sql: str, case_type: str = "answer",
                reply_chars: int = 4000) -> str:
    """The user message for the reply judge: the question, what the assistant should do, the style asked for, the reply
    and the SQL it goes with.

    The reply is cut to ``reply_chars`` with a marker saying how much was left out.
    """
    text = reply_text.strip()
    if reply_chars and len(text) > reply_chars:
        text = f"{text[:reply_chars]}\u2026 (+{len(text) - reply_chars} more characters)"
    return (
        f"Question: {question}\n\n"
        f"The assistant should: {_EXPECTED.get(parse_type(case_type) or 'answer')}\n\n"
        f"Reply style:\n{reply_style.strip()}\n\n"
        f"Assistant's reply:\n{text}\n\n"
        f"SQL the assistant wrote:\n{sql.strip() or 'none'}"
    )
