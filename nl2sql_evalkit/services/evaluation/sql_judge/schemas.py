"""The shapes of what the judge returns."""
from pydantic import BaseModel, Field, field_validator

CAUSES = ("schema_lookup", "sql", "both", "none")


def parse_cause(value) -> str:
    """The cause of a wrong query as one of ``CAUSES``: ``schema_lookup`` (the schema the assistant looked at missed a table or
    column that was needed), ``sql`` (the SQL went wrong with the schema it had), ``both`` or ``none``. Anything else, such
    as a missing value or a different spelling the model came up with, reads as ``none``."""
    word = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if word in CAUSES:
        return word
    if word in ("lookup", "schema", "retrieval"):
        return "schema_lookup"
    return "none"


class ReplyGrade(BaseModel):
    """The judge's mark for one written reply (out of 10): how well it follows the requested style, why, and what to change."""

    reply_marks: int = Field(ge=0, le=10)
    reply_comment: str
    suggestion: str = ""


class SqlGrade(BaseModel):
    """The judge's mark for one reply (out of 10), the reason, and what to change."""

    sql_marks: int = Field(ge=0, le=10)
    sql_comment: str
    suggestion: str = ""
    cause: str = "none"        # why the query is wrong: "schema_lookup", "sql", "both" or "none" (not wrong, or not known)

    @field_validator("cause", mode="before")
    @classmethod
    def _lenient_cause(cls, value) -> str:
        return parse_cause(value)
