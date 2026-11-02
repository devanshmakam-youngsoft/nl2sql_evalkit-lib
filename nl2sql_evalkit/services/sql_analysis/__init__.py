"""Reading a SQL query without running it: whether it parses, whether it only reads, and which tables, columns and joins it uses."""
from nl2sql_evalkit.services.sql_analysis.analysis import (
    alias_map,
    columns_used,
    join_keys,
    parse_statements,
    read_only_problem,
    tables_used,
)

__all__ = ["alias_map", "columns_used", "join_keys", "parse_statements", "read_only_problem", "tables_used"]
