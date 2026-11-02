"""How the version to ship is chosen."""
from nl2sql_evalkit.core.config.base import Settings


class ScoringSettings(Settings):
    """The weights and limits used to recommend a version."""

    answer_weight: float = 0.6                  # share of answer_marks in the overall score
    material_weight: float = 0.4                # share of material_marks; 0 for systems without retrieval
    recommendation_tolerance: float = 0.25      # versions this close to the best overall score count as tied
    recommendation_min_quality: float = 5.0     # below this overall score (0-10) nothing is recommended
    max_response_time: float | None = None      # seconds; slower versions are not recommended
