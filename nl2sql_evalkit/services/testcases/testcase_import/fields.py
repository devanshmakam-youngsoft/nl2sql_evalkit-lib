"""The fields of a test case row and the header names recognised for each."""


MAX_ROWS = 20_000


MAX_BYTES = 10 * 1024 * 1024


FIELDS = ("chat_id", "turn_no", "type", "question", "expected_sql", "expected_tables", "expected_columns", "groups")


FIELD_LABELS = {
    "chat_id": "Chat ID",
    "turn_no": "Turn number",
    "type": "Type",
    "question": "Question",
    "expected_sql": "Expected SQL",
    "expected_tables": "Expected tables",
    "expected_columns": "Expected columns",
    "groups": "Groups",
}


# Header names we recognise for each field, compared after lower-casing and turning punctuation into "_".
ALIASES: dict[str, tuple[str, ...]] = {
    "chat_id": ("chat_id", "chat", "chatid", "conversation_id", "conversation", "session_id", "session", "thread_id", "thread"),
    "turn_no": ("turn_no", "turn", "turn_number", "turn_num", "turnno", "step", "message_no"),
    "type": ("type", "question_type", "category", "kind"),
    "question": ("question", "user_query", "user_question", "natural_language_question", "prompt", "input", "user_input", "utterance"),
    "expected_sql": ("expected_sql", "gold_sql", "sql", "expected_query", "gold_query", "reference_sql", "ground_truth_sql", "expected"),
    "expected_tables": ("expected_tables", "tables", "expected_table", "table", "gold_tables", "required_tables"),
    "expected_columns": ("expected_columns", "columns", "expected_column", "column", "gold_columns", "required_columns"),
    "groups": ("groups", "group", "tags", "tag", "labels", "label"),
}
