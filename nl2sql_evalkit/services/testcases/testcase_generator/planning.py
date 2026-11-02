"""Deciding which tables each question is written from."""
from __future__ import annotations

from dataclasses import dataclass, field

from nl2sql_evalkit.services.testcases.schema_reader import ReadSchema


@dataclass
class Task:
    """One question (or conversation) to write."""

    category: str
    file: str                  # the uploaded file the tables come from
    tables: list[str]          # the tables the question is written from, in the order they are shown
    number: int                # 1-based within its category
    schema: ReadSchema = field(repr=False, compare=False, default=None)    # type: ignore[assignment]


def spread_order(n: int) -> list[int]:
    """0..n-1 ordered so that any prefix is spread across the whole range (van der Corput order):
    n=8 gives 0, 4, 2, 6, 1, 5, 3, 7. Taking tables in this order samples a schema evenly."""
    def reverse_bits(i: int) -> float:
        value, base = 0.0, 0.5
        while i:
            value += (i & 1) * base
            i >>= 1
            base /= 2
        return value

    return sorted(range(n), key=lambda i: (reverse_bits(i), i))


class _Picker:
    """Hands out the tables of one schema in a spread order, so any few questions sample the whole schema,
    wrapping round when it runs out."""

    def __init__(self, schema: ReadSchema):
        self.schema = schema
        self.names = list(schema.tables)
        self.order = spread_order(len(self.names))
        self.related = schema.relations()
        self.pointer = 0

    def _next(self, only: set[str] | None = None) -> str | None:
        for _ in range(len(self.order)):
            name = self.names[self.order[self.pointer % len(self.order)]]
            self.pointer += 1
            if only is None or name in only:
                return name
        return None

    def take(self, size: int, *, joined: bool, index: int) -> list[str]:
        """``size`` tables. With ``joined`` they are linked by keys (as many as can be linked); without, any tables."""
        connected = {n for n, links in self.related.items() if links}
        start = self._next(connected if joined and connected else None)
        if start is None:
            return []
        chosen = [start]
        while len(chosen) < size:
            if joined:
                neighbours = sorted({n for c in chosen for n in self.related.get(c, ())} - set(chosen))
                if not neighbours:
                    break
                chosen.append(neighbours[index % len(neighbours)])
            else:
                extra = self._next()
                if extra is None or extra in chosen:
                    break
                chosen.append(extra)
        return chosen


# how many tables a question of each category is written from, by position within the category (the pattern repeats)
_SIZES = {
    "simple": (1,), "nested": (1, 2), "aggregate": (1, 2), "join": (2, 2, 3), "followup": (2, 1), "vague": (1, 2), "unsafe": (1,),
}
_JOINED = {"join", "followup"}


def plan_tasks(schemas: list[ReadSchema], categories: list[str], per_category: int) -> list[Task]:
    """``per_category`` questions in each category, shared out across the schemas in turn.

    A category that cannot be written from a schema (a join question when no two of its tables are linked by a key) gets no
    question from it, so fewer tasks than asked for can come back.
    """
    pickers = {s.name: _Picker(s) for s in schemas}
    tasks: list[Task] = []
    for category in categories:
        sizes = _SIZES[category]
        for i in range(per_category):
            schema = schemas[i % len(schemas)]
            picker = pickers[schema.name]
            size = sizes[i % len(sizes)]
            joined = category in _JOINED or (category == "aggregate" and size == 2)
            tables = picker.take(size, joined=joined, index=i)
            if category == "join" and len(tables) < 2:
                continue
            if tables:
                tasks.append(Task(category, schema.name, tables, i + 1, schema))
    return tasks
