"""``Config``: every option of the library, assembled from the settings groups in this package."""
from nl2sql_evalkit.core.config.access import AccessSettings
from nl2sql_evalkit.core.config.datasets import DatasetSettings
from nl2sql_evalkit.core.config.function_adapter import FunctionAdapterSettings
from nl2sql_evalkit.core.config.generation import GenerationSettings
from nl2sql_evalkit.core.config.judge import JudgeSettings
from nl2sql_evalkit.core.config.logs import LogSettings
from nl2sql_evalkit.core.config.recording import RecordingSettings
from nl2sql_evalkit.core.config.scoring import ScoringSettings
from nl2sql_evalkit.core.config.server import ServerSettings
from nl2sql_evalkit.core.config.sql import SqlSettings


class Config(
    ServerSettings,
    LogSettings,
    AccessSettings,
    RecordingSettings,
    JudgeSettings,
    GenerationSettings,
    ScoringSettings,
    SqlSettings,
    FunctionAdapterSettings,
    DatasetSettings,
):
    """All options with their defaults. ``serve()`` fills it from its arguments."""
