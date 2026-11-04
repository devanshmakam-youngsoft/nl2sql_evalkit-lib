"""The optional reply style of a test case: created, edited, imported, exported to a run and downloaded in the template."""
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from nl2sql_evalkit.core.config import Config
from nl2sql_evalkit.main import create_app
from nl2sql_evalkit.schemas.internal.run_selection import cases_to_dataframe
from nl2sql_evalkit.services.db_services import EvalStore
from nl2sql_evalkit.services.testcases.testcase_import import (
    detect_mapping,
    parse_rows,
    template_workbook,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "s.json")
    yield s
    s.close()


@pytest.fixture
def client(tmp_path):
    cfg = Config(data_dir=tmp_path / "api", require_login=False, eval_secret="s")
    with TestClient(create_app(cfg, fn=lambda q: "a")) as c:
        yield c


def parsed(**cols):
    df = pd.DataFrame({k: list(v) for k, v in cols.items()})
    return parse_rows(df, detect_mapping(list(df.columns)))


# ---- import --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("header", ["reply_style", "Reply Style", "response_style", "Style", "persona", "tone"])
def test_the_reply_style_column_is_recognised_under_common_names(header):
    rows, problems = parsed(question=["Totals?"], expected_tables=["orders"], **{header: ["Friendly, two sentences"]})
    assert not problems and rows[0]["reply_style"] == "Friendly, two sentences"


def test_a_file_without_the_column_gives_an_empty_style():
    rows, _ = parsed(question=["Totals?"], expected_tables=["orders"])
    assert rows[0]["reply_style"] == ""


def test_the_template_has_the_reply_style_column_and_explains_it():
    df = pd.read_excel(io.BytesIO(template_workbook()), sheet_name="dataset", dtype=str)
    assert "reply_style" in df.columns and df["reply_style"].notna().sum() == 1
    rows, problems = parse_rows(df, detect_mapping(list(df.columns)))
    assert not problems and rows[0]["reply_style"]
    guide = pd.read_excel(io.BytesIO(template_workbook()), sheet_name="How to fill", dtype=str)
    assert "reply_style" in set(guide.iloc[:, 0].dropna())


def test_importing_saves_the_style_and_changing_it_makes_a_new_version(store):
    row = {"row": 2, "chat_id": "c1", "turn_no": 1, "type": "answer", "question": "q1", "expected_sql": "SELECT 1",
           "expected_tables": "", "expected_columns": "", "reply_style": "Friendly", "groups": []}
    assert store.import_cases([row])["new"] == 1
    assert store.list_test_cases()[0]["reply_style"] == "Friendly"
    assert store.import_cases([row])["unchanged"] == 1
    assert store.import_cases([{**row, "reply_style": "Formal"}])["updated"] == 1
    case = store.list_test_cases()[0]
    assert case["reply_style"] == "Formal" and case["version"] == 2


def test_importing_a_data_frame_into_a_group_keeps_the_style(store):
    gid = store.create_group("Sales")
    df = pd.DataFrame([("c1", 1, "answer", "q1", "SELECT 1", "Friendly")],
                      columns=["chat_id", "turn_no", "type", "question", "expected_sql", "reply_style"])
    store.import_into_group(gid, df)
    assert store.list_test_cases()[0]["reply_style"] == "Friendly"


# ---- creating and editing -------------------------------------------------------------------------------

def test_a_test_case_is_created_with_a_style_and_edited_with_a_new_version(store):
    made = store.create_test_case("c1", 1, "Totals?", "SELECT 1", reply_style="  Friendly  ")
    assert made["reply_style"] == "Friendly"
    edited = store.edit_test_case(made["tc_id"], {"reply_style": "Formal, one sentence"})
    assert edited["reply_style"] == "Formal, one sentence" and edited["version"] == 2
    cleared = store.edit_test_case(made["tc_id"], {"reply_style": ""})
    assert cleared["reply_style"] == "" and cleared["version"] == 3


def test_the_api_creates_edits_and_lists_the_style(client):
    made = client.post("/api/test-cases", json={"chat_id": "c1", "turn_no": 1, "question": "Totals?", "expected_sql": "SELECT 1",
                                                "reply_style": "Friendly"}).json()
    assert made["reply_style"] == "Friendly"
    edited = client.patch(f"/api/test-cases/{made['tc_id']}", json={"reply_style": "Short"}).json()
    assert edited["reply_style"] == "Short"
    assert client.get("/api/test-cases").json()[0]["reply_style"] == "Short"
    plain = client.post("/api/test-cases", json={"chat_id": "c2", "turn_no": 1, "question": "More?", "expected_sql": "SELECT 2"}).json()
    assert plain["reply_style"] == ""


def test_the_api_imports_the_style_from_a_file(client):
    text = "question,expected_sql,reply_style\nTotals?,SELECT 1,Friendly\nMore?,SELECT 2,\n"
    done = client.post("/api/test-cases/import", files={"file": ("c.csv", text.encode(), "text/csv")}).json()
    assert done["new"] == 2
    styles = {c["question"]: c["reply_style"] for c in client.get("/api/test-cases").json()}
    assert styles == {"Totals?": "Friendly", "More?": ""}


# ---- running ---------------------------------------------------------------------------------------------

def test_a_run_gets_the_style_of_each_test_case(store):
    store.create_test_case("c1", 1, "Totals?", "SELECT 1", reply_style="Friendly")
    store.create_test_case("c2", 1, "More?", "SELECT 2")
    cases = store.list_test_cases()
    df = cases_to_dataframe(cases, {})
    by_question = {r.question: getattr(r, "reply_style", "") for r in df.itertuples(index=False)}
    assert by_question["Totals?"] == "Friendly" and (pd.isna(by_question["More?"]) or by_question["More?"] == "")      # a blank is NaN in the frame
