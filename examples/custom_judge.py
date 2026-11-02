"""Replace the AI judge with your own function. It receives the question, the expected SQL, the assistant's reply and the
findings of the checks (``checks``), and returns the SQL score (0 to 10) with an optional comment and suggestion.

A reply that has no SQL, does not parse or is not read-only is scored 0 before your function is called."""
import nl2sql_evalkit


def my_assistant(question: str) -> str:
    return "SELECT region, SUM(amount) FROM orders GROUP BY region"


def same_as_expected(question: str, expected_sql: str, reply: str, checks: dict) -> dict:
    """The simplest judge: full marks when the query is the expected one, ignoring case, spaces and a final semicolon."""
    def tidy(sql: str) -> str:
        return " ".join(sql.lower().replace(";", " ").split())

    same = bool(expected_sql) and tidy(expected_sql) == tidy(reply)
    return {
        "sql_marks": 10 if same else 3,
        "sql_comment": "The same as the expected SQL." if same else "Different from the expected SQL.",
        "suggestion": "" if same else "Compare the query with the expected SQL, line by line.",
    }


def no_select_star(question: str, expected_sql: str, reply: str, checks: dict) -> dict:
    """Uses the findings of the checks: a query that selects every column (``*``) is marked down."""
    if checks["star"]:
        return {"sql_marks": 4, "sql_comment": "Selects every column with *.", "suggestion": "List only the columns the question needs."}
    return {"sql_marks": 10, "sql_comment": "Lists its columns."}


def strict_about_joins(question: str, expected_sql: str, reply: str, checks: dict) -> dict:
    """Also uses the checks: ``joins_match`` is None without an expected SQL, True when the joins are the expected ones."""
    if checks["joins_match"] is None:
        return {"sql_marks": 8, "sql_comment": "No expected SQL to compare the joins with."}
    if checks["joins_match"]:
        return {"sql_marks": 10, "sql_comment": "The joins are the expected ones."}
    return {
        "sql_marks": 4,
        "sql_comment": f"The joins differ. Missing: {', '.join(checks['joins_missing']) or 'none'}.",
        "suggestion": "Join on the keys of the expected SQL.",
    }


if __name__ == "__main__":
    nl2sql_evalkit.serve(my_assistant, judge_fn=strict_about_joins)
