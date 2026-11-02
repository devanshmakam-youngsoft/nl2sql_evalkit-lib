"""How the version to ship is chosen."""
from nl2sql_evalkit.core.config.base import Settings


class ScoringSettings(Settings):
    """The weights and limits used to recommend a version."""

    sql_weight: float = 0.6                  # share of sql_marks in the overall score
    schema_weight: float = 0.4                # share of schema_marks (tables and columns used)
    recommendation_tolerance: float = 0.25      # versions this close to the best overall score count as tied
    recommendation_min_quality: float = 5.0     # below this overall score (0-10) nothing is recommended
    max_response_time: float | None = None      # seconds; slower versions are not recommended
