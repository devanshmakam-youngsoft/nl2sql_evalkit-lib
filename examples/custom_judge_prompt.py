"""Keep the AI judge but change how it scores: your own rubric, your own model, your own wording for the findings."""
import nl2sql_evalkit


def finance_assistant(question: str) -> str:
    return "SELECT month, revenue FROM v_monthly_revenue WHERE year = 2025 ORDER BY month"


# Only describe HOW to score. nl2sql_evalkit adds the reply format (the JSON with sql_marks, sql_comment and suggestion) itself.
FINANCE_RUBRIC = """You review SQL written by an assistant for a finance team.
You receive the question, what the test case expects, the assistant's SQL and the results of the checks already run.

sql_marks (0-10):
  10 = answers the question exactly, reading from the reporting views (names starting with v_).
  7-9 = right, with a small flaw such as an unneeded column or an unclear alias.
  4-6 = partly right, or right but reads a raw table where a reporting view exists.
  0-3 = wrong figures, a missing date filter, or a query that would double count through a join.
Money is summed per currency: a query that adds amounts in different currencies together gets at most 3.
suggestion: one change to the SQL, starting with a verb."""

# What the AI-written findings of a run should look at. The reply format is added for you here too.
SUMMARY_FOCUS = """You are reviewing one test run of a finance reporting assistant for the finance lead.
Point out which kinds of questions went worst and what to change in the instructions the assistant is given. Mention
queries that read raw tables instead of the reporting views. Plain language."""


if __name__ == "__main__":
    nl2sql_evalkit.serve(
        finance_assistant,
        dialect="postgres",
        judge_model="openai/gpt-4o-mini",      # any LiteLLM model: "groq/...", "gemini/...", "ollama/llama3", ...
        judge_prompt=FINANCE_RUBRIC,
        summary_prompt=SUMMARY_FOCUS,
    )
