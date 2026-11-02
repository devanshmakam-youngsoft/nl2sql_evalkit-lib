"""The background job that writes questions, and the review that turns them into test cases.

A *review batch* (stored in ``store.batches``) looks like::

    {batch_id, status: running|ready|failed|cancelled|interrupted, created_at, expires_at,
     options: {per_category, categories, turns}, model, files: [{name, tables, relations, skipped, error}],
     total_tasks, done_tasks, errors: [{category, file, reason}], error,
     items: [{item_id, category, file, number, type,
              turns: [{question, expected_sql, expected_tables, expected_columns, needs_context}]}]}

A vague or unsafe item (type ``clarify`` or ``refuse``) has no SQL: its turn holds ``question`` and ``note`` instead.
It is saved after every item, so nothing is lost if the browser goes away; it only becomes test cases when approved.
"""
from __future__ import annotations

import logging
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from nl2sql_evalkit.core.constants import (
    ANSWER,
    CATEGORIES,
    CATEGORY_LABELS,
    DEFAULT_PER_CATEGORY,
    DEFAULT_TURNS,
    MAX_TURNS,
    MIN_TURNS,
    SUPPORTED_SUFFIXES,
    parse_type,
)
from nl2sql_evalkit.core.diagnostics import EventLog
from nl2sql_evalkit.core.exceptions import (
    GenerationBusy,
    InvalidInput,
    NotFoundError,
    SchemaError,
)
from nl2sql_evalkit.services.sql_analysis import (
    parse_statements,
    read_only_problem,
    tables_used,
)
from nl2sql_evalkit.services.testcases.schema_reader import ReadSchema, read_schema
from nl2sql_evalkit.services.testcases.testcase_generator.checks import (
    check_text,
    expected_columns_of,
)
from nl2sql_evalkit.services.testcases.testcase_generator.model_client import GenerationModelClient
from nl2sql_evalkit.services.testcases.testcase_generator.planning import Task, plan_tasks
from nl2sql_evalkit.services.testcases.testcase_generator.writer import generate_item

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationManager:
    """Starts generation jobs and turns approved review batches into test cases.

    One job runs at a time, on a background thread that reads the uploads and then asks the model for each
    question using a pool of worker threads. Every model call is retried and checked (see ``writer``), and the
    batch is saved after each item so progress survives a closed browser.

    Args:
        config: The app config (model names, dialect, limits, worker count, batch lifetime).
        store: Where batches and test cases are saved.
        llm: Callable taking chat messages and returning the reply text; defaults to ``GenerationModelClient``.
            Replace it to use your own model client or a fake in tests.
        sleep: Called with the seconds to wait between retries; defaults to ``time.sleep``.
    """

    def __init__(self, config, store, llm: Callable | None = None, sleep: Callable | None = None):
        self.config = config
        self.store = store
        self._llm = llm or GenerationModelClient(config)
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._active: str | None = None
        self._cancelled: set[str] = set()
        self.store.interrupt_running_batches()  # a restart cannot resume a job, but what it saved stays reviewable

    @property
    def model(self) -> str:
        """The name of the model that receives the schema text: the client's own, else the configured one."""
        return getattr(self._llm, "model", None) or self.config.generator_model or self.config.judge_model

    def limits(self) -> dict:
        """What the dialog states up front: limits, the categories, the SQL dialect, and which model receives the text."""
        return {
            "max_files": self.config.generate_max_files,
            "max_file_mb": self.config.generate_max_file_mb,
            "per_category_max": self.config.generate_per_category_max,
            "per_category_default": DEFAULT_PER_CATEGORY,
            "turns_default": DEFAULT_TURNS,
            "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
            "model": self.model,
            "dialect": self.config.dialect,
            "ttl_hours": self.config.batch_ttl_hours,
            "formats": [s.lstrip(".") for s in SUPPORTED_SUFFIXES],
        }

    # ---- writing ------------------------------------------------------------------------------

    def start(self, files: list[tuple[str, Path]], workdir: Path | None, *, per_category: int, categories: list[str], turns: int) -> dict:
        """Create a review batch and start writing into it on a background thread; return the new batch at once.

        Args:
            files: ``(name, path)`` pairs: the name to show for each uploaded schema file and where it is on disk.
            workdir: The temporary folder holding the uploads; deleted once the files have been read.
            per_category: How many questions to write for each category.
            categories: Which categories to write; unknown names are ignored.
            turns: How many turns a conversation has.

        Raises:
            InvalidInput: When no valid category is chosen or ``per_category`` or ``turns`` is out of range.
            GenerationBusy: When another generation is still running.
        """
        categories = [c for c in CATEGORIES if c in categories]
        if not categories:
            raise InvalidInput("Choose at least one category")
        if not 1 <= per_category <= self.config.generate_per_category_max:
            raise InvalidInput(f"Questions per category must be between 1 and {self.config.generate_per_category_max}")
        if not MIN_TURNS <= turns <= MAX_TURNS:
            raise InvalidInput(f"A conversation needs between {MIN_TURNS} and {MAX_TURNS} turns")
        with self._lock:
            if self._active:
                raise GenerationBusy("Another generation is already running")
            batch_id = uuid.uuid4().hex[:12]
            created = _now()
            batch = {
                "batch_id": batch_id, "status": "running", "created_at": created.isoformat(),
                "expires_at": (created + timedelta(hours=self.config.batch_ttl_hours)).isoformat(),
                "options": {"per_category": per_category, "categories": categories, "turns": turns},
                "model": self.model, "files": [{"name": n} for n, _ in files],
                "total_tasks": 0, "done_tasks": 0, "items": [], "errors": [], "error": "",
            }
            self.store.save_batch(batch)
            self._active = batch_id
        log = EventLog(self.config, "generation", batch_id)
        log.info("Generation %s started: %d schema files, %d per category, categories %s, %d turns, dialect %s, model %s",
                 batch_id, len(files), per_category, ", ".join(categories), turns, self.config.dialect, self.model)
        batch["log_file"] = log.file_name
        self.store.save_batch(batch)
        threading.Thread(target=self._run, args=(batch, files, workdir, log), daemon=True, name=f"generate-{batch_id}").start()
        return batch

    def cancel(self, batch_id: str) -> None:
        """Ask a running generation to stop; questions already being written finish, the rest are skipped.

        The batch is then marked ``cancelled``, and what was written stays available for review.
        """
        self._cancelled.add(batch_id)

    def _run(self, batch: dict, files: list[tuple[str, Path]], workdir: Path | None, log: EventLog) -> None:
        batch_id = batch["batch_id"]
        try:
            schemas = self._read_schemas(batch, files, workdir, log)
            if schemas:
                self._write_items(batch, schemas, log)
            self._finish(batch)
        except Exception as e:  # never leave a batch stuck on "running"
            issue = log.issue("generation_run", e, f"after {batch['done_tasks']} of {batch['total_tasks']} questions")
            batch.update(status="failed" if not batch["items"] else "ready", error=issue.message, error_detail=issue.technical)
            self.store.save_batch(batch)
        finally:
            log.info("Generation %s %s: %d items, %d problems", batch_id, batch["status"], len(batch["items"]), log.issue_total)
            log.close()
            self._cancelled.discard(batch_id)
            with self._lock:
                self._active = None

    def _read_schemas(self, batch: dict, files: list[tuple[str, Path]], workdir: Path | None, log: EventLog) -> list[ReadSchema]:
        """Read every upload (one that cannot be read is reported and skipped), then delete the uploads."""
        schemas: list[ReadSchema] = []
        batch["files"] = []
        try:
            for name, path in files:
                try:
                    schema = read_schema(path, name, self.config.dialect)
                    schemas.append(schema)
                    batch["files"].append({"name": name, "tables": len(schema.tables), "relations": len(schema.key_pairs()), "skipped": schema.skipped})
                except SchemaError as e:
                    log.issue("generation", e, name)
                    batch["files"].append({"name": name, "error": str(e)})
        finally:
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)  # nothing of the upload is kept
        if not schemas:
            reasons = " ".join(f["error"] for f in batch["files"] if f.get("error"))
            batch.update(status="failed", error=reasons or "No schema file could be read.")
        self.store.save_batch(batch)
        return schemas

    def _write_items(self, batch: dict, schemas: list[ReadSchema], log: EventLog) -> None:
        batch_id, opts = batch["batch_id"], batch["options"]
        tasks = plan_tasks(schemas, opts["categories"], opts["per_category"])
        batch["total_tasks"] = len(tasks)
        self.store.save_batch(batch)
        lock = threading.Lock()

        def work(task: Task) -> dict | None:
            if batch_id in self._cancelled:
                return None
            with lock:
                avoid = [t["question"] for it in batch["items"] if it["file"] == task.file for t in it["turns"]]
            return generate_item(task, self._llm, turns=opts["turns"], avoid=avoid, dialect=self.config.dialect, sleep=self._sleep)

        with ThreadPoolExecutor(max_workers=max(1, self.config.generate_workers)) as pool:
            futures = {pool.submit(work, t): t for t in tasks}
            for future in as_completed(futures):
                task = futures[future]
                with lock:
                    batch["done_tasks"] += 1
                    try:
                        item = future.result()
                        if item:
                            item["item_id"] = uuid.uuid4().hex[:8]
                            batch["items"].append(item)
                    except Exception as e:
                        issue = log.issue("generation", e, f"{CATEGORY_LABELS[task.category]} question from {task.file}")
                        batch["errors"].append({"category": task.category, "file": task.file, "reason": issue.message, "detail": issue.technical})
                    batch["items"].sort(key=lambda it: (CATEGORIES.index(it["category"]), it["number"]))
                    self.store.save_batch(batch)  # saved after every item: nothing is lost if the browser goes away

    def _finish(self, batch: dict) -> None:
        if batch["status"] == "failed":  # no schema file could be read
            return
        if batch["batch_id"] in self._cancelled:
            batch["status"] = "cancelled"
        elif not batch["items"]:
            batch.update(status="failed", error="No question could be written. " + (batch["errors"][0]["reason"] if batch["errors"] else ""))
        else:
            batch["status"] = "ready"
        self.store.save_batch(batch)

    # ---- review -------------------------------------------------------------------------------

    def _editable(self, batch_id: str) -> dict:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise NotFoundError("These generated test cases are no longer available")
        if batch["status"] == "running":
            raise GenerationBusy("Wait for generation to finish before editing")
        return batch

    def edit_item(self, batch_id: str, item_id: str, turns: list[dict]) -> dict:
        """Reword the question, and the SQL when the item has any. The number of turns stays as it is.

        New SQL has to parse in the configured dialect and be one read-only query; the tables and columns of the test case are
        read from it again, so they always match the SQL.
        """
        batch = self._editable(batch_id)
        item = next((i for i in batch["items"] if i["item_id"] == item_id), None)
        if item is None:
            raise NotFoundError("Item not found")
        if len(turns) != len(item["turns"]):
            raise InvalidInput("The number of turns cannot change")
        has_sql = parse_type(item.get("type")) == ANSWER
        cleaned = []
        for turn, new in zip(item["turns"], turns):
            question, sql = str(new.get("question", "")).strip(), str(new.get("expected_sql", "")).strip()
            problem = check_text(question, sql, standalone=False, needs_sql=has_sql, technical=item["category"] != "unsafe")
            if problem:
                raise InvalidInput(problem[0].upper() + problem[1:])
            updated = {**turn, "question": question}
            if has_sql:
                statements, error = parse_statements(sql, self.config.dialect)
                problem = f"the SQL does not parse as {self.config.dialect}: {error}" if error else read_only_problem(statements)
                if problem:
                    raise InvalidInput(problem[0].upper() + problem[1:] if error else f"The SQL must be one read-only SELECT, but {problem}")
                updated.update(expected_sql=sql, expected_tables=", ".join(tables_used(statements)),
                               expected_columns=", ".join(expected_columns_of(statements[0])))
            cleaned.append(updated)
        item["turns"] = cleaned
        self.store.save_batch(batch)
        return item

    def remove_item(self, batch_id: str, item_id: str) -> None:
        """Drop one item from a batch under review so it is not turned into test cases.

        Raises:
            NotFoundError: When the batch has expired or is gone, or has no such item.
            GenerationBusy: When the batch is still being written.
        """
        batch = self._editable(batch_id)
        remaining = [i for i in batch["items"] if i["item_id"] != item_id]
        if len(remaining) == len(batch["items"]):
            raise NotFoundError("Item not found")
        batch["items"] = remaining
        self.store.save_batch(batch)

    def _chat_ids(self, items: list[dict]) -> dict[str, str]:
        """A short chat id for each item: ``simple-1``, ``followup-2``, ... Numbering carries on after the highest one
        already in the store, so ids never collide with a case that exists."""
        highest: dict[str, int] = {}
        for case in self.store.list_test_cases():
            found = re.fullmatch(r"([a-z]+)-(\d+)", str(case.get("chat_id", "")))
            if found and found.group(1) in CATEGORIES:
                highest[found.group(1)] = max(highest.get(found.group(1), 0), int(found.group(2)))
        ids = {}
        for item in items:
            highest[item["category"]] = highest.get(item["category"], 0) + 1
            ids[item["item_id"]] = f"{item['category']}-{highest[item['category']]}"
        return ids

    def approve(self, batch_id: str, item_ids: list[str] | None = None) -> dict:
        """Turn the chosen items (all by default) into test cases, labelled by category, and delete the batch.
        Anything not chosen is discarded with it."""
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise NotFoundError("These generated test cases are no longer available")
        if batch["status"] == "running":
            raise GenerationBusy("Wait for generation to finish, or cancel it first")
        wanted = set(item_ids) if item_ids is not None else None
        chosen = [it for it in batch["items"] if wanted is None or it["item_id"] in wanted]
        if not chosen:
            raise InvalidInput("There is nothing to approve")

        chat_ids = self._chat_ids(chosen)
        rows = []
        for item in chosen:
            for turn_no, turn in enumerate(item["turns"], start=1):
                rows.append({
                    "row": len(rows) + 2, "chat_id": chat_ids[item["item_id"]], "turn_no": turn_no, "type": item.get("type") or ANSWER,
                    "question": turn["question"], "expected_sql": turn.get("expected_sql", ""),
                    "expected_tables": turn.get("expected_tables", ""), "expected_columns": turn.get("expected_columns", ""),
                    "groups": [CATEGORY_LABELS[item["category"]]],
                    "origin": {
                        "kind": "generated", "category": item["category"], "file": item["file"], "model": batch.get("model", ""),
                        **({"needs_context": turn["needs_context"]} if turn.get("needs_context") else {}),
                        **({"note": turn["note"]} if turn.get("note") else {}),
                    },
                })
        result = self.store.import_cases(rows)
        self.store.delete_batch(batch_id)
        return {
            "cases": len(rows), "items": len(chosen), "discarded": len(batch["items"]) - len(chosen),
            "groups": [label for key, label in CATEGORY_LABELS.items() if any(i["category"] == key for i in chosen)],
            "groups_created": result["groups_created"],
        }
