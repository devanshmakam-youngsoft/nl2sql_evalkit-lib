"""Library configuration: one small file per group of options, assembled into ``Config``."""
from nl2sql_evalkit.core.config.dotenv import load_dotenv
from nl2sql_evalkit.core.config.settings import Config

__all__ = ["Config", "load_dotenv"]
