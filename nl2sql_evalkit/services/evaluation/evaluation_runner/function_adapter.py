"""Calling your pipeline function: which arguments it takes, how its answer is read, how history is passed."""
import asyncio
import inspect
from typing import Any, Callable

from nl2sql_evalkit.services.evaluation.sql_checks import split_reply


def detect_call_style(fn: Callable, session_aliases: list[str], history_aliases: list[str]) -> str:
    """Returns 'session_id' | 'history' | 'question' based on fn's parameter names.

    Priority: session_id > history > question.
    A function that accepts a session_id is assumed to be stateful (manages its own
    conversation history); the runner still builds history but passes it only to
    functions that explicitly declare a history parameter.
    """
    s_aliases, h_aliases = set(session_aliases), set(history_aliases)
    params = set(inspect.signature(fn).parameters)
    if params & s_aliases:
        return "session_id"
    if params & h_aliases:
        return "history"
    return "question"


def parameter_name_for(fn: Callable, aliases: set[str]) -> str:
    """Return the actual parameter name from fn that matches one of the aliases."""
    matched = set(inspect.signature(fn).parameters) & aliases
    return next(iter(matched), list(aliases)[0])


def answer_text_of(result, answer_keys: list[str]) -> str:
    """
    Turn any text-to-SQL function's return value into a plain string.
    Handles str, dict (tries answer_keys in order), pydantic model, or any object.
    """
    keys = answer_keys
    if isinstance(result, str):
        return result
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif hasattr(result, "dict") and callable(result.dict):
        try:
            result = result.dict()
        except Exception:
            pass
    if isinstance(result, dict):
        for key in keys:
            if result.get(key) not in (None, ""):
                return str(result[key]) if not isinstance(result[key], str) else result[key]
        import json
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)
    for key in keys:
        val = getattr(result, key, None)
        if val is not None:
            return str(val)
    return str(result)


def reply_text_of(result, answer_keys: list[str], reply_keys: list[str], answer: str) -> str:
    """The written reply that came with the SQL: what the assistant says to the user.

    A dict or object result is searched for ``reply_keys`` in order, skipping the key the SQL itself was read from, so
    ``{"sql": ..., "summary": ...}`` gives the summary. Otherwise it is the text of the answer that is not SQL: a message
    sent alone (a question back, a refusal) is all of it, and a message around fenced SQL is what is left of it.

    Args:
        result: What ``fn()`` returned.
        answer_keys: The keys the SQL (the answer) is read from, as used for ``answer``.
        reply_keys: The keys the written reply is read from.
        answer: The answer text already read from ``result``.
    """
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    if isinstance(result, dict):
        fields = result
    elif isinstance(result, str) or result is None:
        fields = {}
    else:
        fields = {key: getattr(result, key, None) for key in (*answer_keys, *reply_keys)}
    used = next((k for k in answer_keys if fields.get(k) not in (None, "")), None)
    for key in reply_keys:
        value = fields.get(key)
        if key != used and value not in (None, "") and str(value).strip():
            return str(value).strip()
    return split_reply(answer)[1]


def call_sync(fn: Callable, *args, **kwargs) -> Any:
    """Call ``fn`` and return its result, running it to completion first when it is an ``async def``.

    If an event loop is already running in the calling thread, the coroutine runs on a fresh loop in a helper
    thread (blocking until it finishes); otherwise it runs on this thread's loop, or a new one if there is none.
    A plain function is simply called.
    """
    if inspect.iscoroutinefunction(fn):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, fn(*args, **kwargs)).result()
            return loop.run_until_complete(fn(*args, **kwargs))
        except RuntimeError:
            return asyncio.run(fn(*args, **kwargs))
    return fn(*args, **kwargs)


def format_history(turns: list[dict], fmt: str) -> list[dict]:
    """
    Convert internal history to the format the developer's function expects.

    fmt="dict"   → [{"question": "...", "answer": "..."}]   (default)
    fmt="openai" → [{"role": "user", "content": "..."},
                    {"role": "assistant", "content": "..."}]
    """
    if fmt == "openai":
        msgs = []
        for t in turns:
            msgs.append({"role": "user",      "content": t.get("question", "")})
            msgs.append({"role": "assistant", "content": t.get("answer",   "")})
        return msgs
    return list(turns)  # default "dict" format
