"""Reading test case spreadsheets into a validated table."""
from nl2sql_evalkit.core.exceptions import DatasetError
from nl2sql_evalkit.services.testcases.spreadsheet_loader.legacy_datasets import (
    describe_default_dataset,
    describe_uploaded_dataset,
    import_uploaded_dataset,
)
from nl2sql_evalkit.services.testcases.spreadsheet_loader.loader import (
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    load_dataset,
)
from nl2sql_evalkit.services.testcases.spreadsheet_loader.uploads import (
    load_spreadsheet,
    load_uploaded_spreadsheet,
)

__all__ = [
    "DatasetError", "OPTIONAL_COLUMNS", "REQUIRED_COLUMNS", "describe_default_dataset",
    "describe_uploaded_dataset", "import_uploaded_dataset", "load_dataset", "load_spreadsheet",
    "load_uploaded_spreadsheet"
]
