"""The shapes of what the judge returns."""
from pydantic import BaseModel, Field


class SqlGrade(BaseModel):
    """The judge's mark for one reply (out of 10), the reason, and what to change."""

    sql_marks: int = Field(ge=0, le=10)
    sql_comment: str
    suggestion: str = ""
