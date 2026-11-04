"""The schema a step looked at, as plain readable text."""
from nl2sql_evalkit.services.evaluation.step_recorder.limits import clip_schema, text_of


def _columns_of(value) -> str:
    """``["id", "name"]`` or ``{"id": "int", "name": "text"}`` as ``id, name`` / ``id int, name text``."""
    if isinstance(value, dict):
        return ", ".join(f"{name} {kind}".strip() for name, kind in value.items())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_column_name(item) for item in value)
    return text_of(value)


def _column_name(item) -> str:
    if isinstance(item, dict):
        name = item.get("name") or item.get("column") or ""
        kind = item.get("type") or ""
        return f"{name} {kind}".strip() if name else text_of(item)
    return text_of(item)


def _table_line(item) -> str:
    """One table: a ready-made line, or ``{"table": "orders", "columns": [...]}`` as ``orders(id, amount)``."""
    if isinstance(item, dict):
        name = item.get("table") or item.get("name") or item.get("table_name")
        columns = item.get("columns")
        if name and columns is not None:
            return f"{name}({_columns_of(columns)})"
    return text_of(item)


def schema_text(value) -> str:
    """The schema a step looked at as readable text: a string as it is, a list as one line per item, and a dict of
    ``table -> columns`` as ``table(column, column)`` lines. ``None`` is no schema at all."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        lines = []
        for table, columns in value.items():
            lines.append(f"{table}({_columns_of(columns)})" if isinstance(columns, (list, tuple, set, dict)) else f"{table}: {text_of(columns)}")
        return "\n".join(lines)
    if isinstance(value, (list, tuple, set)):
        return "\n".join(_table_line(item) for item in value)
    return text_of(value)


def joined_schema(steps: list[dict]) -> str:
    """The schemas every step of a question declared, one after another and each once, cut to ``max_schema_chars``.
    Empty when no step declared one."""
    seen: dict[str, None] = {}
    for item in steps:
        text = str(item.get("schema") or "").strip()
        if text:
            seen.setdefault(text)
    return clip_schema("\n\n".join(seen))
