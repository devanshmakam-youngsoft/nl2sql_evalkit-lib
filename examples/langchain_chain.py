"""A LangChain chain that writes SQL. Steps work inside runnables, including the branches LangChain runs in parallel threads.
The chain returns the SQL; it does not run it."""
from langchain_core.runnables import RunnableLambda, RunnableParallel

import nl2sql_evalkit

SCHEMA = {
    "customers": "customers(id, name, region)",
    "orders": "orders(id, customer_id, amount, status, created_at)",
}


@nl2sql_evalkit.step("rewrite")
def rewrite(question: str) -> str:
    return question.lower().replace("?", "")


def tables_by_name(query: str) -> list[str]:
    with nl2sql_evalkit.step("name_match"):
        return [name for name in SCHEMA if name.rstrip("s") in query]


def tables_by_column(query: str) -> list[str]:
    with nl2sql_evalkit.step("column_match"):
        return [name for name, text in SCHEMA.items() if any(word in text for word in query.split() if len(word) > 3)]


def merge(results: dict) -> list[str]:
    """Join what the parallel lookups found: these are the tables the model is shown."""
    with nl2sql_evalkit.step("schema_lookup"):
        return list(dict.fromkeys(results["by_name"] + results["by_column"])) or ["orders"]


def write_sql(tables: list[str]) -> str:
    with nl2sql_evalkit.step("llm"):
        return f"SELECT COUNT(*) FROM {tables[0]}"


chain = (
    RunnableLambda(rewrite)
    | RunnableParallel(by_name=RunnableLambda(tables_by_name), by_column=RunnableLambda(tables_by_column))
    | RunnableLambda(merge)
    | RunnableLambda(write_sql)
)


def pipeline(question: str) -> str:
    return chain.invoke(question)


if __name__ == "__main__":
    nl2sql_evalkit.serve(pipeline, dialect="postgres")
