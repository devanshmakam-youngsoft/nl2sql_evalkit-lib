"""Your pipeline module. Production and the evaluation both import it, and it needs no changes for either."""
import nl2sql_evalkit

SCHEMA = {
    "customers": "customers(id, name, region)",
    "orders": "orders(id, customer_id, amount, status, created_at)",
}


def answer_question(question: str) -> str:
    # Outside an evaluation these do nothing, so they can stay in the code that ships.
    with nl2sql_evalkit.step("schema_lookup"):
        words = question.lower().replace("?", "")
        tables = [name for name in SCHEMA if name.rstrip("s") in words] or ["orders"]
    with nl2sql_evalkit.step("llm"):
        return f"SELECT COUNT(*) FROM {tables[0]}"
