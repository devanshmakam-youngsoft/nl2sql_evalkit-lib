"""The rules a written question must follow. The model is asked to follow them; this is what makes sure it did.

``validate`` returns the cleaned turns, or the reason the reply was rejected, worded so it can be handed back to the
model for another attempt. The SQL is read, never run, and the tables and columns of the test case are taken from it,
so they cannot be invented.
"""
from __future__ import annotations

import re

from sqlglot import exp

from nl2sql_evalkit.services.sql_analysis import (
    alias_map,
    join_keys,
    parse_statements,
    read_only_problem,
    tables_used,
)
from nl2sql_evalkit.services.testcases.testcase_generator.planning import Task
from nl2sql_evalkit.utils import tokenize

SIMILARITY_LIMIT = 0.75        # two questions this alike count as the same question
RESTATES_LIMIT = 0.6           # a follow-up that repeats this much of the earlier questions is not a follow-up
MIN_DEPENDS_CHARS = 8
MIN_NOTE_CHARS = 8

# words a person asking a data question does not use: they do not know how the data is stored
_TECHNICAL = re.compile(r"\b(sql|schema|tables?|columns?|database|group\s+by|order\s+by|inner\s+join|left\s+join|where\s+clause)\b", re.I)

# how people refer back in a conversation: pronouns, "the same", "the other one". Words that also turn up in
# standalone questions ("above $500", "one of", "the first day") are deliberately not here.
_REFERS_BACK = re.compile(
    r"\b(it|its|it's|they|them|their|theirs|that|those|these|there|then|same|former|latter|previous|earlier|"
    r"instead|otherwise|also|too|as well|the other|the others|that one|this one|this|such|both|either|another|else|rest|mentioned|"
    r"only|just|now|sort|rank|limit|add|exclude|without|including)\b", re.I)
_ELLIPTIC_START = re.compile(r"^\s*(and|but|so|then|also|what about|how about|what if|why|how come|in that case|if so|if not|now|only)\b", re.I)


def check_text(question: str, expected_sql: str = "", *, standalone: bool = True, needs_sql: bool = True, technical: bool = True) -> str | None:
    """Length limits, and (for a question that has to stand alone) no technical words that give the schema away."""
    if not 12 <= len(question) <= 400:
        return "the question must be between 12 and 400 characters"
    if needs_sql and not 6 <= len(expected_sql) <= 4000:
        return "the SQL must be between 6 and 4000 characters"
    if technical and _TECHNICAL.search(question):
        return 'the question uses technical words ("table", "column", "SQL", "GROUP BY"...); ask it the way a person who does not know how the data is stored would'
    return None


