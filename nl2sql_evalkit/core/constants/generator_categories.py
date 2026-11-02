"""The kinds of question that can be written, and how they are labelled."""

# key -> label shown to people and used as the group each question is added to
CATEGORY_LABELS = {"direct": "Direct", "indirect": "Indirect", "multipart": "Multi-part", "multiturn": "Multi-turn"}
CATEGORIES = tuple(CATEGORY_LABELS)

# every generated test case is one the assistant should answer
CASE_TYPE = "answer"

MIN_TURNS, MAX_TURNS, DEFAULT_TURNS = 2, 4, 3
DEFAULT_PER_CATEGORY = 3
