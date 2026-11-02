"""What the test case generation endpoints receive and return."""

from nl2sql_evalkit.schemas.testcase_generator.requests import Approval, ItemEdit
from nl2sql_evalkit.schemas.testcase_generator.responses import (
    ApproveResult,
    BatchCancelling,
    BatchDetail,
    BatchDiscarded,
    BatchSummary,
    GeneratedItem,
    GenerationLimits,
    ItemRemoved,
)

__all__ = [
    "Approval", "ApproveResult", "BatchCancelling", "BatchDetail", "BatchDiscarded", "BatchSummary",
    "GeneratedItem", "GenerationLimits", "ItemEdit", "ItemRemoved"
]
