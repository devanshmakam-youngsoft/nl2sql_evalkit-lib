"""The evaluation entry point: run `python eval_entry.py` when you want to evaluate. Production never runs this file."""
import nl2sql_evalkit

from shared_pipeline import answer_question

if __name__ == "__main__":
    nl2sql_evalkit.serve(answer_question, port=8002, require_login=False)