def similarity(a: str, b: str) -> float:
    """Return how alike two texts are, from 0 to 1: the share of their distinct words that both contain."""
    x, y = set(tokenize(a)), set(tokenize(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def _check_follow_up(question: str, earlier: list[str]) -> str | None:
    """A follow-up must need the conversation so far: it refers back, and it does not restate the topic."""
    if not (_REFERS_BACK.search(question) or _ELLIPTIC_START.search(question)):
        return (f'this follow-up ("{question}") could be asked on its own, so it is just another new question; rewrite it so it '
                'depends on the previous result by referring back to it ("and for last month?", "only those in the north", "sort that by ...") '
                'without naming the topic again')
    q_tokens = set(tokenize(question))
    seen = set(tokenize(" ".join(earlier)))
    if len(q_tokens) >= 4 and len(q_tokens & seen) / len(q_tokens) > RESTATES_LIMIT:
        return 'this follow-up repeats the earlier question\'s words instead of referring back; say "that" or "those" rather than naming the topic again'
    return None


def _category_problem(category: str, statement: exp.Expression, used: list[str], task: Task) -> str | None:
    """Whether the SQL is the kind of query the category asks for."""
    if category == "simple" and (len(used) != 1 or statement.find(exp.Join) or statement.find(exp.Group) or statement.find(exp.AggFunc)):
        return "a simple question needs exactly one table, no JOIN, no GROUP BY and no totals or counts; write a plain look-up, filter or sort"
    if category == "join":
        keys = join_keys([statement])
        if len(used) < 2 or not keys:
            return "a join question needs the SQL to JOIN at least two of the tables on their keys"
        declared = {pair for pair in task.schema.key_pairs() if all(side.split(".")[0] in used for side in pair)}
        if declared and not any(frozenset(key.split(" = ")) in declared for key in keys if " = " in key):
            options = "; ".join(" = ".join(sorted(pair)) for pair in sorted(declared, key=sorted))
            return f"the join must use the keys the tables are linked by: {options}"
    if category == "aggregate" and not statement.find(exp.AggFunc):
        return "an aggregation question needs the SQL to use COUNT, SUM, AVG, MIN or MAX"
    if category == "nested" and not statement.find(exp.With) and len(list(statement.find_all(exp.Select))) < 2:
        return "this question needs the SQL to use a subquery or a WITH (CTE); a plain query is not enough"
    return None


def expected_columns_of(statement: exp.Expression) -> list[str]:
    """The columns a test case should expect of this SQL: the ones the question is about (what is selected, filtered, grouped
    and sorted), as ``table.column`` when the SQL says which table. The columns a join is made on are left out: another
    way to link the tables is not a mistake, and the tables are checked on their own."""
    aliases = {a.alias.lower() for a in statement.find_all(exp.Alias) if a.alias}
    names = alias_map(statement)
    found: dict[str, None] = {}
    for column in statement.find_all(exp.Column):
        if isinstance(column.this, exp.Star) or column.name.lower() in aliases or column.find_ancestor(exp.Join) is not None:
            continue
        table = names.get(column.table.lower(), column.table.lower()) if column.table else ""
        found.setdefault(f"{table}.{column.name.lower()}" if table else column.name.lower())
    return list(found)


def analyse_sql(sql: str, task: Task, dialect: str) -> tuple[dict | None, str]:
    """Read the SQL of one turn against the schema it was written from.

    Returns ``({"statement", "tables", "columns"}, "")`` for SQL that parses, only reads, and uses nothing but the tables it was
    given and columns that exist in them; otherwise ``(None, the reason)``.
    """
    statements, error = parse_statements(sql, dialect)
    if error:
        return None, f"the SQL does not parse as {dialect}: {error}"
    problem = read_only_problem(statements)
    if problem:
        return None, f"the SQL must be one read-only SELECT, but {problem}"
    statement = statements[0]
    used = tables_used(statements)
    if not used:
        return None, "the SQL does not read from any table"
    outside = [t for t in used if t not in task.tables]
    if outside:
        return None, f"the SQL uses tables it was not given: {', '.join(outside)}. Use only: {', '.join(task.tables)}"

    aliases = {a.alias.lower() for a in statement.find_all(exp.Alias) if a.alias}
    names = alias_map(statement)
    for column in statement.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        name = column.name.lower()
        if column.table:
            table = names.get(column.table.lower())
            if table in task.schema.tables and name not in task.schema.tables[table].column_names():
                return None, f"column {name} does not exist in table {table}; its columns are: {', '.join(task.schema.tables[table].column_names())}"
        elif name not in aliases and not any(name in task.schema.tables[t].column_names() for t in used):
            return None, f"column {name} does not exist in {', '.join(used)}; use only the columns shown"
    return {"statement": statement, "tables": used, "columns": expected_columns_of(statement)}, ""


def _clean_sql(raw) -> str:
    sql = str(raw or "").strip()
    return sql.rstrip(";").strip() if sql.endswith(";") and sql.count(";") == 1 else sql


def _answer_turn(task: Task, raw, index: int, earlier: list[dict], avoid: list[str], dialect: str) -> tuple[dict | None, str]:
    """One turn that has SQL: (the cleaned turn, "") or (None, the reason it was rejected)."""
    if not isinstance(raw, dict):
        return None, "each turn must be an object with question and sql"
    question, sql = str(raw.get("question") or "").strip(), _clean_sql(raw.get("sql") or raw.get("expected_sql"))
    problem = check_text(question, sql)
    if problem:
        return None, problem
    found, problem = analyse_sql(sql, task, dialect)
    if found is None:
        return None, problem
    if task.category != "followup":
        problem = _category_problem(task.category, found["statement"], found["tables"], task)
        if problem:
            return None, problem
    turn = {"question": question, "expected_sql": sql, "expected_tables": ", ".join(found["tables"]), "expected_columns": ", ".join(found["columns"])}
    if task.category == "followup" and index > 0:
        problem = _check_follow_up(question, [t["question"] for t in earlier])
        if problem:
            return None, problem
        needs = str(raw.get("depends_on") or raw.get("relies_on") or raw.get("context") or "").strip()
        if len(needs) < MIN_DEPENDS_CHARS:
            return None, 'every follow-up needs "depends_on": one sentence saying what it relies on from the earlier turns'
        turn["needs_context"] = needs
    if any(similarity(question, other) >= SIMILARITY_LIMIT for other in avoid + [t["question"] for t in earlier]):
        return None, "this is too similar to a question already written; ask about something different"
    return turn, ""


def _declining_turn(task: Task, data: dict, avoid: list[str]) -> tuple[list[dict] | None, str]:
    """A vague or an unsafe question: it has no SQL, only a note saying why the assistant should not just answer it."""
    question = str(data.get("question") or "").strip()
    key, what = ("unclear_because", "what the unclear parts are") if task.category == "vague" else ("harm", "what is wrong with the request")
    note = str(data.get(key) or "").strip()
    problem = check_text(question, needs_sql=False, technical=task.category == "vague")
    if problem:
        return None, problem
    if len(note) < MIN_NOTE_CHARS:
        return None, f'add "{key}": one sentence saying {what}'
    if any(similarity(question, other) >= SIMILARITY_LIMIT for other in avoid):
        return None, "this is too similar to a question already written; ask about something different"
    return [{"question": question, "note": note}], ""


def validate(task: Task, data: dict | None, *, turns: int, avoid: list[str], dialect: str) -> tuple[list[dict] | None, str]:
    """Check one model reply. Returns (turns, "") when it follows every rule, else (None, reason).

    In a conversation the reason names the turn that broke the rule, so the retry can fix just that one."""
    if not data:
        return None, "the reply was not valid JSON in the required shape"
    if task.category in ("vague", "unsafe"):
        return _declining_turn(task, data, avoid)
    raw_turns = data.get("turns") if task.category == "followup" else [data]
    if not isinstance(raw_turns, list) or not raw_turns:
        return None, 'the reply must contain "turns" for a conversation' if task.category == "followup" else "missing question"
    if task.category == "followup" and not 2 <= len(raw_turns) <= max(2, turns):
        return None, f"the conversation must have between 2 and {max(2, turns)} turns"

    out: list[dict] = []
    for index, raw in enumerate(raw_turns):
        turn, problem = _answer_turn(task, raw, index, out, avoid, dialect)
        if turn is None:
            return None, f"turn {index + 1}: {problem}" if task.category == "followup" else problem
        out.append(turn)
    return out, ""
