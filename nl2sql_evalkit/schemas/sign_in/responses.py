"""What the sign-in endpoints return."""
from nl2sql_evalkit.schemas.base import ApiResponse


class SignedInUser(ApiResponse):
    """Who is signed in."""

    username: str


class Acknowledged(ApiResponse):
    """A plain confirmation that an action was carried out."""

    ok: bool                        # always true
