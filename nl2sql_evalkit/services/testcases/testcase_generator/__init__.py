"""Writing test cases from schema files.

FLOW
----
1. ``schema_reader.read_schema`` turns each uploaded ``.sql`` / ``.ddl`` file into tables, columns and keys (and the upload
   is deleted). No database is connected and no data is read.
2. ``planning.plan_tasks`` decides which tables each question is written from: tables are taken in a spread order so they
   sample the whole schema, questions are shared out across the uploaded files, and join questions are written from tables
   that are linked by a key.
3. ``writer.generate_item`` asks the model for ONE item of a category (a question with its SQL, or a whole conversation).
   ``checks.validate`` rejects anything that breaks the rules (the SQL must parse in the configured dialect, only read,
   use only the tables it was given and columns that exist, and be the kind of query the category asks for) and the item is
   retried with the reason spelled out. The tables and columns of the test case are read from the SQL, never from the model.
4. ``manager.GenerationManager`` runs this in the background, saving every finished item to a *review batch*
   so closing the browser or losing the network loses nothing. Items become test cases only when approved;
   batches never approved are deleted after ``batch_ttl_hours``.

CATEGORIES (see ``core.constants.generator_categories``; each becomes a group)
    simple     one table: a look-up, a filter, a sort
    join       two or three tables joined on their keys
    aggregate  counts, sums and averages, grouped, with HAVING
    nested     needs a subquery or a WITH
    followup   a conversation whose later questions only make sense with the earlier turns
    vague      unclear on purpose: the assistant should ask back (test case type ``clarify``)
    unsafe     a request the assistant should refuse (test case type ``refuse``)

Modules: ``prompts/`` (what the model is told, one file each) · ``checks`` (the rules) · ``model_client`` (the model; the call
itself is ``llm_client.complete``) · ``writer`` · ``planning`` · ``manager``.
"""
from nl2sql_evalkit.core.constants import CATEGORIES, CATEGORY_LABELS, case_type_of
from nl2sql_evalkit.core.exceptions import GenerationBusy, GenerationError
from nl2sql_evalkit.services.testcases.testcase_generator.checks import validate
from nl2sql_evalkit.services.testcases.testcase_generator.manager import GenerationManager
from nl2sql_evalkit.services.testcases.testcase_generator.model_client import GenerationModelClient
from nl2sql_evalkit.services.testcases.testcase_generator.planning import Task, plan_tasks
from nl2sql_evalkit.services.testcases.testcase_generator.reply_parser import parse_reply
from nl2sql_evalkit.services.testcases.testcase_generator.review_batches import (
    batch_summary,
    discard_batch,
    get_batch,
    start_generation,
)
from nl2sql_evalkit.services.testcases.testcase_generator.writer import generate_item

__all__ = [
    "CATEGORIES", "CATEGORY_LABELS", "GenerationBusy", "GenerationError", "GenerationManager", "GenerationModelClient", "Task",
    "batch_summary", "case_type_of", "discard_batch", "generate_item", "get_batch", "parse_reply", "plan_tasks",
    "start_generation", "validate",
]
