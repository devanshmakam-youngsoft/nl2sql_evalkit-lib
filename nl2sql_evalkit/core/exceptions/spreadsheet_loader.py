"""Errors raised while reading a test case spreadsheet."""
from nl2sql_evalkit.core.exceptions.base import RagevalError


class DatasetError(RagevalError):
    """Dataset file is missing, unreadable, or fails column validation."""
