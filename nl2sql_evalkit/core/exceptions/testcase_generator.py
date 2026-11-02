"""Errors raised while writing test cases from documents."""
from nl2sql_evalkit.core.exceptions.base import EvalKitError


class GenerationError(EvalKitError):
    """A question could not be written that follows every rule."""


class GenerationBusy(EvalKitError):
    """Another generation is already running."""
