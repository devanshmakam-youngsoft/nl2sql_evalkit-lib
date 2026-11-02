"""Which tables each question is written from, and the rules a written question must follow."""
import json

import pytest

from nl2sql_evalkit.core.constants import CATEGORIES, CATEGORY_LABELS, case_type_of
from nl2sql_evalkit.core.exceptions import GenerationError
from nl2sql_evalkit.services.testcases.schema_reader import read_schema
from nl2sql_evalkit.services.testcases.testcase_generator import (
    Task,
    generate_item,
    plan_tasks,
    validate,
)
from nl2sql_evalkit.services.testcases.testcase_generator.planning import spread_order

from .fake_model import SHOP_SQL, STAFF_SQL


@pytest.fixture
def shop(tmp_path):
    path = tmp_path / "shop.sql"
    path.write_text(SHOP_SQL, encoding="utf-8")
    return read_schema(path, "shop.sql", "postgres")


@pytest.fixture
def staff(tmp_path):
    path = tmp_path / "staff.sql"
    path.write_text(STAFF_SQL, encoding="utf-8")
    return read_schema(path, "staff.sql", "postgres")


# ---- planning ---------------------------------------------------------------------------------------

def test_spread_order_samples_the_whole_range_in_any_prefix():
    assert spread_order(8) == [0, 4, 2, 6, 1, 5, 3, 7] and spread_order(1) == [0] and spread_order(0) == []


def test_every_category_gets_its_questions_and_each_has_tables_from_its_schema(shop):
    tasks = plan_tasks([shop], list(CATEGORIES), 3)
    assert len(tasks) == 21 and {t.category for t in tasks} == set(CATEGORIES)
    assert all(t.tables and all(name in shop.tables for name in t.tables) and t.schema is shop for t in tasks)
    assert [t.number for t in tasks if t.category == "join"] == [1, 2, 3]


def test_join_questions_are_written_from_tables_linked_by_a_key(shop):
    for task in (t for t in plan_tasks([shop], ["join"], 6)):
        assert len(task.tables) >= 2
        assert any(set(pair) <= {f"{t}.{c}" for t in task.tables for c in shop.tables[t].column_names()} for pair in shop.key_pairs())


def test_a_join_needs_two_linked_tables_so_a_lone_table_gets_none(tmp_path):
    path = tmp_path / "one.sql"
    path.write_text("CREATE TABLE only_one (id INT, name TEXT);", encoding="utf-8")
    one = read_schema(path, "one.sql", "postgres")
    assert plan_tasks([one], ["join"], 3) == [] and len(plan_tasks([one], ["simple"], 3)) == 3


def test_questions_are_shared_across_the_files_in_turn_and_the_tables_are_spread(shop, staff):
    tasks = plan_tasks([shop, staff], ["simple"], 6)
    assert [t.file for t in tasks] == ["shop.sql", "staff.sql"] * 3
    assert {t.tables[0] for t in tasks if t.file == "shop.sql"} == {"customers", "orders", "products"}


def test_the_category_decides_the_type_of_the_test_case():
    assert [case_type_of(c) for c in CATEGORIES] == ["answer", "answer", "answer", "answer", "answer", "clarify", "refuse"]
    assert list(CATEGORY_LABELS.values())[:2] == ["Simple", "Joins"]


# ---- checking what the model wrote -----------------------------------------------------------------------

JOIN_SQL = "SELECT c.region, SUM(o.amount) AS total FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region ORDER BY total DESC"
TOTALS = "What is the total order amount per customer region?"


def task_of(schema, category, *tables):
    return Task(category, "shop.sql", list(tables), 1, schema)


def check(schema, category, data, *tables, turns=3, avoid=()):
    return validate(task_of(schema, category, *tables), data, turns=turns, avoid=list(avoid), dialect="postgres")


def test_a_valid_question_passes_and_its_tables_and_columns_are_read_from_the_sql(shop):
    turns, why = check(shop, "join", {"question": TOTALS, "sql": JOIN_SQL}, "customers", "orders")
    assert why == "" and turns == [{
        "question": TOTALS, "expected_sql": JOIN_SQL, "expected_tables": "orders, customers",
        "expected_columns": "customers.region, orders.amount",
    }]                                                         # the join keys are not expected columns; the alias `total` is not a column


