"""Telling the SQL in what the assistant returned from a plain message."""
import re

_FENCED = re.compile(r"```(?:sql)?[ \t]*\n?(.*?)```", re.S | re.I)

# What a statement starts with. Only words that are rarely the first word of an English sentence count: a reply that
# starts with "Which customers do you mean?" is a message, one that starts with "SELECT" is SQL. A leading "(" and
# comments are allowed. "WITH" counts only in the shape of a CTE (``WITH name AS (``).
_STATEMENT = re.compile(
    r"^\s*(?:(?:--[^\n]*\n|/\*.*?\*/)\s*)*\(*\s*"
    r"(?:select\b|insert\b|update\b|delete\b|drop\b|create\b|alter\b|truncate\b|merge\b|grant\b|revoke\b|explain\b"
    r"|with\s+(?:recursive\s+)?[\w\"`\[\]]+\s*(?:\([^)]*\)\s*)?as\s*\()",
    re.I | re.S,
)


def split_reply(reply) -> tuple[str, str]:
    """Split a reply into ``(sql, message)``. A reply that is SQL has an empty message and the other way round.

    SQL inside a fenced block (```` ```sql ````) is taken out, and the rest of the reply is the message. Without a fence,
    the whole reply is SQL when it starts like a statement.
    """
    text = str(reply or "").strip()
    if not text:
        return "", ""
    fenced = _FENCED.search(text)
    if fenced and fenced.group(1).strip():
        return fenced.group(1).strip(), (text[:fenced.start()] + text[fenced.end():]).strip()
    if _STATEMENT.match(text):
        return text, ""
    return "", text
