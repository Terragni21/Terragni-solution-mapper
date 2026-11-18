"""
Make an Excel file of all contact-form entries and visitor questions.

    python -m backend.scripts.export_leads_excel

Reads the Oracle table WEBSITE_LEAD. If Oracle (Terragni-10) cannot be
reached, it reads the backup files instead.

The file is saved in backend/data/leads/exports/ with two sheets:
    Contact form   - everyone who filled the contact form
    Questions      - every question typed in the Solution Mapper

The file contains personal details: share it only inside Terragni.
It is never added to git (backend/data/leads/ is in .gitignore).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.leads import (  # noqa: E402
    LEADS_DIR,
    LEADS_FILE,
    TABLE,
    VISITS_FILE,
    contact_row,
    question_row,
)
from backend.scripts.import_old_leads import read_lines  # noqa: E402

CONTACT_COLUMNS = [
    ("Date & time", "submitted_at"),
    ("Reference", "reference_no"),
    ("Name", "full_name"),
    ("Email", "email"),
    ("Organisation", "organisation"),
    ("Phone", "phone"),
    ("Message", "message"),
    ("Industry", "industry"),
    ("Role", "visitor_role"),
    ("Question asked", "question"),
    ("Problem summary", "summary"),
    ("Suggested services", "suggested_services"),
]

QUESTION_COLUMNS = [
    ("Date & time", "submitted_at"),
    ("Question", "question"),
    ("Industry", "industry"),
    ("Role", "visitor_role"),
    ("Path", "search_path"),
    ("Result", "outcome"),
]


def from_oracle() -> list[dict]:
    from backend.database.connection import get_connection

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT ENTRY_TYPE, SUBMITTED_AT, REFERENCE_NO, FULL_NAME, EMAIL,
                   ORGANISATION, PHONE, MESSAGE, INDUSTRY, VISITOR_ROLE,
                   SEARCH_PATH, OUTCOME, QUESTION, SUMMARY, SUGGESTED_SERVICES
            FROM {TABLE}
            ORDER BY SUBMITTED_AT DESC
            """
        )
        names = [
            "entry_type", "submitted_at", "reference_no", "full_name", "email",
            "organisation", "phone", "message", "industry", "visitor_role",
            "search_path", "outcome", "question", "summary", "suggested_services",
        ]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def from_backup_files() -> list[dict]:
    rows = [contact_row(r) for r in read_lines(LEADS_FILE) if r.get("reference")]
    rows += [question_row(v) for v in read_lines(VISITS_FILE) if v.get("text")]
    rows.sort(key=lambda r: r["submitted_at"] or datetime.min, reverse=True)
    return rows


def add_sheet(workbook, title: str, columns, rows) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    sheet = workbook.create_sheet(title)
    sheet.append([label for label, _ in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F2557")
    for row in rows:
        sheet.append([row.get(key) for _, key in columns])

    for index, (label, key) in enumerate(columns, start=1):
        letter = sheet.cell(row=1, column=index).column_letter
        wide = key in ("question", "message", "summary", "suggested_services")
        sheet.column_dimensions[letter].width = 50 if wide else 20
        if key == "submitted_at":
            for cell in sheet[letter][1:]:
                cell.number_format = "dd-mmm-yyyy hh:mm"
    for line in sheet.iter_rows(min_row=2):
        for cell in line:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def main() -> None:
    try:
        from openpyxl import Workbook
    except ImportError:
        print("Please install the Excel library first:  pip install openpyxl")
        return

    try:
        rows = from_oracle()
        source = f"Oracle table {TABLE}"
    except Exception as exc:
        print(f"Could not read Oracle ({exc}).")
        print("Using the backup files instead.")
        rows = from_backup_files()
        source = "backup files"

    contacts = [r for r in rows if r["entry_type"] == "CONTACT"]
    questions = [r for r in rows if r["entry_type"] == "QUESTION"]

    workbook = Workbook()
    workbook.remove(workbook.active)
    add_sheet(workbook, "Contact form", CONTACT_COLUMNS, contacts)
    add_sheet(workbook, "Questions", QUESTION_COLUMNS, questions)

    out_dir = LEADS_DIR / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"website_leads_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
    workbook.save(out_file)

    print(f"Read from      : {source}")
    print(f"Contact entries: {len(contacts)}")
    print(f"Questions      : {len(questions)}")
    print(f"Excel saved to : {out_file}")


if __name__ == "__main__":
    main()