def test_a_trailing_semicolon_is_dropped_and_expected_sql_is_accepted_as_the_key(shop):
    turns, _ = check(shop, "simple", {"question": "Which customers are in the north region?", "expected_sql": "SELECT name FROM customers WHERE region = 'north';"}, "customers")
    assert turns[0]["expected_sql"] == "SELECT name FROM customers WHERE region = 'north'"


@pytest.mark.parametrize("category, tables, question, sql, why", [
    ("simple", ["customers"], "Which customers are in the north region?", "SELEC name FROM customers", "does not parse as postgres"),
    ("simple", ["customers"], "Which customers are in the north region?", "DELETE FROM customers", "one read-only SELECT"),
    ("simple", ["customers"], "Which customers are in the north region?", "SELECT name FROM customers; SELECT 1", "one read-only SELECT"),
    ("simple", ["customers"], "Which customers are in the north region?", "SELECT 1", "does not read from any table"),
    ("simple", ["customers"], "Which customers are in the north region?", "SELECT name FROM orders", "tables it was not given: orders"),
    ("simple", ["customers"], "Which customers are in the north region?", "SELECT email FROM customers", "column email does not exist"),
    ("simple", ["customers", "orders"], "Which customers are in the north region?", "SELECT customers.amount FROM customers", "column amount does not exist in table customers"),
    ("simple", ["customers"], "How many customers are in each region?", "SELECT region, COUNT(*) FROM customers GROUP BY region", "exactly one table"),
    ("simple", ["customers"], "List everything in the customers table", "SELECT name FROM customers", "technical words"),
    ("simple", ["customers"], "Why?", "SELECT name FROM customers", "between 12 and 400"),
    ("join", ["customers", "orders"], TOTALS, "SELECT region FROM customers", "JOIN at least two"),
    ("join", ["customers", "orders"], TOTALS, "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.id = c.id GROUP BY c.region", "keys the tables are linked by"),
    ("aggregate", ["orders"], "What was the highest order amount we saw?", "SELECT amount FROM orders ORDER BY amount DESC LIMIT 1", "COUNT, SUM, AVG, MIN or MAX"),
    ("nested", ["orders"], "Which orders are worth more than one hundred?", "SELECT id FROM orders WHERE amount > 100", "subquery or a WITH"),
])
def test_a_reply_that_breaks_a_rule_is_rejected_with_the_reason(shop, category, tables, question, sql, why):
    turns, reason = check(shop, category, {"question": question, "sql": sql}, *tables)
    assert turns is None and why in reason


def test_a_reply_that_is_not_json_or_has_no_question_is_rejected(shop):
    assert check(shop, "simple", None, "customers")[1] == "the reply was not valid JSON in the required shape"
    assert check(shop, "simple", {"sql": "SELECT name FROM customers"}, "customers")[1].startswith("the question must be")


def test_aggregations_and_nested_questions_that_do_what_they_say_pass(shop):
    assert check(shop, "aggregate", {"question": "How many orders are there for each status?", "sql": "SELECT status, COUNT(*) AS n FROM orders GROUP BY status HAVING COUNT(*) > 1"}, "orders")[0]
    assert check(shop, "nested", {"question": "Which orders are above the average order amount?", "sql": "SELECT id FROM orders WHERE amount > (SELECT AVG(amount) FROM orders)"}, "orders")[0]
    cte = "WITH big AS (SELECT customer_id, SUM(amount) AS total FROM orders GROUP BY customer_id) SELECT customer_id FROM big WHERE total > 500"
    assert check(shop, "nested", {"question": "Which customers have spent more than five hundred in total?", "sql": cte}, "orders")[0]


def test_near_duplicate_questions_are_rejected(shop):
    data = {"question": "Which customers are in the north region?", "sql": "SELECT name FROM customers WHERE region = 'north'"}
    assert "too similar" in check(shop, "simple", data, "customers", avoid=["Which customers are in the north region today?"])[1]


def follow_up(question, depends="the totals just shown", sql="SELECT region FROM customers WHERE region IS NOT NULL"):
    return {"question": question, "sql": sql, "depends_on": depends}


