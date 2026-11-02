"""Two versions of one assistant. Change a setting, restart, run the same test cases again as the next version."""
import os

import nl2sql_evalkit

SCHEMA = {
    "customers": ["id", "name", "region"],
    "orders": ["id", "customer_id", "amount", "status", "created_at"],
}

# Version 1 shows the model only the table names. Version 2 also shows the columns:  WITH_COLUMNS=1 python versions_workflow.py
WITH_COLUMNS = os.environ.get("WITH_COLUMNS", "0") == "1"


def prompt_schema() -> str:
    """The schema text the model would be given."""
    if WITH_COLUMNS:
        return "\n".join(f"{table}({', '.join(columns)})" for table, columns in SCHEMA.items())
    return ", ".join(SCHEMA)


def write_sql(question: str, schema: str) -> str:
    """Stand-in for your LLM call. Without the columns it can only guess, so it selects everything."""
    if "(" in schema:
        return "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region"
    return "SELECT * FROM orders"


def assistant(question: str) -> str:
    with nl2sql_evalkit.step("schema_lookup"):
        schema = prompt_schema()
    with nl2sql_evalkit.step("llm"):
        return write_sql(question, schema)


if __name__ == "__main__":
    nl2sql_evalkit.serve(assistant, port=8002, require_login=False, dialect="postgres")
