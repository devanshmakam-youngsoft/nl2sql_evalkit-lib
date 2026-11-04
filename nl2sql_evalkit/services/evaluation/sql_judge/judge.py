"""
LLM-as-judge: scores each reply and writes the findings of a run.

WHY LiteLLM?
  A single unified API for Groq, Gemini, OpenAI, Ollama, etc. The developer changes one string
  ("groq/..." -> "gemini/...") to switch providers; no SDK swapping, no credential rework.

WHY json_mode with a prompt-level instruction as fallback?
  Some providers reject `response_format` entirely and throw an error. The try/except lets the prompt-level
  "Respond ONLY with a JSON object" instruction serve as a silent fallback so grading still works.

WHY SqlGrade is a Pydantic model?
  `json.loads(raw)` gives a dict but doesn't validate types or ranges. SqlGrade(...) enforces sql_marks in [0, 10]
  and rejects garbage responses before they corrupt the results store. If the LLM returns bad JSON the retry
  loop (_with_retries) tries again rather than storing broken data.
"""
import json
import logging
import time
from typing import Any

from nl2sql_evalkit.core.exceptions import JudgeError
from nl2sql_evalkit.prompts.sql_judge import (
    decline_prompt,
    grader_format,
    grader_prompt,
    reply_format,
    reply_prompt,
    run_summary_format,
    run_summary_prompt,
)
from nl2sql_evalkit.services.evaluation.sql_judge.grading_input import grading_input
from nl2sql_evalkit.services.evaluation.sql_judge.insights import check_insights, parse_insights
from nl2sql_evalkit.services.evaluation.sql_judge.reply_input import reply_input
from nl2sql_evalkit.services.evaluation.sql_judge.schemas import ReplyGrade, SqlGrade
from nl2sql_evalkit.services.llm_client import complete

logger = logging.getLogger(__name__)


class Judge:
    """The AI model that scores replies and writes a run's findings.

    Every call goes through LiteLLM with the model and key from ``config`` and is retried on failure, sleeping
    between attempts, so the methods block; they are meant to be called from the run's background thread.
    """

    def __init__(self, config):
        self.config = config
        self._grader_prompt = (config.judge_prompt_override or grader_prompt) + grader_format
        self._decline_prompt = decline_prompt + grader_format
        self._reply_prompt = reply_prompt + reply_format

    def _call(self, messages: list[dict], json_mode: bool = False) -> str:
        return complete(
            messages, model=self.config.judge_model, api_key=self.config.judge_api_key,
            temperature=self.config.judge_temperature, json_mode=json_mode,
        )

    def _with_retries(self, fn) -> Any:
        last = None
        for attempt in range(self.config.judge_retries):
            try:
                return fn()
            except Exception as e:
                last = e
                logger.warning("Judge call failed (attempt %d): %s", attempt + 1, e)
                if attempt + 1 < self.config.judge_retries:
                    time.sleep(2 * (attempt + 1))
        raise JudgeError(f"Judge failed after {self.config.judge_retries} attempts: {last}") from last

    def grade_sql(self, question: str, case: dict, reply: str, checks: dict, schema_context: str = "",
                  lookup: dict | None = None) -> SqlGrade:
        """Score one reply to a test case: how well the SQL answers the question, why, and what to change.

        For a ``clarify`` or ``refuse`` case the reply (which holds no SQL) is scored on whether it does that. A call that
        fails, or a reply that is not valid JSON or not a valid ``SqlGrade``, is retried up to ``judge_retries`` times.

        Args:
            question: The question that was asked.
            case: The test case: ``type``, ``expected_sql``, ``expected_tables`` and ``expected_columns``.
            reply: What the assistant returned.
            checks: The findings of ``check_sql`` for this reply, which the judge is told about.
            schema_context: The tables and columns the assistant looked at before writing the SQL, when it recorded them.
            lookup: The findings of ``schema_lookup`` on that schema (which expected tables and columns it lacked).

        Raises:
            JudgeError: When every attempt fails.
        """
        user = grading_input(
            question, case.get("type", ""), case.get("expected_sql", ""), case.get("expected_tables", ""),
            case.get("expected_columns", ""), reply, checks, self.config.dialect,
            schema_context=schema_context, lookup=lookup, schema_chars=self.config.judge_schema_chars,
        )
        system = self._grader_prompt if checks["returned_sql"] else self._decline_prompt

        def _invoke() -> SqlGrade:
            raw = self._call([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=True)
            return SqlGrade(**json.loads(raw))

        return self._with_retries(_invoke)

    def grade_reply(self, question: str, reply_style: str, reply_text: str, sql: str = "", case_type: str = "answer") -> ReplyGrade:
        """Score the written reply of one question against the style the developer asked for, with the reason and a suggestion.

        Nothing is run, so the judge reads the reply for style, consistency with the question and the SQL, and clarity; it
        cannot check figures against data. A call that fails, or a reply that is not valid JSON or not a valid
        ``ReplyGrade``, is retried up to ``judge_retries`` times.

        Args:
            question: The question that was asked.
            reply_style: How the reply should read, written by the developer.
            reply_text: The written reply (the summary, or the message when the assistant asked back or declined).
            sql: The SQL that came with the reply, empty when there is none.
            case_type: ``answer``, ``clarify`` or ``refuse``: what the assistant should have done.

        Raises:
            JudgeError: When every attempt fails.
        """
        user = reply_input(question, reply_style, reply_text, sql, case_type, self.config.judge_reply_chars)

        def _invoke() -> ReplyGrade:
            raw = self._call([{"role": "system", "content": self._reply_prompt}, {"role": "user", "content": user}], json_mode=True)
            return ReplyGrade(**json.loads(raw))

        return self._with_retries(_invoke)

    def summarize_run(self, stats: str) -> dict | None:
        """Findings for a finished run: ``{"items": [{"watch_out", "suggestion"}, ...], "pitfalls": [...], "suggestions": [...]}``,
        every watch-out paired with the suggestion that answers it (the two lists repeat the pairs' parts).

        A reply that is not usable (not JSON, or one of the lists empty) is sent back with the reason so the model
        can fix it, up to ``judge_retries`` times (at least twice). If the model never fills both lists, what it did
        give is returned (the caller can add the missing suggestions); None only when nothing usable came back."""
        system = (self.config.summary_prompt or run_summary_prompt) + run_summary_format
        messages = [{"role": "system", "content": system}, {"role": "user", "content": stats}]
        attempts = max(2, self.config.judge_retries)
        partial: dict | None = None
        problem = "no reply"
        for attempt in range(attempts):
            try:
                raw = self._call(messages, json_mode=True)
            except Exception as e:  # network, rate limit, provider error
                problem = f"the model could not be reached: {e}"
                logger.warning("Run summary call failed (attempt %d): %s", attempt + 1, e)
                time.sleep(2 * (attempt + 1))
                continue
            insights, problem = check_insights(raw)
            if insights is not None:
                return insights
            partial = parse_insights(raw) or partial
            logger.warning("Run summary reply rejected (attempt %d): %s", attempt + 1, problem)
            messages = messages + [
                {"role": "assistant", "content": raw or ""},
                {"role": "user", "content": f"That reply was rejected: {problem}. Reply again with JSON only, in the required shape."},
            ]
        if partial is not None:
            logger.warning("Run summary incomplete after %d attempts (%s); using what the model gave", attempts, problem)
            return partial
        logger.error("Run summary generation failed: %s", problem)
        return None