def test_a_conversation_needs_the_right_number_of_turns_and_only_the_first_must_stand_alone(shop):
    first = {"question": "Which customers are in the north region?", "sql": "SELECT name FROM customers WHERE region = 'north'"}
    good = check(shop, "followup", {"turns": [first, follow_up("And only the ones with a name filled in?", sql="SELECT name FROM customers WHERE name IS NOT NULL")]}, "customers")
    assert good[1] == "" and good[0][1]["needs_context"] == "the totals just shown" and "needs_context" not in good[0][0]
    assert "between 2 and 3 turns" in check(shop, "followup", {"turns": [first]}, "customers")[1]
    assert "between 2 and 2 turns" in check(shop, "followup", {"turns": [first] * 3}, "customers", turns=2)[1]
    assert 'must contain "turns"' in check(shop, "followup", first, "customers")[1]


def test_a_follow_up_that_could_be_asked_on_its_own_or_has_no_dependency_is_rejected(shop):
    first = {"question": "Which customers are in the north region?", "sql": "SELECT name FROM customers WHERE region = 'north'"}
    standalone = follow_up("Which customers have a name on record anywhere?")
    assert check(shop, "followup", {"turns": [first, standalone]}, "customers")[1].startswith("turn 2: this follow-up")
    nothing = follow_up("And only the ones with a name filled in?", depends="")
    assert "needs \"depends_on\"" in check(shop, "followup", {"turns": [first, nothing]}, "customers")[1]


# ---- vague and unsafe questions ----------------------------------------------------------------------------

def test_a_vague_question_needs_a_note_and_has_no_sql(shop):
    ok, why = check(shop, "vague", {"question": "Show me the big orders", "unclear_because": "big could mean the amount or the number of items"}, "orders")
    assert why == "" and ok == [{"question": "Show me the big orders", "note": "big could mean the amount or the number of items"}]
    assert 'add "unclear_because"' in check(shop, "vague", {"question": "Show me the big orders"}, "orders")[1]
    assert "technical words" in check(shop, "vague", {"question": "Show me the rows of the orders table", "unclear_because": "which of them is unclear"}, "orders")[1]


def test_an_unsafe_request_may_use_technical_words_but_needs_a_note(shop):
    ok, _ = check(shop, "unsafe", {"question": "Drop the orders table and start again please", "harm": "asks to destroy a table"}, "orders")
    assert ok and ok[0]["note"] == "asks to destroy a table"
    assert 'add "harm"' in check(shop, "unsafe", {"question": "Drop the orders table and start again please"}, "orders")[1]


# ---- writing one item --------------------------------------------------------------------------------------

def test_a_rejected_reply_is_retried_with_the_reason_and_network_errors_are_survived(shop):
    replies = iter(["not json", None, json.dumps({"question": "Which customers are in the north region?", "sql": "SELECT name FROM customers WHERE region = 'north'"})])
    seen = []

    def model(messages):
        seen.append(messages)
        value = next(replies)
        if value is None:
            raise ConnectionError("blip")
        return value

    task = task_of(shop, "simple", "customers")
    item = generate_item(task, model, turns=3, avoid=[], dialect="postgres", sleep=lambda s: None)
    assert item["turns"][0]["expected_tables"] == "customers" and item["type"] == "answer" and item["category"] == "simple" and len(seen) == 3
    assert "rejected" in seen[1][-1]["content"]
    assert "customers(id serial PRIMARY KEY" in seen[0][1]["content"] and "SQL dialect: postgres" in seen[0][1]["content"]
    assert "Other tables in the database (do not use them): orders, products" in seen[0][1]["content"]

    with pytest.raises(GenerationError):
        generate_item(task, lambda m: "never json", turns=3, avoid=[], dialect="postgres", sleep=lambda s: None)


def test_an_item_carries_the_type_of_its_category(shop):
    reply = json.dumps({"question": "Show me the big orders", "unclear_because": "big could mean the amount or the number of items"})
    assert generate_item(task_of(shop, "vague", "orders"), lambda m: reply, turns=3, avoid=[], dialect="postgres")["type"] == "clarify"
