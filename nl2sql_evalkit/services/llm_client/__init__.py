"""Calling language models through LiteLLM: a safe one-time load and a single ``complete()`` call."""
from nl2sql_evalkit.services.llm_client.completion import complete
from nl2sql_evalkit.services.llm_client.loader import load_litellm

__all__ = ["complete", "load_litellm"]
