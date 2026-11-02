"""A typical text-to-SQL pipeline: rewrite the question, pick the tables, write the SQL, check it. Each stage is a step, so
the dashboard shows where the time goes. The SQL is only returned, never run."""
import nl2sql_evalkit

SCHEMA = {
    "customers": "customers(id, name, region)",
    "orders": "orders(id, customer_id, amount, status, created_at)",
    "products": "products(id, title, price)",
}


def rewrite_question(question: str) -> str:
    """Stand-in for a question-rewriting LLM call."""
    return question.lower().replace("?", "")


def pick_tables(question: str) -> list[str]:
    """Stand-in for the lookup of the tables the question needs."""
    return [name for name in SCHEMA if name.rstrip("s") in question] or ["orders"]


def call_llm(question: str, tables: list[str]) -> str:
    """Stand-in for your SQL-writing LLM call."""
    if "how many" in question:
        return f"SELECT COUNT(*) FROM {tables[0]}"
    return f"SELECT * FROM {tables[0]}"


def text_to_sql(question: str) -> str:
    with nl2sql_evalkit.step("rewrite"):
        clean = rewrite_question(question)

    with nl2sql_evalkit.step("schema_lookup"):
        tables = pick_tables(clean)
    nl2sql_evalkit.note("tables_given", ", ".join(tables))     # shown next to the question in the results

    with nl2sql_evalkit.step("llm"):
        sql = call_llm(clean, tables)

    with nl2sql_evalkit.step("self_check"):                     # e.g. ask the model to review its own query
        return sql.rstrip(";")


if __name__ == "__main__":
    nl2sql_evalkit.serve(text_to_sql, dialect="postgres")
