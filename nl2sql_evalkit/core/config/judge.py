"""The AI judge: which model grades answers, and how it is called."""
from nl2sql_evalkit.core.config.base import Settings


class JudgeSettings(Settings):
    """Options for the LLM judge: model, credentials and prompts."""

    # Any LiteLLM model string: "groq/...", "gemini/...", "openai/...", "ollama/..."
    judge_model: str = "groq/openai/gpt-oss-120b"
    judge_api_key: str = ""        # optional; LiteLLM also reads env vars automatically
    judge_prompt_override: str = ""  # replaces the built-in grading rubric when set; the JSON reply format is always added
    judge_temperature: float | None = None   # None: the model's own default is used
    judge_retries: int = 3
    judge_schema_chars: int = 6000   # how much of the schema the assistant looked at the judge reads per question
    judge_reply_chars: int = 4000    # how much of the written reply the judge reads per question
    reply_style: str = ""            # how every written reply should read (a test case's own reply style wins); empty: replies are not scored

    # Override the LLM summary prompt (the one that writes the run's watch-outs and suggestions).
    summary_prompt: str = ""
