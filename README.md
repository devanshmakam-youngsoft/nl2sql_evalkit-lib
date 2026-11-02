# nl2sql_evalkit

Evaluate any text-to-SQL assistant. You give nl2sql_evalkit a Python function that turns a question into SQL; it replays your test questions through it, **reads** each SQL answer (it is never run), scores it with checks and an AI judge, and shows the versions of your assistant side by side in a dashboard.

- **Static checks only.** No database connection and nothing executed: the SQL is parsed, not run
- Checks on every answer: does it parse, is it read-only, does it use the expected tables and columns, does it join the way the expected SQL does
- Two scores per version: the **SQL score** (0–10, written by an AI judge with a reason and a suggestion) and the **tables-and-columns score** (rule-based), plus response time and how long each step takes
- A **Where answers fail** view: which check fails how often, and what changed since the run before
- A test case library: groups (labels), bulk import from Excel/CSV, and test cases written from your own `.sql` / `.ddl` schema files
- A recommendation of which version to ship, computed on the test cases the versions share
- Plain-language findings for every run: each watch-out paired with what to do about it
- Excel export, optional login, and one JSON file for storage (TinyDB), so there is nothing to set up

**More:** the dashboard's **Help** page is the full guide, with runnable examples for the common setups (function shapes, steps, LangGraph, your own judge) and a troubleshooting section. The same page is in the repository at [nl2sql_evalkit/web/guide/developer-guide.html](nl2sql_evalkit/web/guide/developer-guide.html), and its code is in [examples/](examples/).

---

## Installation

```bash
pip install git+https://github.com/devanshmakam-youngsoft/nl2sql_evalkit-lib.git
```

To pin a release, add a tag, for example `@v0.1.3` (tags: `v0.1.0` to `v0.1.4`). `v0.1.4` is the first release with the backend layout described below and the `data_dir` option in place of `store_path` and `log_dir`; code written for an earlier tag that passes those two options needs the one change.

In `requirements.txt`:

```
git+https://github.com/devanshmakam-youngsoft/nl2sql_evalkit-lib.git
```

> **Windows:** run `pip install` from **Git Bash** if `git` is not in your PowerShell PATH.

**Dependencies are pinned for safety.** `litellm` is held to `>=1.104,<1.107`: version 1.107.0 (21 Oct 2026) and 1.82.7/1.82.8 (Mar 2026) were published with credential-stealing malware. Raise the upper bound only after checking that a newer release is clean.

---

## Quick Start

### 1. Start the evaluation server

`serve()` takes **your assistant function**. Anything that turns a question into SQL works, and the SQL is only read, never run:

```python
import nl2sql_evalkit

def my_assistant(question: str) -> str:
    return text_to_sql_chain.invoke(question)        # returns "SELECT ..."

nl2sql_evalkit.serve(my_assistant, dialect="postgres", port=8002, require_login=False)
```

`dialect` is the SQL your assistant writes: `"postgres"` (the default), `"mysql"`, `"sqlite"` or `"tsql"` (`"SQL Server"` works too). It decides how the SQL is parsed. The dashboard opens at `http://localhost:8002` (the default port is `8001`). A `.env` file next to your script is read, so `GROQ_API_KEY`, `OPENAI_API_KEY` and the like are picked up for the judge.

Your function can also take history or a session id, return a dict (the `sql` or `query` key is read first), or be `async`; nl2sql_evalkit adapts to its parameter names (see the guide). A reply may also be a plain message instead of SQL: that is what a test case of type `clarify` or `refuse` expects. To show what happens *inside* the assistant, mark its steps:

```python
with nl2sql_evalkit.step("schema_lookup"):
    tables = pick_tables(question)
with nl2sql_evalkit.step("llm"):
    sql = llm.generate(question, tables)
```

A step is timed and its inputs and output are shown on the question's result. Steps may run in threads you start; they still belong to the question being evaluated.

### 2. Add test cases

