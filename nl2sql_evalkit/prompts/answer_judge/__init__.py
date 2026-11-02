"""Every prompt the judge uses, one file each, each exporting one named variable."""
from nl2sql_evalkit.prompts.answer_judge.grader import grader_format, grader_prompt
from nl2sql_evalkit.prompts.answer_judge.run_summary import run_summary_format, run_summary_prompt
from nl2sql_evalkit.prompts.answer_judge.source_check import source_check_prompt

__all__ = [
    "grader_format", "grader_prompt", "run_summary_format", "run_summary_prompt", "source_check_prompt"
]
