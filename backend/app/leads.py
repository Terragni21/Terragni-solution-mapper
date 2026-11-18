"""
Contact-form leads and visitor questions for Terragni Solution Mapper.

Everything is saved in ONE Oracle table, WEBSITE_LEAD (local Oracle on
Terragni-10, nothing goes to any cloud):

    ENTRY_TYPE = 'CONTACT'   a contact-form submission (name, email, ...
                             plus the question they asked in the mapper)
    ENTRY_TYPE = 'QUESTION'  a question typed in the mapper (contact
                             columns are empty)

A backup copy is also written to two files, so nothing is lost if the
Oracle computer is switched off:
    backend/data/leads/leads.jsonl   (contact-form submissions)
    backend/data/leads/visits.jsonl  (every question asked)

Old backup entries can be copied into Oracle with:
    python -m backend.scripts.import_old_leads
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from .confidentiality import redact_confidential_text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

LEADS_DIR = Path(__file__).resolve().parents[1] / "data" / "leads"
LEADS_FILE = LEADS_DIR / "leads.jsonl"
VISITS_FILE = LEADS_DIR / "visits.jsonl"

TABLE = "WEBSITE_LEAD"

_WRITE_LOCK = threading.Lock()
_TABLE_LOCK = threading.Lock()
_TABLE_READY = False

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, record: dict[str, Any]) -> None:
    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


# ============================================================
# THE ORACLE TABLE
# ============================================================

CREATE_TABLE_SQL = f"""
CREATE TABLE {TABLE} (
    ENTRY_KEY           VARCHAR2(64)    PRIMARY KEY,
    ENTRY_TYPE          VARCHAR2(10)    NOT NULL,
    SUBMITTED_AT        TIMESTAMP,
    REFERENCE_NO        VARCHAR2(20),
    FULL_NAME           VARCHAR2(200 CHAR),
    EMAIL               VARCHAR2(200 CHAR),
    ORGANISATION        VARCHAR2(300 CHAR),
    PHONE               VARCHAR2(60),
    MESSAGE             CLOB,
    INDUSTRY            VARCHAR2(200 CHAR),
    VISITOR_ROLE        VARCHAR2(300 CHAR),
    SEARCH_PATH         VARCHAR2(40),
    OUTCOME             VARCHAR2(60),
    QUESTION            CLOB,
    SUMMARY             VARCHAR2(2000 CHAR),
    SUGGESTED_SERVICES  VARCHAR2(1000 CHAR),
    CREATED_AT          TIMESTAMP DEFAULT SYSTIMESTAMP
)
"""

INSERT_SQL = f"""
INSERT INTO {TABLE} (
    ENTRY_KEY, ENTRY_TYPE, SUBMITTED_AT, REFERENCE_NO, FULL_NAME, EMAIL,
    ORGANISATION, PHONE, MESSAGE, INDUSTRY, VISITOR_ROLE, SEARCH_PATH,
    OUTCOME, QUESTION, SUMMARY, SUGGESTED_SERVICES
) VALUES (
    :entry_key, :entry_type, :submitted_at, :reference_no, :full_name, :email,
    :organisation, :phone, :message, :industry, :visitor_role, :search_path,
    :outcome, :question, :summary, :suggested_services
)
"""


def ensure_table(cursor) -> None:
    """Create WEBSITE_LEAD the first time it is needed."""
    global _TABLE_READY
    if _TABLE_READY:
        return
    with _TABLE_LOCK:
        if _TABLE_READY:
            return
        cursor.execute(
            "SELECT COUNT(*) FROM user_tables WHERE table_name = :t", {"t": TABLE}
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(CREATE_TABLE_SQL)
        _TABLE_READY = True


def _local_time(iso_text: str):
    """'2026-11-18T06:30:00+00:00' -> this computer's local time (IST), no zone."""
    try:
        moment = datetime.fromisoformat(str(iso_text))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def question_key(at: str, text: str) -> str:
    """Stable id for a question row, so the same question is never stored twice."""
    return "Q-" + hashlib.sha1(f"{at}|{text}".encode("utf-8")).hexdigest()[:40]


