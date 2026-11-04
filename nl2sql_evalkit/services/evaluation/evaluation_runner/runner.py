"""RunManager: runs test cases through your function on a background thread and saves what it finds."""
import logging
import threading
import time
import uuid
from typing import Callable

import pandas as pd

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.core.constants import ANSWER, parse_type
from nl2sql_evalkit.core.diagnostics import EventLog
from nl2sql_evalkit.core.exceptions import JudgeError, RunBusy
from nl2sql_evalkit.services.db_services import EvalStore
from nl2sql_evalkit.services.evaluation import step_recorder
from nl2sql_evalkit.services.evaluation.evaluation_runner.function_adapter import (
    answer_text_of,
    call_sync,
    detect_call_style,
    format_history,
    parameter_name_for,
    reply_text_of,
)
from nl2sql_evalkit.services.evaluation.evaluation_runner.run import Run, light_row
from nl2sql_evalkit.services.evaluation.run_summarizer import build_group_stats, build_summary
from nl2sql_evalkit.services.evaluation.sql_checks import (
    check_sql,
    gate,
    schema_lookup,
    schema_use_marks,
)
from nl2sql_evalkit.services.evaluation.sql_judge import (
    Judge,
    finish_insights,
    parse_cause,
    stats_for_llm,
)

logger = logging.getLogger(__name__)


