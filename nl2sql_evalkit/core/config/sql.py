"""The SQL dialect the assistant's queries are read in."""
from nl2sql_evalkit.core.config.base import Settings
from nl2sql_evalkit.core.constants import DEFAULT_DIALECT


class SqlSettings(Settings):
    """Options for reading the SQL the assistant writes."""

    dialect: str = DEFAULT_DIALECT   # "postgres", "mysql", "tsql" (SQL Server) or "sqlite"
