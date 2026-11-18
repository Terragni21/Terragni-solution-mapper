"""
Copy the contact-form entries and questions that were saved BEFORE the
Oracle table existed (the backup files) into the Oracle table WEBSITE_LEAD.

    python -m backend.scripts.import_old_leads

Safe to run again: entries already in Oracle are skipped. Also useful if
Terragni-10 was switched off for a while - run it to fill the gap.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.leads import (  # noqa: E402
    LEADS_FILE,
    TABLE,
    VISITS_FILE,
    contact_row,
    insert_rows,
    question_row,
)


def read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return items


def main() -> None:
    contacts = [contact_row(r) for r in read_lines(LEADS_FILE) if r.get("reference")]
    questions = [question_row(v) for v in read_lines(VISITS_FILE) if v.get("text")]

    print(f"Contact-form entries in backup : {len(contacts)}")
    print(f"Questions in backup            : {len(questions)}")

    added_contacts = insert_rows(contacts)
    added_questions = insert_rows(questions)

    print(f"Added to Oracle {TABLE}: {added_contacts} contact entries, "
          f"{added_questions} questions (the rest were already there).")


if __name__ == "__main__":
    main()
