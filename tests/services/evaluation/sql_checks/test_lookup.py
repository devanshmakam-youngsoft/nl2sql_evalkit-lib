"""The schema lookup score: did the tables and columns the assistant looked at hold what the test case expects."""
from nl2sql_evalkit.services.evaluation.sql_checks import schema_lookup

SCHEMA = "orders(id, customer_id, amount, status)\ncustomers(id, name, region)"


def test_every_expected_table_and_column_in_the_schema_scores_ten():
    got = schema_lookup(SCHEMA, "orders, customers", "customers.region, orders.amount")
    assert got["graded"] and got["marks"] == 10 and got["tables_missing"] == [] and got["columns_missing"] == []
    assert got["remarks"] == "The schema the assistant looked at included every expected table and column."


def test_a_missing_table_or_column_lowers_the_score_and_is_named():
    got = schema_lookup("orders(id, amount)", "orders, approvals", "orders.amount, approvals.status")
    assert got["marks"] == 5 and got["tables_missing"] == ["approvals"] and got["columns_missing"] == ["approvals.status"]
    assert got["remarks"] == "The schema the assistant looked at did not include table approvals or column approvals.status."


def test_each_kind_that_was_expected_counts_equally():
    assert schema_lookup("orders(id)", "orders, customers", "")["marks"] == 5             # tables only
    assert schema_lookup("orders(id)", "", "id, amount")["marks"] == 5                    # columns only


def test_names_are_matched_as_whole_words_without_regard_to_case():
    assert schema_lookup("ORDERS(ID)", "orders", "id")["marks"] == 10
    assert schema_lookup("order_items(id)", "order", "")["tables_missing"] == ["order"]  # order is not order_items
    assert schema_lookup("CREATE TABLE public.orders (id int)", "public.orders", "")["marks"] == 10


def test_nothing_is_graded_without_a_schema_or_expectations_or_for_a_declining_case():
    assert schema_lookup("", "orders", "")["graded"] is False and schema_lookup("", "orders", "")["marks"] is None
    assert schema_lookup(SCHEMA, "", "")["graded"] is False
    assert schema_lookup(SCHEMA, "orders", "", "clarify")["graded"] is False
    assert schema_lookup(SCHEMA, "orders", "", "refuse")["marks"] is None
