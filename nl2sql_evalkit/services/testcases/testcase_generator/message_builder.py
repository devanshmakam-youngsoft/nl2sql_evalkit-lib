"""Putting the rules, the tables and the questions already written into the messages sent to the model."""
from __future__ import annotations

from nl2sql_evalkit.prompts.testcase_generator import CATEGORY_PROMPTS, common_rules
from nl2sql_evalkit.services.testcases.testcase_generator.planning import Task

MAX_OTHER_TABLES = 40


def system_prompt(category: str, turns: int) -> str:
    """Return the rules every question must follow plus the instructions for one category.

    ``turns`` is filled into the category's instructions (it matters for conversations).
    """
    return common_rules + "\n\n" + CATEGORY_PROMPTS[category].replace("{turns}", str(turns))


def build_messages(task: Task, turns: int, avoid: list[str], dialect: str) -> list[dict]:
    """The conversation sent to the model for one task: the rules, the tables, and what is already written."""
    user = f"SQL dialect: {dialect}\n\nTables:\n{task.schema.describe(task.tables)}"
    others = [name for name in task.schema.tables if name not in task.tables]
    if others:
        user += "\n\nOther tables in the database (do not use them): " + ", ".join(others[:MAX_OTHER_TABLES])
    if avoid:
        user += "\n\nQuestions already written (do not repeat or closely resemble them):\n" + "\n".join(f"- {q}" for q in avoid[-12:])
    return [{"role": "system", "content": system_prompt(task.category, turns)}, {"role": "user", "content": user}]
