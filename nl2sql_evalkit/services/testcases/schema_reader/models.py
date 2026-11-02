"""A database schema as read from CREATE TABLE statements."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    """One column of a table."""

    name: str
    type: str = ""
    primary_key: bool = False
    comment: str = ""


@dataclass
class ForeignKey:
    """A foreign key: columns of this table that point at columns of another table."""

    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    """One table: its columns and the foreign keys declared on it."""

    name: str
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    def column_names(self) -> list[str]:
        """The column names, in the order the table declares them."""
        return [c.name for c in self.columns]


@dataclass
class ReadSchema:
    """All the tables read from one uploaded file. Table and column names are lower-cased."""

    name: str                                   # the file name shown to people
    dialect: str
    tables: dict[str, Table] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)      # the start of each statement that could not be read

    def key_pairs(self, *, inferred: bool = False) -> set[frozenset[str]]:
        """The pairs of columns tables are joined on, each as ``{"orders.customer_id", "customers.id"}``.

        These are the declared foreign keys. With ``inferred`` and no declared key at all, a column named ``<table>_id``
        (or ``<table>s_id``) is taken to point at that table's ``id``, which is how most schemas without foreign keys are written.
        """
        pairs: set[frozenset[str]] = set()
        for table in self.tables.values():
            for key in table.foreign_keys:
                if key.ref_table not in self.tables:
                    continue
                for column, ref in zip(key.columns, key.ref_columns or ["id"] * len(key.columns)):
                    pairs.add(frozenset({f"{table.name}.{column}", f"{key.ref_table}.{ref}"}))
        if pairs or not inferred:
            return pairs
        for table in self.tables.values():
            for column in table.column_names():
                stem = column[:-3] if column.endswith("_id") else ""
                target = next((t for t in (stem, stem + "s", stem + "es") if stem and t in self.tables and t != table.name), None)
                if target and "id" in self.tables[target].column_names():
                    pairs.add(frozenset({f"{table.name}.{column}", f"{target}.id"}))
        return pairs

    def relations(self, *, inferred: bool = True) -> dict[str, set[str]]:
        """For each table, the tables it can be joined to through a key (in either direction)."""
        related: dict[str, set[str]] = {name: set() for name in self.tables}
        for pair in self.key_pairs(inferred=inferred):
            left, right = (side.split(".")[0] for side in pair)
            if left != right:
                related[left].add(right)
                related[right].add(left)
        return related

    def describe(self, names: list[str]) -> str:
        """The given tables as compact text for the model: columns with their types, keys and comments, then the keys between them."""
        lines = []
        for name in names:
            table = self.tables[name]
            parts = []
            for column in table.columns:
                text = f"{column.name} {column.type}".strip()
                if column.primary_key:
                    text += " PRIMARY KEY"
                references = [f"{key.ref_table}.{ref}" for key in table.foreign_keys
                              for col, ref in zip(key.columns, key.ref_columns or ["id"] * len(key.columns)) if col == column.name]
                if references:
                    text += " -> " + ", ".join(references)
                if column.comment:
                    text += f"  /* {column.comment} */"
                parts.append(text)
            lines.append(f"{name}({', '.join(parts)})")
        return "\n".join(lines)
