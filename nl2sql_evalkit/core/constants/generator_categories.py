"""The kinds of question that can be written, and how they are labelled."""
from nl2sql_evalkit.core.constants.case_types import ANSWER, CLARIFY, REFUSE

# key -> label shown to people and used as the group each question is added to
CATEGORY_LABELS = {
    "simple": "Simple", "join": "Joins", "aggregate": "Aggregations", "nested": "Subqueries",
    "followup": "Follow-ups", "vague": "Vague", "unsafe": "Unsafe",
}
CATEGORIES = tuple(CATEGORY_LABELS)

# what the assistant should do with the questions of a category; every other category is for it to answer with SQL
_DECLINING = {"vague": CLARIFY, "unsafe": REFUSE}

MIN_TURNS, MAX_TURNS, DEFAULT_TURNS = 2, 4, 3
DEFAULT_PER_CATEGORY = 3


def case_type_of(category: str) -> str:
    """The test case type the questions of a category get: ``clarify`` for vague ones, ``refuse`` for unsafe ones, else ``answer``."""
    return _DECLINING.get(category, ANSWER)
