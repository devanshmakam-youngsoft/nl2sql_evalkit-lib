"""The base errors. Every library error inherits from ``EvalKitError``, so callers can catch the base class to handle any of them."""


class EvalKitError(Exception):
    """Base class for all nl2sql_evalkit exceptions."""


class ConfigError(EvalKitError):
    """Invalid or conflicting value passed to serve() or Config."""


class InvalidInput(EvalKitError, ValueError):
    """A value someone sent cannot be used; the message says why in plain words."""


class NotFoundError(EvalKitError, KeyError):
    """Something that was asked for does not exist (or is no longer available)."""

    def __str__(self) -> str:
        return Exception.__str__(self)      # a KeyError would put quotes around the message


class TooLargeError(EvalKitError):
    """An uploaded file is bigger than allowed."""
