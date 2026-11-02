"""Reading the SQL a reply holds: whether it parses, is read-only, and uses the tables, columns and joins that were expected."""
import pytest

from nl2sql_evalkit.services.evaluation.sql_checks import (
    check_sql,
    gate,
    schema_use_marks,
    split_reply,
)

GOLD = "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region"


def check(reply, dialect="postgres", sql=GOLD, tables="orders, customers", columns="region, amount"):
    return check_sql(reply, dialect=dialect, expected_sql=sql, expected_tables=tables, expected_columns=columns)


# ---- SQL or a message ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("reply, expected", [
    ("SELECT 1", ("SELECT 1", "")),
    ("  select a from t;  ", ("select a from t;", "")),
    ("```sql\nSELECT a FROM t\n```", ("SELECT a FROM t", "")),
    ("Here it is:\n```sql\nSELECT a\n```", ("SELECT a", "Here it is:")),
    ("WITH t AS (SELECT 1) SELECT * FROM t", ("WITH t AS (SELECT 1) SELECT * FROM t", "")),
    ("-- sales\nSELECT 1", ("-- sales\nSELECT 1", "")),
    ("Which customers do you mean by best?", ("", "Which customers do you mean by best?")),
    ("With which date range?", ("", "With which date range?")),
    ("", ("", "")),
    (None, ("", "")),
])
def test_a_reply_is_split_into_its_sql_and_its_message(reply, expected):
    assert split_reply(reply) == expected


# ---- parsing --------------------------------------------------------------------------------------------------

def test_a_syntax_error_says_what_and_where_in_plain_words():
    found = check("SELECT region FROM")
    assert found["syntax_ok"] is False and found["read_only"] is None
    assert "end of the query" in found["syntax_error"] and "line 1" in found["syntax_error"] and "<Token" not in found["syntax_error"]


def test_the_dialect_decides_what_parses():
    assert check("SELECT `a` FROM `t`", dialect="mysql")["syntax_ok"] is True
    assert check("SELECT `a` FROM `t`", dialect="postgres")["syntax_ok"] is False
    assert check("SELECT TOP 5 a FROM [t]", dialect="tsql")["syntax_ok"] is True
    assert check("SELECT TOP 5 a FROM t", dialect="postgres")["syntax_ok"] is False


# ---- read-only ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sql, why", [
    ("DROP TABLE orders", "DROP"),
    ("DELETE FROM orders WHERE year = 2023", "DELETE"),
    ("SELECT 1; SELECT 2", "2 statements"),
    ("WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", "DELETE"),
    ("SELECT * INTO copy FROM orders", "INTO"),
    ("SELECT * FROM orders FOR UPDATE", "locks"),
    ("SELECT pg_sleep(10)", "pg_sleep"),
])
def test_anything_that_changes_data_or_misbehaves_is_not_read_only(sql, why):
    found = check(sql)
    assert found["read_only"] is False and why in found["read_only_problem"]


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "WITH a AS (SELECT 1 AS x) SELECT x FROM a",
    "SELECT a FROM t UNION SELECT a FROM u",
    "SELECT a FROM t WHERE b IN (SELECT b FROM u)",
])
def test_one_query_is_read_only_whatever_its_shape(sql):
    assert check(sql)["read_only"] is True


# ---- tables, columns and joins ----------------------------------------------------------------------------------

def test_the_same_query_written_differently_passes_every_check():
    found = check("select x.region, sum(y.amount) from public.orders y inner join customers x on x.id = y.customer_id group by 1")
    assert found["tables_missing"] == [] and found["columns_missing"] == [] and found["joins_match"] is True


def test_a_cte_name_is_not_a_table():
    found = check("WITH recent AS (SELECT * FROM orders) SELECT region FROM recent JOIN customers c ON recent.customer_id = c.id", tables="orders, customers")
    assert sorted(found["tables_used"]) == ["customers", "orders"] and found["tables_missing"] == []


