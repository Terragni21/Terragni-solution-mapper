"""
Lead capture, query logging and database tracking for Terragni Solution Mapper.

Stores every visitor interaction in:
    1. Database (PostgreSQL via DATABASE_URL, Oracle if configured, or SQLite leads.db)
    2. Append-only JSON Lines backup files:
       - backend/data/leads/leads.jsonl   (contact-form submissions + role/industry/query context)
       - backend/data/leads/visits.jsonl  (every question asked + role/industry/outcome)

Allows full tracking of user inquiries, queries, roles, and industries for
the Terragni consulting and sales teams.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
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
SQLITE_DB_FILE = LEADS_DIR / "leads.db"

_WRITE_LOCK = threading.Lock()
_DB_LOCK = threading.Lock()
_DB_INITIALIZED = False

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
# DATABASE PERSISTENCE FOR LEADS & QUERIES
# ============================================================

def _init_db_tables():
    """Ensure lead and query tables exist."""
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return

    with _DB_LOCK:
        if _DB_INITIALIZED:
            return

        # 1. Check for PostgreSQL DATABASE_URL
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url)
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_leads (
                            reference VARCHAR(32) PRIMARY KEY,
                            submitted_at VARCHAR(40),
                            name VARCHAR(120),
                            email VARCHAR(200),
                            organisation VARCHAR(160),
                            phone VARCHAR(40),
                            message TEXT,
                            industry VARCHAR(120),
                            role VARCHAR(160),
                            question TEXT,
                            summary TEXT,
                            suggested_services TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE TABLE IF NOT EXISTS user_queries (
                            id SERIAL PRIMARY KEY,
                            logged_at VARCHAR(40),
                            industry VARCHAR(120),
                            role VARCHAR(160),
                            path VARCHAR(40),
                            outcome VARCHAR(40),
                            query_text TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
                conn.close()
                _DB_INITIALIZED = True
                return
            except Exception:
                pass

        # 2. SQLite local database
        try:
            LEADS_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(SQLITE_DB_FILE))
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_leads (
                    reference TEXT PRIMARY KEY,
                    submitted_at TEXT,
                    name TEXT,
                    email TEXT,
                    organisation TEXT,
                    phone TEXT,
                    message TEXT,
                    industry TEXT,
                    role TEXT,
                    question TEXT,
                    summary TEXT,
                    suggested_services TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logged_at TEXT,
                    industry TEXT,
                    role TEXT,
                    path TEXT,
                    outcome TEXT,
                    query_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            conn.close()
            _DB_INITIALIZED = True
        except Exception:
            pass


def _save_lead_to_db(record: dict[str, Any]) -> None:
    """Save the lead record into the database."""
    try:
        _init_db_tables()
        context = record.get("context") or {}
        services_str = ", ".join(context.get("suggested_services") or [])

        # 1. Try PostgreSQL
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url)
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_leads (
                            reference, submitted_at, name, email, organisation,
                            phone, message, industry, role, question, summary, suggested_services
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (reference) DO NOTHING
                    """, (
                        record["reference"],
                        record["submitted_at"],
                        record["name"],
                        record["email"],
                        record["organisation"],
                        record["phone"],
                        record["message"],
                        context.get("industry", ""),
                        context.get("role", ""),
                        context.get("question", ""),
                        context.get("summary", ""),
                        services_str
                    ))
                    conn.commit()
                conn.close()
                return
            except Exception:
                pass

        # 2. Fallback to SQLite
        with _DB_LOCK:
            conn = sqlite3.connect(str(SQLITE_DB_FILE))
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO user_leads (
                    reference, submitted_at, name, email, organisation,
                    phone, message, industry, role, question, summary, suggested_services
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record["reference"],
                record["submitted_at"],
                record["name"],
                record["email"],
                record["organisation"],
                record["phone"],
                record["message"],
                context.get("industry", ""),
                context.get("role", ""),
                context.get("question", ""),
                context.get("summary", ""),
                services_str
            ))
            conn.commit()
            conn.close()
    except Exception:
        pass


def _log_visit_to_db(
    *,
    logged_at: str,
    industry: str,
    role: str,
    path: str,
    outcome: str,
    text: str,
) -> None:
    """Save query log into the database."""
    try:
        _init_db_tables()

        # 1. Try PostgreSQL
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url)
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_queries (
                            logged_at, industry, role, path, outcome, query_text
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        logged_at,
                        industry,
                        role,
                        path,
                        outcome,
                        text
                    ))
                    conn.commit()
                conn.close()
                return
            except Exception:
                pass

        # 2. Fallback to SQLite
        with _DB_LOCK:
            conn = sqlite3.connect(str(SQLITE_DB_FILE))
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_queries (
                    logged_at, industry, role, path, outcome, query_text
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                logged_at,
                industry,
                role,
                path,
                outcome,
                text
            ))
            conn.commit()
            conn.close()
    except Exception:
        pass


# ============================================================
# PUBLIC INTERFACE
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
    """Store a contact-form submission in DB and JSONL, returning the saved record."""
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

    # 1. Append to JSON Lines backup file
    _append(LEADS_FILE, record)

    # 2. Save directly to Database
    _save_lead_to_db(record)

    return record


def log_visit(
    *,
    industry: str,
    role: str,
    path: str,
    outcome: str,
    text: str,
) -> None:
    """Record one question in DB and JSONL. Never raises: logging must not break the page."""
    try:
        now_ts = _now()
        safe_text = _text(redact_confidential_text(text), 600)
        safe_industry = _text(industry, 120)
        safe_role = _text(role, 160)

        # 1. Append to JSON Lines backup file
        _append(
            VISITS_FILE,
            {
                "at": now_ts,
                "industry": safe_industry,
                "role": safe_role,
                "path": path,
                "outcome": outcome,
                "text": safe_text,
            },
        )

        # 2. Save directly to Database
        _log_visit_to_db(
            logged_at=now_ts,
            industry=safe_industry,
            role=safe_role,
            path=path,
            outcome=outcome,
            text=safe_text,
        )
    except Exception:
        pass
