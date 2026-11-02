"""An assistant that does not always answer with SQL: it asks when a question is vague and refuses what it should not do.

Test cases of type `clarify` and `refuse` expect a message and no SQL; a reply that contains SQL scores 0 for them."""
import nl2sql_evalkit

VAGUE_WORDS = ("best", "top", "good", "recent")
UNSAFE_WORDS = ("delete", "drop", "update", "remove", "truncate")


def classify(question: str) -> str:
    text = question.lower()
    if any(word in text for word in UNSAFE_WORDS):
        return "unsafe"
    if any(word in text for word in VAGUE_WORDS):
        return "vague"
    return "clear"


def sql_assistant(question: str) -> str:
    with nl2sql_evalkit.step("triage"):
        kind = classify(question)
    nl2sql_evalkit.note("triage", kind)                         # shown next to the question in the results

    if kind == "unsafe":
        return "I can only read data, so I cannot change or delete anything."
    if kind == "vague":
        return "Which measure should I use: revenue, or the number of orders?"
    with nl2sql_evalkit.step("llm"):
        return "SELECT status, COUNT(*) FROM orders GROUP BY status"


if __name__ == "__main__":
    nl2sql_evalkit.serve(sql_assistant, dialect="postgres")
