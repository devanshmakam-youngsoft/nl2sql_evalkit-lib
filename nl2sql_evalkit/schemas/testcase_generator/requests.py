"""Request bodies for writing test cases from schema files."""
from pydantic import BaseModel


class TurnText(BaseModel):
    """The reworded text of one turn of a generated item."""

    question: str                       # 12 to 400 characters
    expected_sql: str = ""              # 6 to 4000 characters; leave out for a vague or unsafe question, which has no SQL


class ItemEdit(BaseModel):
    """The reworded turns of one generated item, sent while reviewing a batch."""

    turns: list[TurnText]               # one per existing turn, in order; the number of turns cannot change


class Approval(BaseModel):
    """Which generated items to add to the library when a batch is approved."""

    item_ids: list[str] | None = None   # default: everything left in the batch
