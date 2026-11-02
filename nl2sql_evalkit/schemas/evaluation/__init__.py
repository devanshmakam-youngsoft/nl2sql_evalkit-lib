"""What the run, version and recommendation endpoints receive and return."""

from nl2sql_evalkit.schemas.evaluation.requests import SelectionBody
from nl2sql_evalkit.schemas.evaluation.responses import (
    Recommendation,
    RunArchiveState,
    RunDeleted,
    RunIssues,
    RunPreview,
    RunSnapshot,
    StopRequested,
    VersionDetail,
    VersionSummary,
)

__all__ = [
    "Recommendation", "RunArchiveState", "RunDeleted", "RunIssues", "RunPreview", "RunSnapshot",
    "SelectionBody", "StopRequested", "VersionDetail", "VersionSummary"
]
