"""nl2sql_evalkit — evaluate any text-to-SQL assistant. The SQL is read and checked, never run.

Quickstart::

    import nl2sql_evalkit

    def my_text_to_sql(question):
        return pipeline.run(question)       # SQL, or a message when it asks back or declines

    nl2sql_evalkit.serve(my_text_to_sql, dialect="postgres")

With step timing::

    @nl2sql_evalkit.step("pick_tables")
    def pick_tables(question):
        return schema_search(question)

    with nl2sql_evalkit.step("write_sql") as s:
        sql = llm.generate(prompt)
        s.output = sql
"""
from nl2sql_evalkit.core.exceptions import (
    ConfigError,
    DatasetError,
    EvalKitError,
    JudgeError,
    RunBusy,
    RunError,
    StoreError,
    VersionNotFound,
)
from nl2sql_evalkit.launcher import serve
from nl2sql_evalkit.services.evaluation.step_recorder import note, step

__version__ = "0.1.4"
__all__ = [
    "serve", "step", "note", "__version__",
    # exceptions
    "EvalKitError",
    "ConfigError",
    "DatasetError",
    "StoreError", "VersionNotFound",
    "RunError", "RunBusy",
    "JudgeError",
]
