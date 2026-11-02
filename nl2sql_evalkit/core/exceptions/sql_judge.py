"""Errors raised by the AI judge."""
from nl2sql_evalkit.core.exceptions.base import EvalKitError


class JudgeError(EvalKitError):
    """LLM judge failed to return a valid response after all retries."""
