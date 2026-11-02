"""Writing test cases from schema files: the background job, review and approval over the API."""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.main import create_app
from nl2sql_evalkit.services.testcases.testcase_generator import GenerationManager

from .fake_model import SHOP_SQL, STAFF_SQL, FakeModel

SHOP = ("shop.sql", SHOP_SQL.encode(), "text/plain")
STAFF = ("staff.ddl", STAFF_SQL.encode(), "text/plain")
CATEGORY_KEYS = ["simple", "join", "aggregate", "nested", "followup", "vague", "unsafe"]


@pytest.fixture
def make_client(tmp_path):
    clients = []

    def build(model=None, **config):
        config.setdefault("generate_workers", 4)
        cfg = Config(data_dir=tmp_path / f"store{len(clients)}", require_login=False, eval_secret="s", **config)
        c = TestClient(create_app(cfg, fn=lambda q: "SELECT 1", generation_llm=model or FakeModel()))
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)


def upload(client, files, **data):
    return client.post("/api/generate", files=[("files", f) for f in files], data=data)


def wait(client, batch_id, until=("ready", "failed", "cancelled"), timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = client.get(f"/api/generate/{batch_id}").json()
        if batch["status"] in until:
            return batch
        time.sleep(0.05)
    raise AssertionError(f"still {batch['status']}")


def test_schema_files_in_questions_out_and_nothing_is_kept_of_the_upload(make_client):
    client = make_client()
    started = upload(client, [SHOP, STAFF], per_category=2, turns=3)
    assert started.status_code == 202
    batch = wait(client, started.json()["batch_id"])
    assert batch["status"] == "ready" and batch["errors"] == []
    by_category = {c: [i for i in batch["items"] if i["category"] == c] for c in CATEGORY_KEYS}
    assert {c: len(v) for c, v in by_category.items()} == {c: 2 for c in CATEGORY_KEYS}
    assert all(len(i["turns"]) == 3 for i in by_category["followup"]) and all(len(i["turns"]) == 1 for i in by_category["simple"])
    assert {i["file"] for i in batch["items"]} == {"shop.sql", "staff.ddl"}
    assert {i["type"] for i in by_category["vague"]} == {"clarify"} and {i["type"] for i in by_category["unsafe"]} == {"refuse"}
    assert {i["type"] for c in ("simple", "join", "aggregate", "nested", "followup") for i in by_category[c]} == {"answer"}
    joined = by_category["join"][0]["turns"][0]
    assert joined["expected_sql"].startswith("SELECT") and "," in joined["expected_tables"] and joined["expected_columns"]
    assert "note" in by_category["vague"][0]["turns"][0] and "expected_sql" not in by_category["vague"][0]["turns"][0]
    assert [f["name"] for f in batch["files"]] == ["shop.sql", "staff.ddl"]
    assert [(f["tables"], f["relations"]) for f in batch["files"]] == [(3, 2), (2, 1)] and batch["files"][0]["skipped"] == []
    assert client.app.state.store.list_test_cases() == []                      # nothing is a test case yet


def test_review_then_approve_adds_cases_with_their_type_group_tables_and_columns(make_client):
    client = make_client()
    batch = wait(client, upload(client, [SHOP], per_category=1, turns=2).json()["batch_id"])
    bid = batch["batch_id"]
    by_category = {i["category"]: i for i in batch["items"]}
    assert client.delete(f"/api/generate/{bid}/items/{by_category['unsafe']['item_id']}").status_code == 200

    simple = by_category["simple"]
    edited = client.patch(f"/api/generate/{bid}/items/{simple['item_id']}", json={"turns": [
        {"question": "Which customers are in the north region?", "expected_sql": "SELECT name FROM customers WHERE region = 'north'"}]})
    assert edited.status_code == 200
    assert edited.json()["turns"][0]["expected_tables"] == "customers" and edited.json()["turns"][0]["expected_columns"] == "name, region"
    patch = lambda body, item=simple: client.patch(f"/api/generate/{bid}/items/{item['item_id']}", json=body)      # noqa: E731
    assert patch({"turns": []}).status_code == 422
    broken = patch({"turns": [{"question": "Which customers are in the north region?", "expected_sql": "SELEC name FROM customers"}]})
    assert broken.status_code == 422 and "does not parse as postgres" in broken.json()["detail"]
    writes = patch({"turns": [{"question": "Which customers are in the north region?", "expected_sql": "DELETE FROM customers"}]})
    assert writes.status_code == 422 and "read-only" in writes.json()["detail"]
    technical = patch({"turns": [{"question": "Show the rows of the customers table", "expected_sql": "SELECT name FROM customers"}]})
    assert technical.status_code == 422 and "technical words" in technical.json()["detail"]
    vague = by_category["vague"]
    assert patch({"turns": [{"question": "Show me the largest orders please"}]}, vague).status_code == 200      # no SQL needed

    done = client.post(f"/api/generate/{bid}/approve", json={}).json()
    assert done["items"] == len(batch["items"]) - 1 and done["groups"] == ["Simple", "Joins", "Aggregations", "Subqueries", "Follow-ups", "Vague"]
    cases = client.get("/api/test-cases").json()
    assert len(cases) == done["cases"] and {c["type"] for c in cases} == {"answer", "clarify"}
    assert {g["name"] for c in cases for g in c["groups"]} == {"Simple", "Joins", "Aggregations", "Subqueries", "Follow-ups", "Vague"}
    first = next(c for c in cases if c["origin"]["category"] == "simple")
    assert (first["expected_sql"], first["expected_tables"], first["expected_columns"]) == ("SELECT name FROM customers WHERE region = 'north'", "customers", "name, region")
    second = next(c for c in cases if c["origin"]["category"] == "followup" and c["turn_no"] == 2)
    assert second["origin"]["needs_context"] and second["origin"]["kind"] == "generated" and second["expected_sql"]
    clarify = next(c for c in cases if c["type"] == "clarify")
    assert clarify["expected_sql"] == "" and clarify["origin"]["note"] and clarify["groups"][0]["name"] == "Vague"
    assert client.get(f"/api/generate/{bid}").status_code == 404                # the batch is gone once approved
    assert client.post(f"/api/generate/{bid}/approve", json={}).status_code == 404


def test_approving_only_some_items_discards_the_rest(make_client):
    client = make_client()
    batch = wait(client, upload(client, [SHOP], per_category=2, categories='["simple"]').json()["batch_id"])
    first = batch["items"][0]["item_id"]
    done = client.post(f"/api/generate/{batch['batch_id']}/approve", json={"item_ids": [first]}).json()
    assert done["items"] == 1 and done["discarded"] == 1 and len(client.get("/api/test-cases").json()) == 1
    assert client.get("/api/generate").json() == []


def test_questions_are_saved_as_they_are_written_so_a_dropped_connection_loses_nothing(make_client):
    gate = threading.Event()
    client = make_client(model=FakeModel(hold=gate))
    bid = upload(client, [SHOP], per_category=2).json()["batch_id"]
    time.sleep(0.2)
    running = client.get(f"/api/generate/{bid}").json()
    assert running["status"] == "running" and running["total_tasks"] == 14 and running["items"] == []
    assert upload(client, [SHOP]).status_code == 409                                 # one at a time
    gate.set()
    batch = wait(client, bid)
    assert len(batch["items"]) == 14
    listed = client.get("/api/generate").json()                                      # a fresh listing (new tab) still finds it
    assert listed[0]["batch_id"] == bid and listed[0]["item_count"] == 14 and listed[0]["case_count"] == 18
    assert listed[0]["by_category"]["vague"] == 2


def test_cancelling_keeps_what_was_already_written(make_client):
    gate = threading.Event()
    client = make_client(model=FakeModel(hold=gate), generate_workers=1)
    bid = upload(client, [SHOP], per_category=3).json()["batch_id"]
    time.sleep(0.2)
    assert client.post(f"/api/generate/{bid}/cancel").status_code == 202
    gate.set()
    batch = wait(client, bid)
    assert batch["status"] == "cancelled" and len(batch["items"]) < 21
    assert client.delete(f"/api/generate/{bid}").status_code == 200                 # once stopped, it can be discarded
    assert client.get(f"/api/generate/{bid}").status_code == 404


def test_discarding_while_still_writing_asks_it_to_stop_instead(make_client):
    gate = threading.Event()
    client = make_client(model=FakeModel(hold=gate), generate_workers=1)
    bid = upload(client, [SHOP], per_category=3).json()["batch_id"]
    time.sleep(0.2)
    assert client.delete(f"/api/generate/{bid}").status_code == 409
    gate.set()
    assert wait(client, bid)["status"] == "cancelled"


def test_a_restart_marks_unfinished_batches_but_keeps_their_items(make_client):
    client = make_client()
    store = client.app.state.store
    store.save_batch({"batch_id": "old", "status": "running", "created_at": "2026-01-01T00:00:00+00:00",
                      "expires_at": "2999-01-01T00:00:00+00:00", "items": [{"item_id": "x", "category": "simple", "turns": [{}]}]})
    GenerationManager(client.app.state.config, store, llm=FakeModel())
    assert store.get_batch("old")["status"] == "interrupted" and len(store.get_batch("old")["items"]) == 1


def test_unapproved_batches_are_deleted_after_their_time_is_up(make_client):
    client = make_client()
    store = client.app.state.store
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store.save_batch({"batch_id": "stale", "status": "ready", "created_at": past, "expires_at": past, "items": []})
    store.save_batch({"batch_id": "busy", "status": "running", "created_at": past, "expires_at": past, "items": []})
    assert [b["batch_id"] for b in client.get("/api/generate").json()] == ["busy"]     # expired one is gone, running one is not
    assert client.get("/api/generate/stale").status_code == 404


def test_limits_and_unusable_uploads_are_reported_clearly(make_client):
    client = make_client(generate_max_file_mb=1, generate_max_files=2, dialect="mysql")
    limits = client.get("/api/generate/limits").json()
    assert limits["max_files"] == 2 and limits["dialect"] == "mysql" and limits["formats"] == ["sql", "ddl", "txt"]
    assert [c["key"] for c in limits["categories"]] == CATEGORY_KEYS
    assert upload(client, [SHOP, STAFF, ("c.sql", b"CREATE TABLE c (id INT);", "text/plain")]).status_code == 422
    big = ("big.sql", b"-- " + b"a" * (2 * 1024 * 1024), "text/plain")
    too_big = upload(client, [big])
    assert too_big.status_code == 413 and "1 MB" in too_big.json()["detail"]
    wrong = upload(client, [("deck.pptx", b"zzz", "application/octet-stream")])
    assert wrong.status_code == 422 and "unsupported file type" in wrong.json()["detail"] and ".sql or .ddl" in wrong.json()["detail"]
    assert upload(client, [SHOP], per_category=0).status_code == 422
    assert upload(client, [SHOP], categories="[]").status_code == 422
    assert upload(client, [SHOP], categories="not json").status_code == 422
    assert upload(client, [SHOP], turns=9).status_code == 422


def test_a_file_in_the_wrong_dialect_or_without_tables_fails_the_batch_and_says_why(make_client):
    client = make_client()                                                          # postgres
    backticks = ("mysql.sql", b"CREATE TABLE `orders` (`id` int, `name` varchar(5));", "text/plain")
    batch = wait(client, upload(client, [backticks]).json()["batch_id"])
    assert batch["status"] == "failed" and "could be read as postgres" in batch["error"]
    nothing = wait(client, upload(client, [("views.sql", b"CREATE VIEW v AS SELECT 1;", "text/plain")]).json()["batch_id"])
    assert nothing["status"] == "failed" and "no CREATE TABLE statements" in nothing["error"]


def test_a_mysql_file_is_read_when_the_dialect_is_mysql(make_client):
    client = make_client(dialect="mysql")

    class MysqlModel(FakeModel):
        pass

    ddl = ("shop.sql", b"CREATE TABLE `customers` (`id` int PRIMARY KEY, `name` varchar(50), `region` varchar(20)) ENGINE=InnoDB;", "text/plain")
    batch = wait(client, upload(client, [ddl], per_category=1, categories='["simple"]').json()["batch_id"])
    assert batch["status"] == "ready" and batch["files"][0]["tables"] == 1


def test_one_unusable_file_does_not_stop_the_others(make_client):
    client = make_client()
    bad = ("empty.sql", b"  \n", "text/plain")
    batch = wait(client, upload(client, [bad, SHOP], per_category=1, categories='["simple","vague"]').json()["batch_id"])
    assert batch["status"] == "ready" and len(batch["items"]) == 2
    assert "is empty" in next(f for f in batch["files"] if f["name"] == "empty.sql")["error"]


def test_model_failures_are_reported_per_question_and_do_not_lose_the_rest(make_client):
    client = make_client(model=FakeModel(fail_first=1000))
    client.app.state.generator._sleep = lambda s: None          # do not really wait between retries
    batch = wait(client, upload(client, [SHOP], per_category=1, categories='["simple","vague"]').json()["batch_id"])
    assert batch["status"] == "failed" and batch["items"] == [] and "could not be reached" in batch["error"]
    assert len(batch["errors"]) == 2


def test_generated_chat_ids_are_short_and_carry_on_across_approvals(make_client):
    client = make_client()
    first = wait(client, upload(client, [SHOP], per_category=2, turns=2).json()["batch_id"])
    client.post(f"/api/generate/{first['batch_id']}/approve", json={})
    cases = client.get("/api/test-cases").json()
    chats = sorted({c["chat_id"] for c in cases})
    assert chats == sorted(f"{key}-{n}" for key in CATEGORY_KEYS for n in (1, 2))
    assert sorted(c["turn_no"] for c in cases if c["chat_id"] == "followup-1") == [1, 2]      # one chat, both turns

    second = wait(client, upload(client, [SHOP], per_category=1, turns=2).json()["batch_id"])       # a second approval continues the numbering
    client.post(f"/api/generate/{second['batch_id']}/approve", json={})
    everything = {c["chat_id"] for c in client.get("/api/test-cases").json()}
    assert everything - set(chats) == {f"{key}-3" for key in CATEGORY_KEYS}