class RunManager:
    """
    Drives evaluation runs.

    Runtime hooks (all optional, passed via ``create_app``):

    * ``judge_fn(question, expected_sql, reply, checks) -> dict``
        Replaces the LLM judge for scoring replies.  The dict must contain at least
        ``sql_marks`` (int 0–10).  Optional keys: ``sql_comment``, ``suggestion``.  A reply that fails a basic check
        (no SQL, SQL that does not parse, SQL that is not read-only) is scored 0 without calling it.  The judge model
        is still used for the run's written findings.

    * ``reply_judge_fn(question, reply_style, reply_text, sql) -> dict``
        Replaces the LLM judge for scoring the written reply against the reply style. The dict must contain
        ``reply_marks`` (int 0–10); optional keys: ``reply_comment``, ``suggestion``. Called only for questions that
        have a reply style, and not when the assistant wrote no reply (that scores 0).

    * ``extra_metrics: dict[str, Callable[[str, str], float]]``
        Additional metrics run alongside built-ins.
        Each callable receives ``(expected_sql, generated_answer)``
        and should return a float.  Example::

            extra_metrics={"rouge_1": compute_rouge1, "bleu": compute_bleu}

    * ``on_complete(summary: dict | None, rows: list[dict]) -> None``
        Called once after a run completes, or fails (then ``summary`` is None and ``rows`` holds what was
        graded so far).  Not called when a run is stopped.
        Use it to send notifications, write to a database, trigger CI, etc.

    * ``session_id_fn(chat_id: str) -> str``
        Returns the session ID for a chat.  Defaults to ``uuid.uuid4()``.
        Supply a deterministic function to replay conversations against a
        stateful backend with the same session every time.
    """

    def __init__(
        self,
        config: Config,
        store: EvalStore,
        fn: Callable,
        *,
        judge_fn: Callable | None = None,
        reply_judge_fn: Callable | None = None,
        extra_metrics: dict[str, Callable] | None = None,
        on_complete: Callable | None = None,
        session_id_fn: Callable | None = None,
    ):
        self.config = config
        self.store  = store
        self.fn     = fn

        # --- callable hooks ---
        self._judge_fn      = judge_fn
        self._reply_judge_fn = reply_judge_fn
        self._extra_metrics = extra_metrics or {}
        self._on_complete   = on_complete
        self._session_id_fn = session_id_fn or (lambda chat_id: str(uuid.uuid4()))

        # --- config-derived ---
        self._answer_keys   = list(config.answer_keys)
        self._reply_keys    = list(config.reply_keys)
        self._s_aliases     = set(config.session_params)
        self._h_aliases     = set(config.history_params)
        self._history_fmt   = config.history_format
        self._record_detail = config.record_detail
        self._record_mode   = config.record_mode
        step_recorder.configure(max_step_value_chars=config.step_value_chars, max_schema_chars=config.schema_chars)

        # Detect once at startup — inspection is expensive; cache the result.
        self._sig = detect_call_style(fn, self._s_aliases, self._h_aliases)
        # Cache the exact param name so _call_fn can pass it as a keyword arg.
        self._session_kwarg = parameter_name_for(fn, self._s_aliases) if self._sig == "session_id" else "session_id"
        self._history_kwarg = parameter_name_for(fn, self._h_aliases) if self._sig == "history" else "history"

        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self._llm_judge: Judge | None = None

    # ---

    @property
    def judge(self) -> Judge:
        """The LLM judge, created on first use and then reused for every run."""
        if self._llm_judge is None:
            self._llm_judge = Judge(self.config)
        return self._llm_judge

    def active(self) -> Run | None:
        """Return the run that is currently going, or None. Only one run may be active at a time."""
        return next((r for r in self.runs.values() if r.status == "running"), None)

    def start(
        self,
        version: str,
        df: pd.DataFrame,
        dataset_name: str,
        *,
        notes: str = "",
        group_names: list[str] | None = None,
        from_library: bool = False,
        dataset_id: str = "",
    ) -> Run:
        """Start a run in a background thread and return it at once, while it is still running.

        Progress and the outcome are published on the returned ``Run``. The results are saved to the store when
        the run completes (or, partially, when it is stopped).

        Args:
            version: The version name the results are saved under.
            df: The test cases to run, one row per question, in the order they are asked.
            dataset_name: A label for where the test cases came from, shown with the results.
            notes: Free text saved with the run's summary.
            group_names: The groups the test cases were taken from, for per-group statistics.
            from_library: True when ``df`` was resolved from test cases already in the store
                (groups and/or picked cases), so it is not imported again.
            dataset_id: The source group's id when the run came from exactly one group.

        Raises:
            RunBusy: When another run is still going.
        """
        with self._lock:
            if self.active():
                raise RunBusy("Another evaluation is already running")
            run = Run(version, len(df), dataset_name)
            run.log = EventLog(self.config, "runs", version)
            run.notes = notes
            run.group_names = group_names or []
            run.from_library = from_library
            run.dataset_id = dataset_id
            self.runs[run.run_id] = run
        threading.Thread(
            target=self._execute_and_close_log, args=(run, df), daemon=True, name=f"eval-{version}"
        ).start()
        return run

    def _execute_and_close_log(self, run: Run, df: pd.DataFrame) -> None:
        try:
            self._execute(run, df)
        finally:
            run.log.info("Run %s %s after %d of %d questions, %d problems", run.version, run.status, run.done, run.total, run.log.issue_total)
            run.log.close()

    # ---

    def _call_fn(
        self, question: str, history: list[dict], session_id: str
    ) -> tuple[str, float, dict, dict, dict, dict, str, str]:
        """Call the developer's function; return (answer, elapsed, node_timings, step_inputs, step_outputs, flags,
        schema_context, reply_text): the schema the steps declared they looked at (empty when none did) and the
        written reply that came with the SQL (empty when there is none)."""
        _recording_active = self._record_mode != "off"
        if _recording_active:
            step_recorder.begin_question(detail=self._record_detail)
        t0  = time.perf_counter()
        exc = None
        result = None
        try:
            fmt_history = format_history(history, self._history_fmt)
            if self._sig == "session_id":
                # Stateful backend — passes only the session token; backend owns history.
                result = call_sync(self.fn, question, **{self._session_kwarg: session_id})
            elif self._sig == "history":
                # Stateless backend — runner passes the full conversation history each turn.
                result = call_sync(self.fn, question, **{self._history_kwarg: fmt_history})
            else:
                result = call_sync(self.fn, question)
        except Exception as e:
            exc = e
        finally:
            if _recording_active:
                step_recorder.end_question()

        elapsed   = round(time.perf_counter() - t0, 3)
        collected = step_recorder.collect_question()
        steps     = collected["steps"]
        flags     = collected["flags"]

        if exc is not None:
            raise exc

        answer = answer_text_of(result, self._answer_keys)
        if result is not None and not isinstance(result, str):
            logger.info(
                "fn() returned %s — extracted answer string via answer_keys. "
                "Pass answer_keys= to serve() to customise.",
                type(result).__name__,
            )

        # A step that ran several times (an agent calling a tool in a loop, or the same search in parallel threads)
        # has its time added up: this is the time spent in that step.
        node_timings: dict[str, float] = {}
        for s in steps:
            node_timings[s["name"]] = round(node_timings.get(s["name"], 0.0) + s["elapsed"], 3)
        step_inputs  = {s["name"]: s.get("inputs", {}) for s in steps}
        step_outputs = {s["name"]: s.get("output",  "") for s in steps}
        reply_text = reply_text_of(result, self._answer_keys, self._reply_keys, answer)
        return answer, elapsed, node_timings, step_inputs, step_outputs, flags, step_recorder.joined_schema(steps), reply_text

    def _grade_sql(self, row, out: dict, case_type: str, run: Run, where: str) -> dict:
        """The SQL score of one reply with the reason and a suggestion: 0 for a failed question or a reply that fails a basic
        check, else judge_fn if provided, otherwise the LLM judge."""
        if out["status"] != "ok":
            return {"sql_marks": 0, "sql_comment": "No reply: the function raised an error.", "suggestion": "", "cause": "none"}
        checks = out["sql_checks"]
        stopped = gate(checks, case_type, self.config.dialect)
        if stopped:
            return {"sql_marks": stopped[0], "sql_comment": stopped[1], "suggestion": stopped[2], "cause": "none"}
        reply = out.get("generated_answer") or ""
        if self._judge_fn is not None:
            try:
                raw = call_sync(self._judge_fn, row.question, row.expected_sql, reply, checks)
                if not isinstance(raw, dict):
                    raw = {"sql_marks": int(raw)}
                return {"sql_marks": int(raw.get("sql_marks", 0)), "sql_comment": str(raw.get("sql_comment", "")),
                        "suggestion": str(raw.get("suggestion", "")), "cause": parse_cause(raw.get("cause"))}
            except Exception as e:
                issue = run.log.issue("custom_judge", e, where)
                return {"sql_marks": 0, "sql_comment": issue.message, "suggestion": "", "cause": "none"}
        case = {"type": case_type, "expected_sql": row.expected_sql,
                "expected_tables": out.get("expected_tables", ""), "expected_columns": out.get("expected_columns", "")}
        lookup = out.get("schema_lookup") or {}
        grade = self.judge.grade_sql(row.question, case, reply, checks, schema_context=out.get("schema_context", ""),
                                     lookup=lookup)
        return {"sql_marks": grade.sql_marks, "sql_comment": grade.sql_comment, "suggestion": grade.suggestion,
                "cause": grade.cause}

    def _grade_reply(self, row, out: dict, style: str, case_type: str, run: Run, where: str) -> dict:
        """The reply score of one written reply against its reply style: 0 for a failed question or no written reply, else
        reply_judge_fn if provided, otherwise the LLM judge. A failure of the judge is raised for the caller to record."""
        if out["status"] != "ok":
            return {"reply_marks": 0, "reply_comment": "No reply: the function raised an error.", "suggestion": ""}
        text = out.get("reply_text", "")
        if not text.strip():
            return {"reply_marks": 0, "reply_comment": "The assistant returned no written reply.",
                    "suggestion": "Return a written reply next to the SQL, in the requested style."}
        sql = out.get("generated_sql", "")
        if self._reply_judge_fn is not None:
            try:
                raw = call_sync(self._reply_judge_fn, row.question, style, text, sql)
                if not isinstance(raw, dict):
                    raw = {"reply_marks": int(raw)}
                return {"reply_marks": max(0, min(10, int(raw.get("reply_marks", 0)))),
                        "reply_comment": str(raw.get("reply_comment", "")), "suggestion": str(raw.get("suggestion", ""))}
            except Exception as e:
                issue = run.log.issue("custom_judge", e, f"{where}, reply")
                return {"reply_marks": 0, "reply_comment": issue.message, "suggestion": ""}
        grade = self.judge.grade_reply(row.question, style, text, sql, case_type)
        return {"reply_marks": grade.reply_marks, "reply_comment": grade.reply_comment, "suggestion": grade.suggestion}

    def _process_row(self, row, session_id: str, history: list[dict], run: Run) -> dict:
        where = f"Question {run.done + 1} of {run.total} (chat {row.chat_id}, turn {row.turn_no})"
        out = {
            "chat_id":         row.chat_id,
            "turn_no":         row.turn_no,
            "type":            row.type,
            "question":        row.question,
            "expected_sql": row.expected_sql,
            "session_id":      session_id,
            "status":          "ok",
        }
        tc_id = getattr(row, "tc_id", None)
        if tc_id:
            out["tc_id"] = tc_id  # lets per-group stats find this row even after chat/turn edits
        groups = getattr(row, "groups", None)
        if groups is not None:
            out["groups"] = list(groups)  # the groups this case belonged to when it ran
        for field in ("expected_tables", "expected_columns", "reply_style"):
            value = str(getattr(row, field, "") or "").strip()
            if value and value.lower() != "nan":
                out[field] = value
        # the test case's own reply style wins over the default given to serve()
        style = out.get("reply_style") or self.config.reply_style.strip()
        if style:
            out["reply_style"] = style

        # Carry any extra columns from the row into the receipt
        for col in self.config.extra_columns:
            col_n = col.strip().lower()
            if hasattr(row, col_n):
                out[col_n] = getattr(row, col_n)

        try:
            answer, elapsed, node_timings, step_inputs, step_outputs, flags, schema_context, reply_text = \
                self._call_fn(row.question, history, session_id)
            out.update(
                generated_answer=answer,
                total_time_taken=elapsed,
                node_timings=node_timings,
                step_inputs=step_inputs,
                step_outputs=step_outputs,
                schema_context=schema_context,
                reply_text=reply_text,
            )
            if flags:
                out["flags"] = flags

        except Exception as e:
            issue = run.log.issue("answer", e, where)
            out.update(
                status="generation_failed",
                error_message=issue.message,
                error_detail=issue.technical,
                generated_answer=None,
                schema_context="",
                reply_text="",
                node_timings={},
                step_inputs={},
                step_outputs={},
            )

        # What the SQL says, read without running it, and the tables and columns score
        case_type = parse_type(row.type) or ANSWER
        if out["status"] == "ok":
            checks = check_sql(out.get("generated_answer"), dialect=self.config.dialect, expected_sql=row.expected_sql,
                               expected_tables=out.get("expected_tables", ""), expected_columns=out.get("expected_columns", ""))
            out["sql_checks"], out["generated_sql"] = checks, checks["sql"]
            out["schema_marks"], out["schema_remarks"] = schema_use_marks(
                checks, out.get("expected_tables", ""), out.get("expected_columns", ""), case_type)
            # did the schema the assistant looked at hold what the question needed (only when a step recorded one)
            lookup = schema_lookup(out.get("schema_context", ""), out.get("expected_tables", ""),
                                   out.get("expected_columns", ""), case_type)
            out["lookup_marks"], out["lookup_remarks"] = lookup.pop("marks"), lookup.pop("remarks")
            out["schema_lookup"] = lookup

        # Extra / custom metrics
        if out["status"] == "ok" and self._extra_metrics:
            gen = out.get("generated_answer", "")
            for name, fn in self._extra_metrics.items():
                try:
                    out[name] = call_sync(fn, row.expected_sql, gen)
                except Exception as e:
                    run.log.issue("metric", e, f"{where}, {name}", severity="warning")
                    out[name] = None

        # The SQL score (gates, then LLM judge or custom judge_fn)
        try:
            grade = self._grade_sql(row, out, case_type, run, where)
            out.update(sql_marks=grade["sql_marks"], sql_remarks=grade["sql_comment"], sql_suggestion=grade["suggestion"],
                       sql_cause=grade["cause"])
        except Exception as e:
            issue = run.log.issue("grading", e, where)
            if out["status"] == "ok":
                out["status"] = "grading_failed"
            out.update(sql_remarks=issue.message, error_message=issue.message, error_detail=issue.technical)

        # The reply score: only for a question that has a reply style
        if style:
            try:
                reply_grade = self._grade_reply(row, out, style, case_type, run, where)
                out.update(reply_marks=reply_grade["reply_marks"], reply_remarks=reply_grade["reply_comment"],
                           reply_suggestion=reply_grade["suggestion"])
            except Exception as e:
                issue = run.log.issue("grading", e, f"{where}, reply")
                if out["status"] == "ok":
                    out["status"] = "grading_failed"
                out.update(reply_remarks=issue.message, error_message=issue.message, error_detail=issue.technical)

        return out

    def _execute(self, run: Run, df: pd.DataFrame) -> None:
        rows: list[dict] = []

        # Import this dataset's questions into the test_cases table for traceability.
        # Skip for library runs (the cases already live in the store) and for multi-group runs
        # (import_dataset would create a spurious combined group).
        fingerprint = df.attrs.get("fingerprint", "")
        dataset_id = run.dataset_id
        if not run.from_library and len(run.group_names) <= 1:
            try:
                dataset_id = self.store.import_dataset(run.dataset_name, df, fingerprint)
            except Exception as e:
                run.log.issue("save", e, "importing the questions into the library", severity="warning")

        try:
            run.log.info(
                "Run %s started: %d questions from %s, judge model %s",
                run.version, run.total, run.dataset_name, "custom judge_fn" if self._judge_fn else self.config.judge_model,
            )
            run.emit("started")
            sessions:  dict[str, str]        = {}
            histories: dict[str, list[dict]] = {}

            for row in df.itertuples(index=False):
                # Check if a stop was requested before processing the next row.
                if run.stop_requested:
                    run.status = "stopped"
                    run.current_question = ""
                    run.log.info("Stop requested: stopped after %d of %d questions", run.done, run.total)
                    run.emit("stopped")
                    write_partial_results(self, run, rows, fingerprint, dataset_id)
                    return

                run.current_question = row.question[:120]
                chat_id = row.chat_id
                if chat_id not in sessions:
                    sessions[chat_id]  = self._session_id_fn(chat_id)
                    histories[chat_id] = []

                result = self._process_row(row, sessions[chat_id], histories[chat_id], run)
                if result.get("generated_answer"):
                    histories[chat_id].append({
                        "question": row.question,
                        "answer":   result["generated_answer"],
                    })
                rows.append(result)
                run.done += 1
                run.log.info(
                    "Question %d of %d | chat %s turn %s | %s | answer %s, tables and columns %s, schema lookup %s, reply %s | %ss",
                    run.done, run.total, row.chat_id, row.turn_no, result["status"],
                    result.get("sql_marks"), result.get("schema_marks"), result.get("lookup_marks"), result.get("reply_marks"),
                    result.get("total_time_taken", "-"),
                )
                run.emit("progress", row=light_row(result))

            run.current_question = "Summarising run…"

            summary = build_summary(
                run.version, rows, run.started, run.dataset_name,
                judge_model=self.config.judge_model,
                question_fingerprint=fingerprint,
                dataset_id=dataset_id,
            )
            summary["run_id"] = run.version  # stable identifier used by dashboard actions
            summary["notes"] = run.notes
            summary["group_names"] = run.group_names
            summary["group_stats"] = build_group_stats(self.store, run.group_names, rows)
            insights = self.judge.summarize_run(stats_for_llm(summary, rows))
            if insights:
                insights = finish_insights(insights, summary, rows)      # every watch-out gets its suggestion
                summary["insights"] = insights
                # plain-text version for anything that only reads `comment` (xlsx, on_complete hooks)
                summary["comment"] = "\n".join(
                    f"• {i['watch_out']} → {i['suggestion']}" if i["watch_out"] and i["suggestion"] else f"• {i['watch_out'] or i['suggestion']}"
                    for i in insights["items"])
            else:
                summary["comment"] = "Summary could not be generated for this run."
                run.log.issue("summary", JudgeError("The judge returned no usable summary"), "writing the findings", severity="warning")

            attach_run_log(summary, run)
            self.store.write(run.version, summary, rows)
            run.summary, run.status, run.current_question = summary, "completed", ""
            run.emit("done", summary=summary)

            # on_complete callback
            if self._on_complete is not None:
                try:
                    call_sync(self._on_complete, summary, rows)
                except Exception as e:
                    run.log.issue("callback", e, "on_complete", severity="warning")

        except Exception as e:
            issue = run.log.issue("run", e, f"after {run.done} of {run.total} questions")
            run.status, run.error, run.error_detail = "failed", issue.message, issue.technical
            run.emit("error")

            if self._on_complete is not None:
                try:
                    call_sync(self._on_complete, None, rows)
                except Exception:
                    pass


def attach_run_log(summary: dict, run: Run) -> None:
    """Keep the run's problems and the name of its log file with the saved results."""
    summary["issues"] = run.log.issue_dicts()
    summary["issue_total"] = run.log.issue_total
    summary["log_file"] = run.log.file_name


def write_partial_results(manager: RunManager, run: Run, rows: list[dict], fingerprint: str, dataset_id: str) -> None:
    """Write partial results when a run is stopped early."""
    try:
        summary = build_summary(
            run.version, rows, run.started, run.dataset_name,
            judge_model=manager.config.judge_model,
            question_fingerprint=fingerprint,
            dataset_id=dataset_id,
        )
        summary["comment"] = f"Run stopped after {run.done}/{run.total} rows."
        attach_run_log(summary, run)
        summary["stopped"] = True  # incomplete: never recommended or compared as a finished run
        summary["run_id"] = run.version
        summary["notes"] = run.notes
        summary["group_names"] = run.group_names
        summary["group_stats"] = build_group_stats(manager.store, run.group_names, rows)
        manager.store.write(run.version, summary, rows)
        run.summary = summary
    except Exception as e:
        logger.error("Could not write partial results for stopped run: %s", e)
