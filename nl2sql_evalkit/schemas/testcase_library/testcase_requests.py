"""Request bodies for test cases."""
from pydantic import BaseModel


class TestCaseUpdate(BaseModel):
    """The fields to change when editing a test case; any field left out or null keeps its value."""

    chat_id: str | None = None          # cannot be empty
    turn_no: int | None = None          # position in the chat, 1 or higher
    question: str | None = None         # cannot be empty
    expected_sql: str | None = None     # the gold query
    expected_tables: str | None = None  # the tables the SQL must use, separated by commas
    expected_columns: str | None = None  # the columns the SQL must use, separated by commas (table.column or just column)
    reply_style: str | None = None      # how the written reply should read; when set, the reply is scored too
    type: str | None = None             # "answer", "clarify" or "refuse"


class TestCaseStatusUpdate(BaseModel):
    """The new status for one test case."""

    status: str  # "active" | "inactive"


class BulkStatusUpdate(BaseModel):
    """The test cases to activate or deactivate, and the status to give them."""

    tc_ids: list[str]
    status: str  # "active" | "inactive"


class TestCaseIds(BaseModel):
    """A list of test cases to act on together."""

    tc_ids: list[str]


class TestCaseGroups(BaseModel):
    """The complete set of groups a test case should carry."""

    group_ids: list[str]            # replaces the groups it has now; an empty list removes them all


class CreateTestCase(BaseModel):
    """A single test case to add to the library."""

    chat_id: str                    # the conversation this question belongs to; turns of one chat share it
    turn_no: int                    # position in the chat, starting at 1
    question: str
    expected_sql: str = ""          # the gold query
    type: str = "answer"            # what the assistant should do: "answer" (return SQL), "clarify" (ask back) or "refuse"
    expected_tables: str = ""       # the tables the SQL must use, separated by commas
    expected_columns: str = ""      # the columns the SQL must use, separated by commas (table.column or just column)
    reply_style: str = ""           # how the written reply should read, for example "Friendly, two sentences"; empty scores the SQL only
    group_id: str | None = None     # also put the test case in this group
    dataset_id: str | None = None  # backward-compat alias
