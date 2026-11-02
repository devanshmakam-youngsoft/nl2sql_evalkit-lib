"""Errors raised by the AI judge."""
from nl2sql_evalkit.core.exceptions.base import RagevalError


class JudgeError(RagevalError):
    """LLM judge failed to return a valid response after all retries."""
