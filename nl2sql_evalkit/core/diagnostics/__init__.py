"""Log files and plain-language problem reports.

``configure_logging`` sets up ``<data folder>/logs/server.log``; ``EventLog`` writes one file per evaluation run or
generation job; ``Issue`` is a problem with a message for people and technical detail for whoever needs it.
"""
from nl2sql_evalkit.core.diagnostics.event_log import EventLog
from nl2sql_evalkit.core.diagnostics.issues import Issue
from nl2sql_evalkit.core.diagnostics.plain_language import explain
from nl2sql_evalkit.core.diagnostics.redaction import redact
from nl2sql_evalkit.core.diagnostics.setup import configure_logging

__all__ = ["EventLog", "Issue", "configure_logging", "explain", "redact"]