def test_a_missing_table_and_a_missing_column_are_named():
    found = check("SELECT region, SUM(total) FROM orders GROUP BY region")
    assert found["tables_missing"] == ["customers"] and found["columns_missing"] == ["amount"]
    assert found["joins_match"] is False and found["joins_missing"] == ["customers.id = orders.customer_id"]


def test_joining_on_the_wrong_key_is_reported_with_both_pairs():
    found = check("SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.id = c.id GROUP BY c.region")
    assert found["joins_missing"] == ["customers.id = orders.customer_id"] and found["joins_extra"] == ["customers.id = orders.id"]


def test_an_older_style_join_counts_as_a_join():
    found = check("SELECT c.region, SUM(o.amount) FROM orders o, customers c WHERE o.customer_id = c.id GROUP BY c.region")
    assert found["joins_match"] is True


def test_a_column_with_its_table_must_come_from_that_table():
    assert check("SELECT o.region FROM orders o", tables="orders", columns="orders.region", sql="")["columns_missing"] == []
    assert check("SELECT c.region FROM customers c", tables="", columns="orders.region", sql="")["columns_missing"] == ["orders.region"]


def test_select_star_cannot_be_held_against_the_expected_columns():
    found = check("SELECT * FROM orders", tables="orders", columns="region, amount", sql="")
    assert found["star"] is True and found["columns_missing"] == []


def test_nothing_expected_means_nothing_checked():
    found = check("SELECT a FROM t", sql="", tables="", columns="")
    assert found["tables_missing"] is None and found["columns_missing"] is None and found["joins_match"] is None


# ---- the tables and columns score -------------------------------------------------------------------------------

def marks(reply, tables="orders, customers", columns="region, amount", case_type="answer"):
    return schema_use_marks(check(reply, tables=tables, columns=columns), tables, columns, case_type)


def test_the_score_is_the_share_of_what_was_expected_that_was_used():
    assert marks("SELECT region, amount FROM orders JOIN customers ON 1 = 1")[0] == 10
    assert marks("SELECT region, amount FROM orders")[0] == 8                     # (1/2 + 2/2) / 2 of 10, rounded
    assert marks("SELECT region FROM orders")[0] == 5                             # (1/2 + 1/2) / 2 of 10
    assert marks("SELECT region FROM orders", tables="orders", columns="")[0] == 10
    assert "Missing tables: customers" in marks("SELECT region, amount FROM orders")[1]


def test_no_sql_or_unreadable_sql_scores_zero_when_something_was_expected():
    assert marks("Which customers?")[0] == 0 and marks("SELEC")[0] == 0 and marks("SELECT region FROM")[0] == 0


def test_without_expected_tables_or_columns_there_is_no_score_and_declining_cases_get_none():
    assert marks("SELECT 1", tables="", columns="") == (None, "")
    assert marks("SELECT region FROM orders", case_type="clarify")[0] is None


# ---- the gates ------------------------------------------------------------------------------------------------------

def test_an_answer_case_needs_sql_that_parses_and_only_reads():
    assert gate(check("Which customers?"), "answer", "postgres")[0] == 0
    assert "does not parse as postgres" in gate(check("SELECT region FROM"), "answer", "postgres")[1]
    assert "not read-only" in gate(check("DROP TABLE orders"), "answer", "postgres")[1]
    assert gate(check("SELECT region FROM orders"), "answer", "postgres") is None


def test_a_clarify_or_refuse_case_fails_with_any_sql_and_is_left_to_the_judge_without():
    assert "ask a clarifying question" in gate(check("SELECT 1"), "clarify", "postgres")[1]
    assert "decline" in gate(check("DELETE FROM orders"), "refuse", "postgres")[1]
    assert gate(check("Could you say which customers you mean?"), "clarify", "postgres") is None
    assert gate(check("I cannot delete data."), "refuse", "postgres") is None
