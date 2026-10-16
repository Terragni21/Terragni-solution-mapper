"""
Lead capture and visit logging for the Terragni Solution Mapper.

Two append-only JSON Lines files are written under backend/data/leads/:

    leads.jsonl   - contact-form submissions, with the visitor's journey context
    visits.jsonl  - one line per question asked (role, industry, path, outcome,
                    redacted text). Lines with outcome "no_match" form the gap
                    log of problems Terragni has no example for yet.

Files keep the prototype simple. In production these should move to Oracle
or Terragni's CRM.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .confidentiality import redact_confidential_text

LEADS_DIR = Path(__file__).resolve().parents[1] / "data" / "leads"
LEADS_FILE = LEADS_DIR / "leads.jsonl"
VISITS_FILE = LEADS_DIR / "visits.jsonl"

_WRITE_LOCK = threading.Lock()

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
    """Store a contact-form submission and return the saved record."""
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

    _append(LEADS_FILE, record)
    return record


def log_visit(
    *,
    industry: str,
    role: str,
    path: str,
    outcome: str,
    text: str,
) -> None:
    """Record one question. Never raises: logging must not break the page."""
    try:
        _append(
            VISITS_FILE,
            {
                "at": _now(),
                "industry": _text(industry, 120),
                "role": _text(role, 160),
                "path": path,
                "outcome": outcome,
                "text": _text(redact_confidential_text(text), 600),
            },
        )
    except Exception:
        pass
