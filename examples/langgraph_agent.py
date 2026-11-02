"""A LangGraph app that writes SQL. Steps are recorded from inside nodes, whichever way you place them.
The graph returns the SQL; it does not run it."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import nl2sql_evalkit

SCHEMA = {
    "customers": "customers(id, name, region)",
    "orders": "orders(id, customer_id, amount, status, created_at)",
}


class State(TypedDict, total=False):
    question: str
    query: str
    tables: str
    sql: str


# 1. A node that calls a decorated function: the decorator records the call wherever it is made from.
@nl2sql_evalkit.step("rewrite")
def rewrite(question: str) -> str:
    return question.lower().replace("?", "")


def rewrite_node(state: State) -> dict:
    return {"query": rewrite(state["question"])}


# 2. A node with a `with` block inside it: use this when only part of the node should be timed.
def schema_node(state: State) -> dict:
    with nl2sql_evalkit.step("schema_lookup"):
        names = [name for name in SCHEMA if name.rstrip("s") in state["query"]] or ["orders"]
    return {"tables": ", ".join(SCHEMA[name] for name in names)}


# 3. A decorator on the node itself.
@nl2sql_evalkit.step("llm")
def sql_node(state: State) -> dict:
    table = state["tables"].split("(")[0]
    return {"sql": f"SELECT COUNT(*) FROM {table}"}


graph = StateGraph(State)
graph.add_node("rewrite", rewrite_node)
graph.add_node("schema", schema_node)
graph.add_node("write_sql", sql_node)
graph.add_edge(START, "rewrite")
graph.add_edge("rewrite", "schema")
graph.add_edge("schema", "write_sql")
graph.add_edge("write_sql", END)
app = graph.compile()


def pipeline(question: str) -> str:
    return app.invoke({"question": question})["sql"]


if __name__ == "__main__":
    nl2sql_evalkit.serve(pipeline, dialect="postgres")
