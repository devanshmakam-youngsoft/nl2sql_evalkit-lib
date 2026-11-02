"""``step()``: time a stage of your pipeline and record what went in and came out."""
import inspect
import time as _time
from functools import wraps
from typing import Any

from nl2sql_evalkit.services.evaluation.step_recorder.limits import display_text
from nl2sql_evalkit.services.evaluation.step_recorder.recorder import current_recorder
from nl2sql_evalkit.services.evaluation.step_recorder.redaction import is_secret_name


class StepContext:
    """
    The object returned by step("name").

    Dual-mode:
      • context manager  → developer controls timing manually with `with`
      • decorator        → wraps a function; timing + I/O captured automatically

    Public attribute (readable/writable in context-manager mode):
      .output  — what this step produced, shown in the results

    Setting .output marks the step as "selected", so it is always recorded even in record_detail="selected" mode.
    A decorated function's return value is its output.
    """

    def __init__(self, name: str):
        self.name = name
        self._output: str = ""
        self._output_explicit: bool = False
        self.inputs: dict = {}    # only populated when used as a decorator
        self._start: float = 0.0
        # take hold of the question's recorder now, so the step still belongs to it if it ends in another thread
        self._rec = current_recorder()
        self._seq = self._rec.next_seq() if self._rec is not None else 0

    @property
    def output(self) -> str:
        """What this step produced, as shown in the results (cut to the display limit).

        Assigning to it marks the step as selected, so it is kept even when ``record_detail="selected"``.
        """
        return self._output

    @output.setter
    def output(self, value) -> None:
        self._output = display_text(value)
        self._output_explicit = True

    def _emit(self, elapsed: float) -> None:
        rec = self._rec
        if rec is None or not rec.open:
            return
        detail = rec.detail

        if detail == "off":
            # Only record name and timing; skip all content.
            entry = {"name": self.name, "elapsed": elapsed}
        else:
            if detail == "selected" and not self._output_explicit:
                return        # only steps that produced an output (decorated, or `s.output = ...`)
            entry = {
                "name":     self.name,
                "elapsed":  elapsed,
                "inputs":   self.inputs  if detail == "all" else {},
                "output":   self.output  if detail == "all" else "",
            }
        with rec.lock:
            rec.steps.append((self._seq, entry))

    # --- context manager ---
    def __enter__(self):
        self._start = _time.perf_counter()
        return self  # `as s` → developer can set s.output

    def __exit__(self, *_):
        # Runs even if the body raised — timing is always recorded.
        self._emit(round(_time.perf_counter() - self._start, 3))

    # --- decorator (sync + async) ---
    def __call__(self, fn):
        """Wrap ``fn`` (sync or async) so every call is timed and its inputs and output are recorded.

        Parameters with secret-looking names are recorded as ``[REDACTED]``. Each call is recorded as its own
        step, and the wrapped function's result and exceptions pass through untouched.
        """
        # Capture the signature once at decoration time (not per call).
        sig = inspect.signature(fn)

        def _capture_inputs(args, kwargs) -> dict:
            """Bind call args to param names; redact secret-named params."""
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                return {
                    k: "[REDACTED]" if is_secret_name(k) else display_text(v)
                    for k, v in bound.arguments.items()
                }
            except Exception:
                return {}

        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs) -> Any:
                ctx = StepContext(self.name)
                ctx.inputs = _capture_inputs(args, kwargs)
                ctx._start = _time.perf_counter()
                result = None
                try:
                    result = await fn(*args, **kwargs)
                    return result
                finally:
                    ctx.output = result
                    ctx._emit(round(_time.perf_counter() - ctx._start, 3))
            return async_wrapper

        @wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            ctx = StepContext(self.name)
            ctx.inputs = _capture_inputs(args, kwargs)
            ctx._start = _time.perf_counter()
            result = None
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                ctx.output = result
                ctx._emit(round(_time.perf_counter() - ctx._start, 3))
        return wrapper


def step(name: str) -> StepContext:
    """
    Record a named pipeline step's execution time, inputs and output.

    As a decorator::

        @nl2sql_evalkit.step("schema_lookup")       # timing, inputs and the return value
        def pick_tables(question): ...

    As a context manager::

        with nl2sql_evalkit.step("write_sql") as s:
            sql = llm.generate(prompt)
            s.output = sql

    Works from any thread (a step run in a thread pool still belongs to the question being evaluated).
    No-op when called outside an active eval run (zero overhead in production).
    Secret-named parameters (password, token, key, etc.) are auto-redacted.
    """
    return StepContext(name)
