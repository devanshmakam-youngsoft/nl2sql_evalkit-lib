"""An agent that loops: the model asks for a tool, gets the result, and decides again until it can write the SQL.
The tools only read the schema; the SQL the agent writes is returned, never run."""
import nl2sql_evalkit

TABLES = {
    "orders": "orders(id, customer_id, amount, status)",
    "customers": "customers(id, name, region)",
}
MAX_TURNS = 5


def describe_table(name: str) -> str:
    return TABLES.get(name, f"{name} does not exist")


def list_tables(_: str) -> str:
    return ", ".join(TABLES)


TOOLS = {"describe_table": describe_table, "list_tables": list_tables}


def model(question: str, results: list[str]) -> dict:
    """Stand-in for the LLM call: asks for the tools it needs, then writes the SQL from what they returned."""
    if not results:
        return {"tool": "list_tables", "argument": ""}
    if len(results) == 1:
        return {"tool": "describe_table", "argument": "orders"}
    return {"sql": "SELECT status, SUM(amount) FROM orders GROUP BY status"}


def sql_agent(question: str) -> str:
    results: list[str] = []
    tools_used: list[str] = []
    for _ in range(MAX_TURNS):
        with nl2sql_evalkit.step("llm"):                      # runs once per loop: its times are added up
            decision = model(question, results)
        if "sql" in decision:
            return decision["sql"]
        with nl2sql_evalkit.step(decision["tool"]):           # one step per tool, named after the tool
            result = TOOLS[decision["tool"]](decision["argument"])
        results.append(result)
        tools_used.append(decision["tool"])
        nl2sql_evalkit.note("tools_used", ", ".join(tools_used))     # shown next to the question in the results
    return "Sorry, I could not finish that."


if __name__ == "__main__":
    nl2sql_evalkit.serve(sql_agent, dialect="postgres")
