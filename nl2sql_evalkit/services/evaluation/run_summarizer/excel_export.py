"""The results of a version as an Excel workbook."""
import io
import json
from typing import Any

import pandas as pd

from nl2sql_evalkit.utils import node_order

# Optional receipt columns — included in Excel when at least one row has a value.
OPTIONAL_RECEIPT_COLUMNS = ["flags"]


EXCEL_CELL_LIMIT = 32000


def cell_value(v) -> Any:
    """Return ``v`` in a form Excel can store in one cell.

    Lists and dicts become JSON text. Text has its line breaks replaced by spaces, so rows keep a fixed height,
    and is cut to ``EXCEL_CELL_LIMIT`` characters. Any other value is returned unchanged.
    """
    if isinstance(v, (list, dict)):
        v = json.dumps(v, ensure_ascii=False)
    if isinstance(v, str):
        # Collapse newlines so Excel doesn't expand row height
        v = v.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        if len(v) > EXCEL_CELL_LIMIT:
            v = v[:EXCEL_CELL_LIMIT]
    return v


def build_results_workbook(data: dict) -> bytes:
    """A Summary sheet and a Results sheet for one version's data (``EvalStore.get``)."""
    rows = data["rows"]
    nodes = node_order(rows)

    # ── human-readable column order for the Results sheet ──────────────
    # Primary identification
    ID_COLS   = ["chat_id", "turn_no", "type", "groups", "status"]
    # The question/answer triplet — the heart of every row
    QA_COLS   = ["question", "expected_sql", "expected_tables", "expected_columns", "generated_answer"]
    # Judge scores + comments right after the answers
    JUDGE_COLS = ["sql_marks", "sql_remarks", "sql_suggestion", "schema_marks", "schema_remarks"]
    # What the checks found in the SQL (kept on each row as ``sql_checks``)
    CHECK_COLS = ["syntax_ok", "read_only", "tables_missing", "columns_missing", "joins_match"]
    # Timing
    TIME_COLS = ["total_time_taken", *[f"node_{n}" for n in nodes]]
    # Optional: anything the run flagged
    OPT_PRESENT = [c for c in OPTIONAL_RECEIPT_COLUMNS if any(r.get(c) is not None for r in rows)]
    # Anything else logged that isn't already covered
    _covered = set(ID_COLS + QA_COLS + JUDGE_COLS + CHECK_COLS + ["sql_checks", "generated_sql"] +
                   ["total_time_taken"] + OPT_PRESENT +
                   ["session_id", "tc_id", "step_inputs", "step_outputs", "node_timings", "version"])
    extra: list[str] = []
    for r in rows:
        for k in r:
            if k not in _covered and k not in extra:
                extra.append(k)

    columns = [*ID_COLS, *QA_COLS, *JUDGE_COLS, *CHECK_COLS,
               *TIME_COLS, *OPT_PRESENT, *extra]

    records = []
    for r in rows:
        rec: dict = {}
        for c in ID_COLS:
            rec[c] = ", ".join(r.get("groups") or []) if c == "groups" else cell_value(r.get(c))
        for c in QA_COLS:
            rec[c] = cell_value(r.get(c))
        for c in JUDGE_COLS:
            rec[c] = cell_value(r.get(c))
        checks = r.get("sql_checks") or {}
        for c in CHECK_COLS:
            rec[c] = cell_value(checks.get(c))
        rec["total_time_taken"] = cell_value(r.get("total_time_taken"))
        nt = r.get("node_timings") or {}
        for n in nodes:
            rec[f"node_{n}"] = nt.get(n)
        for c in OPT_PRESENT:
            rec[c] = cell_value(r.get(c))
        for c in extra:
            rec[c] = cell_value(r.get(c))
        records.append(rec)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        # Sheet 1 — Summary scores
        s = data["summary"]
        summary_display = {
            "version": s.get("version"), "date": s.get("date"),
            "dataset": s.get("dataset"), "notes": s.get("notes", ""),
            "groups": ", ".join(s.get("group_names") or []),
            "total_questions": s.get("total_rows"), "failed": s.get("failed_rows"),
            "avg_sql_marks": s.get("avg_sql_marks"),
            "avg_schema_marks": s.get("avg_schema_marks"),
            "avg_total_time_s": s.get("avg_total_time"),
            "judge_model": s.get("judge_model"),
            "duration_seconds": s.get("duration_seconds"),
            "comment": s.get("comment"),
        }
        pd.DataFrame([summary_display]).to_excel(xw, sheet_name="Summary", index=False)

        # Sheet 2 — Full results
        df_results = pd.DataFrame(records, columns=columns)
        df_results.to_excel(xw, sheet_name="Results", index=False)

        # Formatting: auto-width columns, wrap text in answer and remark cells
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        WRAP_COLS = {"question", "expected_sql", "generated_answer",
                     "sql_remarks", "schema_remarks"}
        HEADER_FILL = PatternFill("solid", fgColor="1A5276")
        HEADER_FONT = Font(bold=True, color="FFFFFF")

        for ws in xw.book.worksheets:
            # Style header row
            for cell in ws[1]:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(wrap_text=False, vertical="center")

            # Style data rows
            for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
                for cell in row:
                    col_name = ws.cell(row=1, column=cell.column).value or ""
                    should_wrap = col_name in WRAP_COLS
                    cell.alignment = Alignment(wrap_text=should_wrap, vertical="top")
                # Taller rows for the Results sheet to show wrapped text
                if ws.title == "Results":
                    ws.row_dimensions[row_idx].height = 60

            # Auto-width (cap at 60 for readability)
            for col_idx, col_cells in enumerate(ws.columns, start=1):
                col_letter = get_column_letter(col_idx)
                header = ws.cell(row=1, column=col_idx).value or ""
                if header in WRAP_COLS:
                    ws.column_dimensions[col_letter].width = 45
                else:
                    max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
                    ws.column_dimensions[col_letter].width = min(max_len + 2, 30)

    return buf.getvalue()
