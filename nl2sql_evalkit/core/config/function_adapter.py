"""How your pipeline function is called and how its answer is read."""
from nl2sql_evalkit.core.config.base import Settings


class FunctionAdapterSettings(Settings):
    """Options for calling your pipeline function: which parameters it takes and where its answer is."""

    # Answer extraction: keys tried when fn() returns a dict/object
    answer_keys: list[str] = [
        "sql", "query", "answer", "response", "output", "result", "text",
        "content", "message", "generated_text", "generation", "completion",
    ]

    # Written reply extraction: keys tried, after the SQL, when fn() returns a dict/object. The reply is scored against the
    # reply style, so a function that returns {"sql": ..., "summary": ...} has its summary read as the reply.
    reply_keys: list[str] = [
        "summary", "response", "reply", "message", "explanation", "final_response",
    ]

    # Signature detection: parameter name aliases
    history_params: list[str] = [
        "history", "chat_history", "messages", "conversation", "turns", "context",
    ]
    session_params: list[str] = [
        "session_id", "session", "thread_id", "conversation_id", "user_id",
    ]

    # History format passed to fn()
    # "dict"  → [{"question": "...", "answer": "..."}]  (default, simple)
    # "openai" → [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    history_format: str = "dict"

