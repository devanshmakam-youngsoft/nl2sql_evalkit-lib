"""Test case types: what the assistant should do with a question.

``answer``   a clear question in scope: the assistant should return SQL (the default)
``clarify``  a vague question: the assistant should ask something back instead of guessing
``refuse``   a harmful or out-of-bounds question: the assistant should decline

Other spellings are understood (``sql``, ``vague``, ``ambiguous``, ``unsafe``, ``attack``...); the library stores the three names.
"""
import re

ANSWER = "answer"


CLARIFY = "clarify"


REFUSE = "refuse"


TYPES = (ANSWER, CLARIFY, REFUSE)


_SPELLINGS = {
    "answer": ANSWER, "sql": ANSWER, "query": ANSWER, "normal": ANSWER,
    "clarify": CLARIFY, "clarification": CLARIFY, "vague": CLARIFY, "ambiguous": CLARIFY,
    "refuse": REFUSE, "refusal": REFUSE, "unsafe": REFUSE, "attack": REFUSE,
}


def parse_type(value) -> str | None:
    """The type a value stands for (a blank one is ``answer``), or None when it is not one of the known spellings."""
    key = re.sub(r"[\s_-]+", "", str(value or "").lower())
    return ANSWER if not key else _SPELLINGS.get(key)


def is_declining(value) -> bool:
    """True for a type where the assistant should return no SQL: ``clarify`` or ``refuse``."""
    return parse_type(value) in (CLARIFY, REFUSE)
