"""What ``step()`` and ``note()`` capture while your pipeline runs."""
from nl2sql_evalkit.core.config.base import Settings


class RecordingSettings(Settings):
    """Options for step recording: when it is active, how much each step keeps and the size limits."""

    # Recording mode (controls what @step captures during eval runs)
    # "eval"     — record steps only during eval runner calls (default)
    # "uat"      — reserved; behaves like "eval"
    # "off"      — disable all step recording (eval still runs, just no step data)
    record_mode: str = "eval"

    # Recording detail level (controls HOW MUCH is captured per step)
    # "all"      — inputs, outputs, timing (default)
    # "selected" — only steps that produced an output (decorated, or `s.output = ...`)
    # "off"      — only step name + elapsed time (no content captured)
    record_detail: str = "all"

    # How much of a step is kept. Shown inputs, outputs and notes are cut at step_value_chars; a cut always ends
    # with a marker saying how much was left out.
    step_value_chars: int = 1000

    # How much of the schema a step looked at is kept with a question's result (see step(..., schema=True)).
    schema_chars: int = 20000
