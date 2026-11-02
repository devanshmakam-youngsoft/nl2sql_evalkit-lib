"""Reading uploaded schema files: tables, columns, keys and comments, without a database and without any data."""
import pytest

from nl2sql_evalkit.core.exceptions import SchemaError
from nl2sql_evalkit.services.testcases.schema_reader import read_schema

POSTGRES = """-- a small shop
CREATE TABLE public.customers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  region TEXT
);
CREATE TABLE orders (
  id INT,
  customer_id INT REFERENCES customers(id),
  product_id INT,
  amount NUMERIC(10,2),
  PRIMARY KEY (id),
  CONSTRAINT fk_product FOREIGN KEY (product_id) REFERENCES products (id)
);
CREATE TABLE products (id INT PRIMARY KEY, title TEXT);
ALTER TABLE ONLY orders ADD CONSTRAINT fk_customer FOREIGN KEY (customer_id) REFERENCES customers(id);
COMMENT ON COLUMN orders.amount IS 'Total in USD';
INSERT INTO customers VALUES (1, 'A; B', 'north');
CREATE INDEX idx_orders ON orders (customer_id);
COPY customers (id) FROM stdin;
1
\\.
"""


def read(tmp_path, text, name="shop.sql", dialect="postgres"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return read_schema(path, name, dialect)


def test_tables_columns_types_and_primary_keys_are_read_and_the_data_is_ignored(tmp_path):
    schema = read(tmp_path, POSTGRES)
    assert list(schema.tables) == ["customers", "orders", "products"] and schema.skipped == []
    orders = schema.tables["orders"]
    assert orders.column_names() == ["id", "customer_id", "product_id", "amount"]
    assert [c.primary_key for c in orders.columns] == [True, False, False, False]
    assert orders.columns[3].type == "decimal(10, 2)" and orders.columns[3].comment == "Total in USD"
    assert schema.tables["customers"].columns[0].primary_key


def test_a_key_declared_inline_in_the_table_and_by_alter_table_is_one_key(tmp_path):
    schema = read(tmp_path, POSTGRES)
    keys = [(k.columns, k.ref_table, k.ref_columns) for k in schema.tables["orders"].foreign_keys]
    assert sorted(keys) == [(["customer_id"], "customers", ["id"]), (["product_id"], "products", ["id"])]
    assert schema.key_pairs() == {frozenset({"orders.customer_id", "customers.id"}), frozenset({"orders.product_id", "products.id"})}
    assert schema.relations() == {"customers": {"orders"}, "orders": {"customers", "products"}, "products": {"orders"}}


def test_the_description_shown_to_the_model_has_types_keys_and_comments(tmp_path):
    text = read(tmp_path, POSTGRES).describe(["orders", "customers"])
    assert "orders(id int PRIMARY KEY, customer_id int -> customers.id, product_id int -> products.id, amount decimal(10, 2)  /* Total in USD */)" in text
    assert "customers(id serial PRIMARY KEY, name varchar(100), region text)" in text


def test_a_schema_without_declared_keys_gets_them_from_the_names_only_when_asked(tmp_path):
    schema = read(tmp_path, "CREATE TABLE customers (id INT, name TEXT);\nCREATE TABLE orders (id INT, customer_id INT, total INT);\n")
    assert schema.key_pairs() == set() and schema.relations(inferred=False) == {"customers": set(), "orders": set()}
    assert schema.key_pairs(inferred=True) == {frozenset({"orders.customer_id", "customers.id"})}
    assert schema.relations()["orders"] == {"customers"}


def test_mysql_and_sql_server_syntax_are_read_in_their_dialect(tmp_path):
    mysql = read(tmp_path, "CREATE TABLE `orders` (`id` int NOT NULL AUTO_INCREMENT COMMENT 'pk', `cid` int, PRIMARY KEY (`id`), "
                           "KEY `idx` (`cid`), CONSTRAINT `fk` FOREIGN KEY (`cid`) REFERENCES `customers` (`id`)) ENGINE=InnoDB;\n", dialect="mysql")
    assert mysql.tables["orders"].column_names() == ["id", "cid"] and mysql.tables["orders"].columns[0].comment == "pk"
    assert mysql.tables["orders"].foreign_keys[0].ref_table == "customers"
    tsql = read(tmp_path, "CREATE TABLE [dbo].[orders] ([id] INT NOT NULL PRIMARY KEY, [cid] INT NULL FOREIGN KEY REFERENCES [dbo].[customers]([id]));\n",
                dialect="tsql")
    assert tsql.tables["orders"].columns[0].primary_key and tsql.tables["orders"].foreign_keys[0].ref_table == "customers"


def test_a_statement_that_cannot_be_read_is_skipped_and_listed_and_the_rest_is_kept(tmp_path):
    schema = read(tmp_path, "CREATE TABLE broken (id INT,, ;\nCREATE TABLE fine (id INT, name TEXT);\n")
    assert list(schema.tables) == ["fine"] and schema.skipped and schema.skipped[0].startswith("CREATE TABLE broken")


def test_a_byte_order_mark_and_an_odd_character_do_not_matter(tmp_path):
    path = tmp_path / "a.ddl"
    path.write_bytes("﻿CREATE TABLE t (id INT, name TEXT /* café */);".encode("utf-8") + b"\xff")
    assert list(read_schema(path, "a.ddl", "postgres").tables) == ["t"]


@pytest.mark.parametrize("name, text, message", [
    ("deck.pptx", "CREATE TABLE t (id INT);", "unsupported file type"),
    ("empty.sql", "   \n", "is empty"),
    ("views.sql", "CREATE VIEW v AS SELECT 1;\nINSERT INTO t VALUES (1);\n", "no CREATE TABLE statements"),
])
def test_a_file_that_cannot_be_used_says_why(tmp_path, name, text, message):
    with pytest.raises(SchemaError, match=message):
        read(tmp_path, text, name=name)


def test_ddl_written_for_one_dialect_is_not_read_as_another(tmp_path):
    with pytest.raises(SchemaError, match="could be read as postgres"):
        read(tmp_path, "CREATE TABLE `orders` (`id` int, `name` varchar(5));\n", dialect="postgres")