Open **Test Cases**. You can add one case with **+ New test case**, bring many in with **Import** (Excel/CSV or pasted rows), or write them from your schema with **Generate from a schema**. Each case has a `chat_id`, `turn_no`, a `type`, a `question`, and for an answer case at least one of `expected_sql`, `expected_tables` and `expected_columns` (see [Test cases and types](#test-cases-and-types)).

### 3. Run an evaluation

Click **Execute session**, name the version, pick groups and/or individual test cases, add an optional note, and run. For each test case nl2sql_evalkit calls your function, checks the SQL, and has the judge score it.

### 4. Read the results

The **Dashboard** shows every version with its average scores and a recommendation. Open a version for the score distribution, **Where answers fail**, the timing of each step, watch-outs with suggestions, and every question's SQL with the checks, the reason and a suggestion. Download an Excel report from the version page.

---

## How an answer is scored

Nothing is executed and no database is involved, so the score comes from reading the SQL (parsed with [sqlglot](https://github.com/tobymao/sqlglot) in your dialect).

**Checks** (rule-based, shown as chips on every question):

| Check | Passes when |
|---|---|
| Parses | The reply is SQL that parses in your dialect |
| Read-only | It is one `SELECT` (or `WITH ... SELECT`) with no write, DDL, `INTO`, lock or risky function such as `pg_sleep` |
| Expected tables | Every table in `expected_tables` is used |
| Expected columns | Every column in `expected_columns` is used (a `SELECT *` cannot be told apart and is flagged) |
| Joins | The join keys match those of `expected_sql` (checked when `expected_sql` is given) |

**SQL score (0–10).** An AI judge reads the question, the expected SQL (if any), the reply and the checks, and gives a score, a reason and a suggestion. A reply that has no SQL, does not parse or is not read-only scores 0 without calling the judge. For a `clarify` or `refuse` case the judge decides whether the reply is a sensible question back or a proper refusal; any SQL in such a reply scores 0.

**Tables-and-columns score.** Rule-based: how much of the expected tables and columns the SQL uses. It is the `schema_weight` part of the recommendation.

**Your own judge.** Pass `judge_fn(question, expected_sql, reply, checks)` to `serve()` to score with your own code instead of the AI judge. It returns `{"sql_marks": 0-10, "sql_comment": "...", "suggestion": "..."}`; `checks` holds what the checks found (`syntax_ok`, `read_only`, `tables_missing`, `columns_missing`, `star`, `joins_match`, `joins_missing`, ...). See [examples/custom_judge.py](examples/custom_judge.py). `judge_prompt` changes the AI judge's rubric instead (see [examples/custom_judge_prompt.py](examples/custom_judge_prompt.py)).

**Where answers fail.** On the dashboard and on each version page: for every check, how many replies failed it out of the questions that should be answered, with arrows for the change since the run before ("v3 fixed joins but broke columns").

**What it cannot tell you.** Because the SQL is never run, a query that parses, reads the right tables and still returns the wrong rows is judged by reading only. The judge is a model, so its scores can vary a little between runs. A reply whose first word is mistyped (`SELCT ...`) reads as a message, not as SQL.

---

## Configuration

The most used `serve()` parameters (the full list, with every default, is in the `serve()` docstring and the developer guide):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `fn` | required | Your assistant function: question in, SQL (or a message) out |
| `dialect` | `"postgres"` | The SQL your assistant writes: `"postgres"`, `"mysql"`, `"sqlite"` or `"tsql"` |
| `port` | `8001` | Port for the dashboard |
| `data_dir` | `"nl2sql_evalkit_data"` | The one folder everything is written to: `store.json`, `logs/`, `uploads/` |
| `show_guide` | `True` | Show the guide on the dashboard's Help page; `False` hides the link and stops serving it |
| `require_login` | `True` | Show the login page; `False` accepts any username without a password |
| `users` | `"admin:admin123"` | `"user:password"` pairs, comma separated |
| `judge_model` | `"groq/openai/gpt-oss-120b"` | Any LiteLLM model string for the judge |
| `judge_api_key` | `None` | Otherwise LiteLLM reads the provider's environment variable |
| `judge_fn` | `None` | Your own scoring function instead of the AI judge |
| `judge_prompt` | `None` | Your own rubric for the AI judge |
| `generator_model` | `None` | Model that writes test cases from schema files; defaults to `judge_model` |
| `sql_weight` / `schema_weight` | `0.6` / `0.4` | How the recommendation weighs the SQL score and the tables-and-columns score |
| `recommendation_tolerance` | `0.25` | Versions this close to the best count as tied; the fastest wins |
| `max_response_time` | `None` | Leave out versions slower than this (seconds) when recommending |
| `summary_prompt` | `None` | Changes what the AI-written findings look for |
| `eval_env` | `"dev"` | `"prod"` turns the dashboard and every eval route off |

---

## Test cases and types

Test cases are the unit of the library. A **group** is just a label you put on test cases: one case can carry any number of labels, and you can add or remove them from the Test Cases page (tick rows → *Add to group…*) or from a case's detail panel.

Each case has a **type**:

| Type | The assistant should | Needs |
|---|---|---|
| `answer` (default) | Write SQL | at least one of `expected_sql`, `expected_tables`, `expected_columns` |
| `clarify` | Ask a question back, because the request is vague | only the question |
| `refuse` | Decline, because the request is unsafe (delete, drop, update ...) | only the question |

`expected_tables` and `expected_columns` are comma separated lists (`orders, customers`; `region, amount` or `orders.amount`). Follow-up questions are cases with the same `chat_id` and a higher `turn_no`; a run includes the earlier turns of each selected conversation so a follow-up has what it builds on.

You can run:

- one or more **groups** (a case that is in several selected groups runs once), or
- any **hand-picked test cases** — tick rows on the Test Cases page and choose *Run*, or use *Pick test cases* in the Execute dialog.

**Deleting a test case removes it for good**, with all its versions and group labels. Past versions keep their own copy of the question and the answer, and mark that row *Test case deleted*. **Deleting a group** only hides it (its labels stay, so past versions still read correctly); open *Deleted groups* on the Groups page to restore or remove one. Deleting a **version** removes it and its results from the store for good. To take a test case out of runs without deleting it, mark it *inactive*.

## Generating test cases from a schema

**Test Cases → Generate from a schema** writes test cases from `.sql`, `.ddl` or `.txt` files that hold `CREATE TABLE` statements (up to 5 files, 10 MB each; a dump with `INSERT` or `COPY` data is fine, only the schema is read). Nothing is connected to and nothing is run: the files are read, used and not kept.

The schema is read in your `dialect`: tables, columns, types, primary keys, foreign keys (including ones added later with `ALTER TABLE`) and column comments. A statement that cannot be read is skipped and listed. By default it writes 3 questions in each of seven categories and puts them in a group per category:

| Category | Type | What it is |
|---|---|---|
| **Simple** | answer | One table: a filter, a sort or a list. |
| **Joins** | answer | Two or three tables linked by their keys. |
| **Aggregations** | answer | Counts, sums, averages, grouped. |
| **Subqueries** | answer | Needs a subquery or a `WITH`. |
| **Follow-ups** | answer | A short conversation (3 turns by default). Each follow-up refers back to the earlier answer and cannot be asked on its own; what it builds on is shown during review. |
| **Vague** | clarify | A question that cannot be answered without asking something back; the reason it is unclear is kept as a note. |
| **Unsafe** | refuse | A request to change or destroy data or to bypass limits. |

- **Questions are planned from the keys.** Join questions use tables that are linked by a declared foreign key (or, if the schema declares none, by names such as `customer_id`).
- **The SQL is checked before you see it.** It must parse in your dialect, be one read-only `SELECT`, use only the tables it was given and columns that exist, and fit its category (a join question must join on the declared keys). A rejected one is rewritten, up to three times, with the reason. Questions in plain language must not use technical words ("table", "SQL") except the unsafe ones.
- **Expected tables and columns come from the SQL**, not from the model, so they cannot be invented. Columns used only to join are left out.
- **Saved as it goes, approved by you.** Questions are saved on the server while they are being written, so closing the browser or losing the network loses nothing; a banner on the Test Cases page brings you back. They only become test cases when you press *Add*; you can edit the question or the SQL first (new SQL is checked the same way). Anything not added within 24 hours (`batch_ttl_hours`) is deleted.
- **Which model writes them:** `serve(generator_model=...)`, defaulting to `judge_model`. The schema is sent to that model, so pick one you are allowed to send it to (a local `ollama/...` model works).

## Importing test cases in bulk

**Test Cases → Import** takes an Excel or CSV file, or rows pasted from a spreadsheet, in three steps: pick the file, check what will happen, then choose where the cases go. Nothing is saved until the last step. A sample is in [examples/test_cases.csv](examples/test_cases.csv).

- **Check first.** You see how many rows are new, will be updated, are already there, or can't be imported — with the row number and reason for each one that can't — before anything is saved. Nothing is silently corrected: a turn of "abc" is reported, not turned into 1.
- **Only the question column is required.** Without a chat column every question becomes its own chat; without a turn column turns are numbered in file order within each chat. The columns are `chat_id`, `turn_no`, `type`, `question`, `expected_sql`, `expected_tables`, `expected_columns` and `groups`; common header names are recognised, and the dialog lets you point any column at the right field.
- **Groups are optional.** The default is *No group*. Pick existing groups or a new one for the whole file, and/or add a `groups` column (`Billing; Refunds`) to label rows individually — missing groups are created.
- **Safe to repeat.** Importing the same file again changes nothing; an edited expected SQL becomes a new version of the existing case. If a row has the same chat and turn as an existing case but a different question you can add it as a new case or update the existing one.
- **Fix and re-import.** The rows that couldn't be imported can be downloaded with the reason next to each. A template (with a short guide) is available in the dialog.

## Which version should ship?

The dashboard's recommendation is computed by the server (`GET /api/recommendation`) every time, from the saved scores of every run that is **not archived** — archive or delete a version and the recommendation, trend charts, deltas and group history update straight away.

**Versions are compared on the test cases they share.** Each run saves its score for every test case, so adding a test case (or running an extra group) in a later version no longer hides it: it is judged on the cases the others also ran, and the dashboard says so ("Compared on the 10 test cases every compared version ran; v4 ran 20"). A case only counts as the same if its question and expected SQL are unchanged. If the shared cases are only a thin slice (fewer than half of a typical version's cases, e.g. a 2-question smoke test next to 10-question runs) that version is left out and the reason is shown. Versions that were stopped early, or failed on a shared case, are left out too. The *overall score* is the SQL score and the tables-and-columns score weighted by `sql_weight` / `schema_weight` from `serve()` (default 60/40); versions within the tie tolerance of the best are tied and the fastest wins. If the tables-and-columns score was not graded for every compared version (no case had expected tables or columns), all are compared on the SQL score alone and the dashboard says so. Changes (the ± figures) and BEST marks use the same shared cases.

Each run's summary also has *Watch-outs & suggestions*: AI-written findings, each pairing one thing that needs attention with the next step that answers it (it does not repeat the headline scores). The reply is checked: a finding without its suggestion is sent back to the model, and if the model cannot write them they are written from the run's own check counts. `serve(summary_prompt=...)` changes what it looks for; the JSON reply format is added automatically.

Each run also saves a detailed `scores` block (score tiers, per-type averages, response-time spread and how many replies failed each check) on its summary; **Where answers fail** reads it.

## For teams and CI

Set `users`, a fixed `secret` (so people stay signed in across restarts) and `data_dir`, and give the whole team the same URL; see [examples/team_setup.py](examples/team_setup.py). To fail a build when the SQL score drops, start the server, run a group of test cases through the API and check the score: [examples/ci_gate.py](examples/ci_gate.py).

---

## Logs and problems

Everything is written to one data folder (`nl2sql_evalkit_data/` by default, `data_dir` moves it): the store, the logs and the uploads.

```
nl2sql_evalkit_data/
├── store.json     results, test cases, groups, review batches
├── logs/          server.log, runs/, generation/
└── uploads/       spreadsheets uploaded for a run
```

The log files:

| File | Contents |
|---|---|
| `logs/server.log` | The library's own log lines; unexpected API errors with a reference number and the full traceback |
| `logs/runs/<time>_<version>.log` | One file per run: every question with its result and time, every problem with its traceback, how the run ended |
| `logs/generation/<batch>.log` | The same for test cases written from schema files |

The dashboard reports problems in plain words and keeps the technical detail one click away: a problem count while a run is going, a *Problems during this run* section and a *Download log* button on each version, the reason on every question that could not be answered or graded, and a message with a reference number for server errors. A failing assistant function never stops a run: that question is marked failed, the reason is recorded, and the run goes on. API keys and passwords are hidden before anything is written or shown.

---

## Versioning

When you release a new version of your assistant, run the evaluator against the same test cases and give it a new version name (e.g. `v2`). The dashboard tracks all versions so you can compare quality over time, and **Where answers fail** shows which checks got better or worse.

---

## Development

### Layout

In the repository:

```
nl2sql_evalkit-lib/
├── README.md, pyproject.toml
├── nl2sql_evalkit/        the BACKEND: the Python package (everything in it is installed)
├── frontend/          the dashboard's source (React + Vite); builds into nl2sql_evalkit/web/dashboard
├── tests/             mirrors nl2sql_evalkit/ folder by folder, plus architecture/, examples/, guides/
├── docs/guide/        the guide's source: shell.html and one file per page in pages/
├── examples/          the runnable code the guide shows; every file is run by tests/examples
└── scripts/           build_guide.py, rename_library.py
```

Inside the backend, each folder is a layer that only reaches downwards (`routers -> services -> core, schemas, utils`; `services/db_services` is the only code that knows the JSON store's format; inside services, `evaluation` may use `testcases`, and `testcases` may use neither `evaluation` nor anything above it;
`tests/architecture` enforces both).

A folder is used through its `__init__`: code outside `services/db_services/` writes
`from nl2sql_evalkit.services.db_services import EvalStore`, never `...db_services.store`. Files inside a folder import each other
directly, and each `__init__` lists what the folder offers in `__all__` (`tests/architecture` checks this too). The folders:

```
nl2sql_evalkit/
├── __init__.py          public API: serve, step, note, errors
├── main.py              builds the web app
├── launcher.py          serve(): checks options, starts the server
├── core/                config/ (settings by topic), constants/ (library.py holds the names), exceptions/ (+ handlers),
│                        diagnostics/ (log files, plain-language problems), security/ (sign-in)
├── routers/             one folder per area, each file thin: evaluation/, testcase_library/, testcase_generator/, sign_in/, app_info/
├── schemas/             the shape of every request and response, same area folders; internal/ for shapes services share
├── services/            what the product does
│   ├── evaluation/      evaluation_runner, sql_judge, step_recorder, run_summarizer, version_recommender
│   ├── testcases/       testcase_library, testcase_import, testcase_generator, schema_reader, spreadsheet_loader
│   ├── db_services/     reads and writes the TinyDB JSON store (store.py and one file per kind of record)
│   ├── llm_client/      one safe way to call any AI model
│   └── app_info/        the guide page and which dashboard features are on
├── prompts/             the instructions sent to AI models, one file each: sql_judge/, testcase_generator/
├── utils/               small shared helpers
└── web/                 generated, do not edit: dashboard/ (built from frontend/) and guide/ (built from docs/guide/)
```

What `pip install` puts on a machine is only the `nl2sql_evalkit/` folder: no tests, docs, examples, frontend source or scripts.
The folder a running server writes is `nl2sql_evalkit_data/` (`data_dir=` moves it): `store.json`, `logs/`, `uploads/`.

**The library's name** is written in one file, `nl2sql_evalkit/core/constants/library.py`; the data folder, the sign-in cookie, the loggers and
the API title are derived from it. To rename the library everywhere (folder, imports, `pyproject`, docs and that file) run
`python scripts/rename_library.py NEW_NAME` for a dry run, and add `--apply` to do it.

### The guide

`nl2sql_evalkit/web/guide/developer-guide.html` is built from `docs/guide/` (a shell and one file per page). Its code comes from the files in
`examples/` (run by `tests/examples`) and its `serve()` reference comes from the function's own signature and docstring, so
it cannot drift. After changing the template, an example or `serve()`, rebuild it:

```bash
python scripts/build_guide.py
```

`tests/guides` fails when the built guide is out of date.

### Dashboard

The dashboard source lives in `frontend/` (React + Vite) and builds straight into `nl2sql_evalkit/web/dashboard/`. To rebuild it:

```bash
cd frontend
npm ci
npm run build
```

The build replaces `nl2sql_evalkit/web/dashboard/`, which is committed so that `pip install` from git works without Node. Backend tests: `pip install -e .[dev]` then `pytest`.
