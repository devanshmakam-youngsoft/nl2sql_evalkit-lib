"""Reading a query: does it parse, is it read-only, and which tables, columns and joins does it use."""
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TOKEN = re.compile(r"<Token[^>]*>")             # how the parser names the end of the text

# Anything that changes data or the database, wherever it sits in the statement (a data-changing CTE counts).
_WRITES = tuple(
    getattr(exp, name) for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge", "Command", "TruncateTable", "Grant", "Revoke",
        "Into", "Lock", "Set", "Use", "Copy", "LoadData", "Transaction", "Commit", "Rollback",
    ) if hasattr(exp, name)
)
_WRITE_WORDS = {
    "Into": "creates a table (SELECT ... INTO)", "Lock": "locks rows (FOR UPDATE)", "Command": "runs a command",
    "TruncateTable": "truncates a table", "Set": "changes a setting",
}

# Functions that read files, run commands, wait or reach other servers.
_RISKY_FUNCTIONS = {
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import", "lo_export", "dblink", "dblink_exec",
    "load_file", "sleep", "benchmark", "xp_cmdshell", "openrowset", "opendatasource",
}


def parse_statements(sql: str, dialect: str) -> tuple[list[exp.Expression], str]:
    """The statements in ``sql`` read in ``dialect``, and an empty string; or no statements and why it does not parse."""
    try:
        statements = sqlglot.parse(sql, read=dialect, error_level=sqlglot.ErrorLevel.RAISE)
    except SqlglotError as error:
        return [], _describe(error)
    return [s for s in statements if s is not None], ""


def _describe(error: SqlglotError) -> str:
    """One line saying what is wrong and where."""
    details = getattr(error, "errors", None) or []
    if details and isinstance(details[0], dict) and details[0].get("description"):
        first = details[0]
        where = f" (line {first['line']}, column {first['col']}" + (f", near '{first['highlight']}'" if first.get("highlight") else "") + ")" \
            if first.get("line") else ""
        description = _TOKEN.sub("the end of the query", _ANSI.sub("", str(first["description"]).strip().rstrip(".")))
        return description + where
    return _ANSI.sub("", str(error)).splitlines()[0][:200]


def read_only_problem(statements: list[exp.Expression]) -> str:
    """Why the statements are not a plain read of data, or an empty string when they are one single query."""
    if len(statements) != 1:
        return f"it holds {len(statements)} statements; only one query is allowed"
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        return f"it is a {type(statement).__name__.upper()} statement, not a query"
    for node in statement.find_all(*_WRITES):
        kind = type(node).__name__
        return _WRITE_WORDS.get(kind) or f"it contains a {kind.upper()}"
    for node in statement.find_all(exp.Func):
        name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
        if name in _RISKY_FUNCTIONS:
            return f"it calls {name}(), which can read files, run commands or wait"
    return ""


def alias_map(statement: exp.Expression) -> dict[str, str]:
    """Each alias and each plain table name, mapped to the table's name."""
    names: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        if table.name:
            names[table.name.lower()] = table.name.lower()
            if table.alias:
                names[table.alias.lower()] = table.name.lower()
    return names


def tables_used(statements: list[exp.Expression]) -> list[str]:
    """The tables read, lower-cased and without their schema, each once, in the order they appear. CTE names are not tables."""
    found: dict[str, None] = {}
    for statement in statements:
        ctes = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
        for table in statement.find_all(exp.Table):
            name = table.name.lower() if table.name else ""
            if name and name not in ctes:
                found.setdefault(name)
    return list(found)


def columns_used(statements: list[exp.Expression]) -> tuple[list[str], bool]:
    """The columns referenced as ``table.column`` (or just ``column`` when the query does not say which table), and
    whether the query selects ``*`` (so the columns it returns cannot be listed)."""
    found: dict[str, None] = {}
    star = False
    for statement in statements:
        aliases = alias_map(statement)
        for column in statement.find_all(exp.Column):
            if isinstance(column.this, exp.Star):
                star = True
                continue
            table = aliases.get(column.table.lower(), column.table.lower()) if column.table else ""
            found.setdefault(f"{table}.{column.name.lower()}" if table else column.name.lower())
        for select in statement.find_all(exp.Select):
            star = star or any(isinstance(item, exp.Star) for item in select.expressions)
    return list(found), star


def join_keys(statements: list[exp.Expression]) -> list[str]:
    """The pairs of columns the query joins on, each as ``a.x = b.y`` with the two sides in alphabetical order."""
    pairs: dict[str, None] = {}
    for statement in statements:
        aliases = alias_map(statement)

        def side(column: exp.Column) -> str:
            table = aliases.get(column.table.lower(), column.table.lower()) if column.table else ""
            return f"{table}.{column.name.lower()}" if table else column.name.lower()

        for join in statement.find_all(exp.Join):
            on = join.args.get("on")
            for equal in (on.find_all(exp.EQ) if on is not None else []):
                if isinstance(equal.left, exp.Column) and isinstance(equal.right, exp.Column):
                    pairs.setdefault(" = ".join(sorted((side(equal.left), side(equal.right)))))
            for using in join.args.get("using") or []:
                pairs.setdefault(f"using({using.name.lower()})")
        where = statement.find(exp.Where)
        for equal in (where.find_all(exp.EQ) if where is not None else []):      # an older style join: FROM a, b WHERE a.x = b.y
            if isinstance(equal.left, exp.Column) and isinstance(equal.right, exp.Column) and equal.left.table and equal.right.table \
                    and aliases.get(equal.left.table.lower()) != aliases.get(equal.right.table.lower()):
                pairs.setdefault(" = ".join(sorted((side(equal.left), side(equal.right)))))
    return list(pairs)
