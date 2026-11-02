"""Running nl2sql_evalkit for a team: accounts, where things are kept, the SQL dialect, models, and how the recommendation decides."""
import os

import nl2sql_evalkit


def answer_question(question: str) -> str:
    return "SELECT region, COUNT(*) FROM customers GROUP BY region"


if __name__ == "__main__":
    nl2sql_evalkit.serve(
        answer_question,
        # --- where it runs and where things are kept ---
        port=8002,
        dialect="postgres",                      # the SQL your assistant writes: "postgres", "mysql", "sqlite" or "tsql"
        data_dir="evals",                        # store.json (results: copy it to back up), logs/ and uploads/ live here
        # --- who may open it ---
        users="alice:pw-for-alice,bob:pw-for-bob",
        secret=os.environ.get("EVAL_SECRET", "change-me"),   # fixed, so people stay signed in across restarts
        # --- models ---
        judge_model="openai/gpt-4o-mini",
        generator_model="ollama/llama3",         # writes test cases from schema files: the schema stays on this machine
        # --- how the recommendation decides ---
        sql_weight=0.7,                         # the SQL score counts for 70%...
        schema_weight=0.3,                      # ...and the tables-and-columns score for 30%
        recommendation_tolerance=0.2,            # versions this close to the best are tied: the fastest wins
        max_response_time=8.0,                   # versions slower than this (seconds) are never recommended
        show_guide=True,                         # the Help page
        open_browser=False,
    )
