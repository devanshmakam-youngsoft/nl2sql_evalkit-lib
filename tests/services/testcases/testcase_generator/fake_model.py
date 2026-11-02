"""A stand-in for the model that writes test cases: it writes a valid item of whatever category the prompt asks for,
using only the tables and columns it is shown."""
import json
import re
import threading

WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen"]

SHOP_SQL = """-- a small shop
CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  region TEXT
);
CREATE TABLE orders (
  id INT PRIMARY KEY,
  customer_id INT REFERENCES customers(id),
  product_id INT,
  amount NUMERIC(10,2),
  status TEXT,
  created_at DATE,
  CONSTRAINT fk_product FOREIGN KEY (product_id) REFERENCES products (id)
);
CREATE TABLE products (id INT PRIMARY KEY, title TEXT, price NUMERIC(10,2));
INSERT INTO customers VALUES (1, 'Ann', 'north');
"""

STAFF_SQL = """CREATE TABLE departments (id INT PRIMARY KEY, name TEXT);
CREATE TABLE employees (id INT PRIMARY KEY, department_id INT REFERENCES departments(id), name TEXT, salary NUMERIC);
"""


def tables_in(user_message: str) -> dict[str, list[str]]:
    """The tables listed under ``Tables:`` in the message sent to the model, with their columns."""
    block = user_message.split("Tables:\n", 1)[1].split("\n\n", 1)[0]
    tables = {}
    for line in block.splitlines():
        match = re.fullmatch(r"(\w+)\((.*)\)", line.strip())
        if match:
            columns = [item.strip().split()[0] for item in re.split(r",\s*(?![^(]*\))", match.group(2)) if item.strip()]
            tables[match.group(1)] = columns
    return tables


def link_between(user_message: str, tables: dict[str, list[str]]):
    """(table, column, other table, other column) for a foreign key shown with ``->`` between two of the tables, else None."""
    block = user_message.split("Tables:\n", 1)[1].split("\n\n", 1)[0]
    for line in block.splitlines():
        owner = line.split("(", 1)[0]
        for column, other, other_column in re.findall(r"(\w+) [^,]*?-> (\w+)\.(\w+)", line):
            if other in tables and owner in tables:
                return owner, column, other, other_column
    return None


class FakeModel:
    """Writes a valid item for any task. ``hold`` pauses every call until set; ``fail_first`` raises for that many calls."""

    def __init__(self, hold: threading.Event | None = None, fail_first: int = 0):
        self.calls = 0
        self.hold = hold
        self.fail_first = fail_first
        self.lock = threading.Lock()
        self.seen: list[list[dict]] = []

    def __call__(self, messages):
        with self.lock:
            self.calls += 1
            n = self.calls
            self.seen.append(messages)
        if self.hold is not None:
            self.hold.wait(10)
        if n <= self.fail_first:
            raise ConnectionError("network down")
        system, user = messages[0]["content"], messages[1]["content"]
        tables = tables_in(user)
        first = next(iter(tables))
        columns = tables[first]
        c1, c2 = columns[0], columns[min(1, len(columns) - 1)]
        word = WORDS[n % len(WORDS)]

        if "ONE vague question" in system:
            return json.dumps({"question": f"Show me the best {first} for round {word}", "unclear_because": "best could mean the most orders or the highest value"})
        if "ONE unsafe request" in system:
            return json.dumps({"question": f"Please delete every {first} entry from last year, attempt {word}", "harm": "asks to destroy data"})
        if "ONE simple question" in system:
            return json.dumps({"question": f"Show the {c2} of every {first} for batch {word}", "sql": f"SELECT {c2} FROM {first} WHERE {c1} IS NOT NULL ORDER BY {c2}"})
        if "so the SQL has to JOIN them" in system:
            link = link_between(user, tables)
            owner, column, other, other_column = link
            return json.dumps({"question": f"Which {owner} go with which {other}, listing details for set {word}",
                               "sql": f"SELECT a.{tables[owner][1]}, b.{tables[other][1]} FROM {owner} a JOIN {other} b ON a.{column} = b.{other_column}"})
        if "needs an aggregate" in system:
            return json.dumps({"question": f"How many {first} are there for each {c2}, round {word}", "sql": f"SELECT {c2}, COUNT(*) AS n FROM {first} GROUP BY {c2}"})
        if "subquery or a WITH" in system:
            return json.dumps({"question": f"Which {c2} of {first} also appear among those with a {c1}, list {word}",
                               "sql": f"SELECT {c2} FROM {first} WHERE {c2} IN (SELECT {c2} FROM {first} WHERE {c1} IS NOT NULL)"})
        turns = int(re.search(r"exactly (\d+) turns", system).group(1))
        items = [{"question": f"Show the {c2} of every {first} for batch {word}", "sql": f"SELECT {c2} FROM {first}"}]
        phrases = [
            (f"And only those with a {c1} on record, option {{w}}?", f"SELECT {c2} FROM {first} WHERE {c1} IS NOT NULL"),
            (f"Now sort that by {c2} instead, variant {{w}}?", f"SELECT {c2} FROM {first} WHERE {c1} IS NOT NULL ORDER BY {c2}"),
            (f"Also drop the ones without a {c1} there, take {{w}}?", f"SELECT {c2} FROM {first} WHERE {c1} <> '' ORDER BY {c2}"),
        ]
        for i in range(1, turns):
            question, sql = phrases[i - 1]
            items.append({"question": question.format(w=WORDS[(n + i) % len(WORDS)]), "sql": sql, "depends_on": "the list of values just shown"})
        return json.dumps({"turns": items})