def contact_row(record: dict[str, Any]) -> dict[str, Any]:
    context = record.get("context") or {}
    return {
        "entry_key": record["reference"],
        "entry_type": "CONTACT",
        "submitted_at": _local_time(record.get("submitted_at")),
        "reference_no": record["reference"],
        "full_name": record.get("name", ""),
        "email": record.get("email", ""),
        "organisation": record.get("organisation", ""),
        "phone": record.get("phone", ""),
        "message": record.get("message", ""),
        "industry": context.get("industry", ""),
        "visitor_role": context.get("role", ""),
        "search_path": context.get("path", ""),
        "outcome": "",
        "question": context.get("question", ""),
        "summary": context.get("summary", ""),
        "suggested_services": ", ".join(context.get("suggested_services") or [])[:1000],
    }


def question_row(visit: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_key": question_key(visit.get("at", ""), visit.get("text", "")),
        "entry_type": "QUESTION",
        "submitted_at": _local_time(visit.get("at")),
        "reference_no": None,
        "full_name": None,
        "email": None,
        "organisation": None,
        "phone": None,
        "message": None,
        "industry": visit.get("industry", ""),
        "visitor_role": visit.get("role", ""),
        "search_path": visit.get("path", ""),
        "outcome": visit.get("outcome", ""),
        "question": visit.get("text", ""),
        "summary": None,
        "suggested_services": None,
    }


def insert_rows(rows: list[dict[str, Any]]) -> int:
    """Insert rows into WEBSITE_LEAD, skipping ones already there. Returns the number added."""
    import oracledb
    from ..database.connection import get_connection

    if not rows:
        return 0
    added = 0
    connection = get_connection()
    try:
        cursor = connection.cursor()
        ensure_table(cursor)
        for row in rows:
            cursor.setinputsizes(message=oracledb.DB_TYPE_CLOB, question=oracledb.DB_TYPE_CLOB)
            try:
                cursor.execute(INSERT_SQL, row)
                added += 1
            except oracledb.IntegrityError:
                pass  # already saved earlier
        connection.commit()
    finally:
        connection.close()
    return added


def _save_in_background(row: dict[str, Any]) -> None:
    """Save one row to Oracle without slowing the page. Never raises."""
    def work():
        try:
            insert_rows([row])
        except Exception as exc:
            print(
                f"Warning: {row['entry_type']} entry not saved to Oracle "
                f"(it is still in the backup file): {exc}"
            )

    threading.Thread(target=work, daemon=True).start()


# ============================================================
# PUBLIC INTERFACE (used by app.py)
# ============================================================

def validate_lead(payload: dict[str, Any]) -> list[str]:
    """Return a list of problems with the submitted form (empty when valid)."""
    errors = []

    if not _text(payload.get("name"), 120):
        errors.append("Please enter your name.")

    email = _text(payload.get("email"), 200)
    if not EMAIL_RE.match(email):
        errors.append("Please enter a valid work email.")

    if not payload.get("consent"):
        errors.append("Please agree that Terragni may contact you.")

    return errors


def save_lead(payload: dict[str, Any]) -> dict[str, Any]:
    """Store a contact-form submission (backup file + Oracle) and return it."""
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    reference = "TSM-" + uuid.uuid4().hex[:8].upper()

    record = {
        "reference": reference,
        "submitted_at": _now(),
        "name": _text(payload.get("name"), 120),
        "email": _text(payload.get("email"), 200),
        "organisation": _text(payload.get("organisation"), 160),
        "phone": _text(payload.get("phone"), 40),
        "message": _text(payload.get("message"), 3000),
        "context": {
            "industry": _text(context.get("industry"), 120),
            "role": _text(context.get("role"), 160),
            "path": _text(context.get("path"), 20),
            "question": redact_confidential_text(_text(context.get("question"), 3000)),
            "summary": _text(context.get("summary"), 600),
            "suggested_services": [
                _text(item, 120) for item in (context.get("suggested_services") or [])[:5]
            ],
        },
    }

    # 1. Backup file first - always works, even if Oracle is off.
    _append(LEADS_FILE, record)

    # 2. Oracle table WEBSITE_LEAD.
    _save_in_background(contact_row(record))

    return record


def log_visit(
    *,
    industry: str,
    role: str,
    path: str,
    outcome: str,
    text: str,
) -> None:
    """Record one question (backup file + Oracle). Never raises."""
    try:
        visit = {
            "at": _now(),
            "industry": _text(industry, 120),
            "role": _text(role, 160),
            "path": path,
            "outcome": outcome,
            "text": _text(redact_confidential_text(text), 600),
        }
        _append(VISITS_FILE, visit)
        _save_in_background(question_row(visit))
    except Exception:
        pass
