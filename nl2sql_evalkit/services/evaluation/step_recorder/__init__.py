"""
Step recording — the zero-overhead observability layer for nl2sql_evalkit.

HOW IT WORKS
------------
`nl2sql_evalkit.step("name")` returns a StepContext that records nothing unless a question is being evaluated.

When the RunManager calls the developer's function it:
  1. calls begin_question(detail)  → opens a fresh recorder for this question
  2. calls fn(question)       → developer code runs; any @step / with step: adds its entry to that recorder
  3. calls end_question()      → closes the recorder (in a finally block — always runs)
  4. calls collect_question()         → returns {"steps": [...], "flags": {...}} from the closed recorder

WHY a recorder per question, not per thread
------------------------------------------
The runner handles ONE question at a time (and one run at a time), so everything recorded while ``fn()`` is
running belongs to that question, whichever thread records it. Pipelines often search several indexes in a
thread pool, or hand work to an executor; a step started there still lands in the current question's recorder.
Each step takes hold of its recorder when it STARTS, so a slow leftover thread from question 1 can never add
its step to question 2: once a question is collected its recorder is closed and late steps are ignored.

WHY end_question() is in a finally block in runner.py
-----------------------------------------------------
If fn() raises an exception the finally block still closes the recorder, so the next question's
begin_question() starts with a clean slate rather than accumulating stale steps from a failed call.

WHAT IS KEPT OF A STEP
----------------------
Its name and time, its inputs and its output: a decorated function's return value, or ``s.output = ...`` inside
``with step(...)``. Displayed inputs, outputs and notes are cut at ``max_step_value_chars`` (default 1,000) with a
visible marker saying how much was left out.

THE SCHEMA A STEP LOOKED AT
---------------------------
A step may say which tables and columns it looked at: ``s.schema = ...`` inside ``with step(...)``, or
``@step("schema_lookup", schema=True)`` which takes the decorated function's return value. A list or a dict is written
out as readable lines. The schemas of all the steps that declared one are joined, cut at ``max_schema_chars``
(default 20,000) with a visible marker, and kept with the question's result. When no step declares a schema nothing
is recorded and the schema lookup score is simply not given. With ``record_detail="off"`` no content is kept, so
none is scored either.

SECRET BLANKING
---------------
Any step input parameter whose name contains a secret-related keyword
(password, token, key, secret, auth, bearer, credential) is replaced with
"[REDACTED]" before storing.

RECORDING DETAIL LEVELS
------------------------
"all"      — capture inputs, outputs, timing (default)
"selected" — only emit steps that produced an output (decorated, or ``s.output = ...``)
"off"      — only record step name + elapsed time (no content)
"""
from nl2sql_evalkit.services.evaluation.step_recorder.limits import (
    LIMITS,
    clip_schema,
    configure,
    display_text,
)
from nl2sql_evalkit.services.evaluation.step_recorder.notes import note
from nl2sql_evalkit.services.evaluation.step_recorder.recorder import (
    begin_question,
    collect_question,
    end_question,
)
from nl2sql_evalkit.services.evaluation.step_recorder.schema_text import joined_schema
from nl2sql_evalkit.services.evaluation.step_recorder.steps import step

__all__ = [
    "LIMITS", "begin_question", "clip_schema", "collect_question", "configure", "display_text", "end_question",
    "joined_schema", "note", "step",
]
