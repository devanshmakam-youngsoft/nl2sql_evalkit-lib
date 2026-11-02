"""Reading CREATE TABLE statements (and the ALTER TABLE and COMMENT statements around them) into a schema."""
from __future__ import annotations

import re
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from nl2sql_evalkit.core.constants import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from nl2sql_evalkit.core.exceptions import SchemaError
from nl2sql_evalkit.services.testcases.schema_reader.models import (
    Column,
    ForeignKey,
    ReadSchema,
    Table,
)

# The statements that describe the schema. A dump that also holds data (INSERT, COPY ... FROM stdin) is read statement by
# statement, so what is not understood is skipped and what is is kept. A statement ends at a semicolon at the end of a line.
_STATEMENT = re.compile(
    r"\b(?:create\s+(?:or\s+replace\s+)?(?:(?:global\s+|local\s+)?temp(?:orary)?\s+|unlogged\s+)?table\b"
    r"|alter\s+table\b|comment\s+on\s+column\b)(?:(?!;[ \t]*(?:--[^\n]*)?(?:\r?\n|\Z)).)*;",
    re.I | re.S,
)


def read_schema(path: Path, name: str | None = None, dialect: str = "postgres") -> ReadSchema:
    """Read one uploaded file into a schema. Raises SchemaError with a message fit to show the user."""
    path = Path(path)
    name = name or path.name
    if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SchemaError(f"{name}: unsupported file type. {SUPPORTED_MESSAGE}")
    text = path.read_bytes().decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise SchemaError(f"{name} is empty.")

    schema = ReadSchema(name=name, dialect=dialect)
    later: list[exp.Expression] = []
    for match in _STATEMENT.finditer(text):
        sql = match.group(0)
        try:
            statement = sqlglot.parse_one(sql, read=dialect)
        except (SqlglotError, ValueError):
            schema.skipped.append(" ".join(sql.split())[:60])
            continue
        if isinstance(statement, exp.Create) and isinstance(statement.this, exp.Schema):
            _add_table(schema, statement.this, dialect)
        elif isinstance(statement, (exp.Alter, exp.Comment)):
            later.append(statement)
    for statement in later:
        _apply(schema, statement)
    if not schema.tables:
        raise SchemaError(f"{name} has no CREATE TABLE statements that could be read as {dialect}.")
    return schema


def _reference(node: exp.Reference) -> tuple[str, list[str]]:
    """The table and columns a REFERENCES clause points at."""
    target = node.this
    if isinstance(target, exp.Schema):
        return target.this.name.lower(), [i.name.lower() for i in target.expressions]
    return str(target.name).lower(), []


def _add_key(table: Table, key: ForeignKey) -> None:
    """Add a foreign key unless the table already has it (the same key can be declared inline and again by ALTER TABLE)."""
    if key not in table.foreign_keys:
        table.foreign_keys.append(key)


def _add_table(schema: ReadSchema, definition: exp.Schema, dialect: str) -> None:
    table = Table(name=definition.this.name.lower())
    for item in definition.expressions:
        if isinstance(item, exp.ColumnDef):
            column = Column(name=item.name.lower(), type=item.args["kind"].sql(dialect=dialect).lower() if item.args.get("kind") else "")
            for constraint in item.args.get("constraints") or []:
                kind = constraint.args.get("kind")
                if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                    column.primary_key = True
                elif isinstance(kind, exp.Reference):
                    ref_table, ref_columns = _reference(kind)
                    _add_key(table, ForeignKey([column.name], ref_table, ref_columns))
                elif isinstance(kind, exp.ForeignKey) and kind.args.get("reference"):
                    ref_table, ref_columns = _reference(kind.args["reference"])
                    _add_key(table, ForeignKey([column.name], ref_table, ref_columns))
                elif isinstance(kind, exp.CommentColumnConstraint):
                    column.comment = str(kind.this.name) if kind.this is not None else ""
            table.columns.append(column)
        elif isinstance(item, exp.PrimaryKey):
            keys = {i.name.lower() for i in item.expressions}
            for column in table.columns:
                column.primary_key = column.primary_key or column.name in keys
        else:
            for key in ([item] if isinstance(item, exp.ForeignKey) else item.find_all(exp.ForeignKey)):
                if key.args.get("reference"):
                    ref_table, ref_columns = _reference(key.args["reference"])
                    _add_key(table, ForeignKey([i.name.lower() for i in key.expressions], ref_table, ref_columns))
    schema.tables[table.name] = table


def _apply(schema: ReadSchema, statement: exp.Expression) -> None:
    """A foreign key added by ALTER TABLE, or a column comment, applied to a table already read."""
    if isinstance(statement, exp.Alter) and isinstance(statement.this, exp.Table):
        table = schema.tables.get(statement.this.name.lower())
        if table is None:
            return
        for key in statement.find_all(exp.ForeignKey):
            if key.args.get("reference"):
                ref_table, ref_columns = _reference(key.args["reference"])
                _add_key(table, ForeignKey([i.name.lower() for i in key.expressions], ref_table, ref_columns))
    elif isinstance(statement, exp.Comment) and isinstance(statement.this, exp.Column) and statement.this.table:
        table = schema.tables.get(statement.this.table.lower())
        text = statement.args.get("expression")
        if table is not None and text is not None:
            for column in table.columns:
                if column.name == statement.this.name.lower():
                    column.comment = str(text.name)
