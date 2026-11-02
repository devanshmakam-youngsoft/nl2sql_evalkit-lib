"""Errors raised while reading an uploaded schema file."""
from nl2sql_evalkit.core.exceptions.base import EvalKitError


class SchemaError(EvalKitError):
    """An uploaded schema file could not be read (unsupported type, empty, or no CREATE TABLE statements in it)."""
