"""nl2sql_evalkit — evaluate any RAG pipeline, chatbot, or multi-agent system.

Quickstart::

    import nl2sql_evalkit

    def my_rag(question):
        return pipeline.run(question)

    nl2sql_evalkit.serve(my_rag)

With step recording::

    @nl2sql_evalkit.step("retriever")
    def retrieve(query):
        return vector_db.search(query)

    with nl2sql_evalkit.step("llm") as s:
        answer = llm.generate(query)
        s.material = retrieved_context
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
