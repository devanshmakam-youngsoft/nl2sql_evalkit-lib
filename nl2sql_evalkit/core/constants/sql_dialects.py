"""The SQL dialects the checks can read, and the other names people use for them."""

DEFAULT_DIALECT = "postgres"


DIALECTS = ("postgres", "mysql", "tsql", "sqlite")


_NAMES = {
    "postgres": "postgres", "postgresql": "postgres", "pg": "postgres",
    "mysql": "mysql", "mariadb": "mysql",
    "tsql": "tsql", "sqlserver": "tsql", "mssql": "tsql", "t-sql": "tsql",
    "sqlite": "sqlite",
}


def parse_dialect(value) -> str | None:
    """The dialect a name stands for (``postgresql`` is ``postgres``, ``sqlserver`` is ``tsql``...), or None when unknown."""
    return _NAMES.get(str(value or "").strip().lower().replace(" ", "").replace("_", ""))
