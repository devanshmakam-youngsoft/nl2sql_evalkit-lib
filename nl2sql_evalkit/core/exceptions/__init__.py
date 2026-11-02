"""Every error the library raises. They all inherit from ``RagevalError``, one file per area.

    base                   RagevalError, ConfigError, InvalidInput, NotFoundError, TooLargeError
    spreadsheet_loader     DatasetError
    document_reader        DocumentError
    db_services            StoreError, VersionNotFound, ConflictError, GroupNotFound
    evaluation_runner      RunError, RunBusy, NoDatasetError
    testcase_generator     GenerationError, GenerationBusy
    sql_judge           JudgeError

``handlers.py`` turns an error into the HTTP answer the dashboard shows. The supported way for library users to import
an error is from the top level: ``from nl2sql_evalkit import RagevalError, JudgeError``.
"""
from nl2sql_evalkit.core.exceptions.base import (
    ConfigError,
    InvalidInput,
    NotFoundError,
    RagevalError,
    TooLargeError,
)
from nl2sql_evalkit.core.exceptions.db_services import (
    ConflictError,
    GroupNotFound,
    StoreError,
    VersionNotFound,
)
from nl2sql_evalkit.core.exceptions.document_reader import DocumentError
from nl2sql_evalkit.core.exceptions.evaluation_runner import NoDatasetError, RunBusy, RunError
from nl2sql_evalkit.core.exceptions.handlers import register_error_handlers
from nl2sql_evalkit.core.exceptions.spreadsheet_loader import DatasetError
from nl2sql_evalkit.core.exceptions.sql_judge import JudgeError
from nl2sql_evalkit.core.exceptions.testcase_generator import GenerationBusy, GenerationError

__all__ = [
    "ConfigError", "ConflictError", "DatasetError", "DocumentError", "GenerationBusy", "GenerationError",
    "GroupNotFound", "InvalidInput", "JudgeError", "NoDatasetError", "NotFoundError", "RagevalError",
    "RunBusy", "RunError", "StoreError", "TooLargeError", "VersionNotFound", "register_error_handlers"
]
