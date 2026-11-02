"""Reading uploaded schema files (.sql, .ddl) into tables, columns and keys that questions can be written from.

Only the structure is used and nothing is kept: the uploaded file is deleted as soon as it has been read. No database is
connected and no data is read; a dump that contains data is fine, the data is ignored.
"""
from nl2sql_evalkit.core.constants import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from nl2sql_evalkit.core.exceptions import SchemaError
from nl2sql_evalkit.services.testcases.schema_reader.models import (
    Column,
    ForeignKey,
    ReadSchema,
    Table,
)
from nl2sql_evalkit.services.testcases.schema_reader.parser import read_schema

__all__ = ["Column", "ForeignKey", "ReadSchema", "SUPPORTED_MESSAGE", "SUPPORTED_SUFFIXES", "SchemaError", "Table", "read_schema"]
