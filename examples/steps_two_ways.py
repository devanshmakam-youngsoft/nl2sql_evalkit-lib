"""The same text-to-SQL pipeline recorded two ways: with `with` blocks, and with decorators. Both record the same two steps,
and both say which tables and columns the assistant looked at, so that is scored and shown with the result."""
import nl2sql_evalkit

SCHEMA = {
    "customers": "customers(id, name, region)",
    "orders": "orders(id, customer_id, amount, status, created_at)",
    "products": "products(id, title, price)",
}


def pick_tables(question: str) -> list[str]:
    """Stand-in for the part of your assistant that decides which tables the question needs."""
    words = question.lower().replace("?", "")
    return [name for name in SCHEMA if name.rstrip("s") in words] or ["orders"]


def write_sql(question: str, tables: str) -> str:
    """Stand-in for your LLM call."""
    return f"SELECT COUNT(*) FROM {tables.split('(')[0]}"


# Style 1: `with` blocks. You decide exactly where a step starts and ends.
def pipeline_with_blocks(question: str) -> str:
    with nl2sql_evalkit.step("schema_lookup") as s:
        tables = [SCHEMA[name] for name in pick_tables(question)]
        s.schema = tables                       # what the assistant looked at: a list, text or {"orders": ["id", ...]}
        nl2sql_evalkit.note("tables_given", ", ".join(tables))
    with nl2sql_evalkit.step("llm"):
        return write_sql(question, tables[0])


# Style 2: decorators. The inputs and the output of each function are recorded for you.
@nl2sql_evalkit.step("schema_lookup", schema=True)     # the return value is the schema the assistant looked at
def look_up_tables(question: str) -> str:
    return ", ".join(SCHEMA[name] for name in pick_tables(question))


@nl2sql_evalkit.step("llm")
def generate(question: str, tables: str) -> str:
    return write_sql(question, tables)


def pipeline_with_decorators(question: str) -> str:
    return generate(question, look_up_tables(question))


if __name__ == "__main__":
    nl2sql_evalkit.serve(pipeline_with_blocks, dialect="postgres")   # or pipeline_with_decorators
