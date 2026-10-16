"""
Confidentiality helpers for the Terragni public-facing AI experience.

This module is dependency-free and provides:
1. Lightweight redaction of obvious identifiers.
2. A final safety pass for public-facing text.
3. Neutral public labels for internal source filenames.

This is not a complete PII/name detector. Users should still be instructed
not to enter client names or other confidential information.
"""

from __future__ import annotations

import re


EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

URL_RE = re.compile(
    r"\b(?:https?://|www\.)[^\s<>\"]+",
    re.IGNORECASE,
)

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
)

ACCOUNT_RE = re.compile(
    r"\b(?:"
    r"account|acct|customer\s*id|customer\s*number|"
    r"account\s*number|policy\s*number|application\s*id|"
    r"application\s*number|ticket\s*id|reference\s*number"
    r")(?:\s*(?:no\.?|number))?\s*[:#-]?\s*"
    # The identifier must contain a digit, so "account opening" or
    # "savings-account journey" are left alone.
    r"(?=[A-Z0-9._/-]*\d)[A-Z0-9][A-Z0-9._/-]{2,}\b",
    re.IGNORECASE,
)

LABELED_IDENTITY_RE = re.compile(
    r"\b("
    r"client|customer|company|organisation|organization|"
    r"brand|account|project|client\s*name|company\s*name|"
    r"organisation\s*name|organization\s*name"
    # A label is "client: X", "client = X" or "client - X". A hyphen joined
    # to the word ("customer-centric") is not a label.
    r")\s*(?:name)?(?:\s*[:=]|\s+[-–]\s)\s*"
    r"([^.;,\n]+)",
    re.IGNORECASE,
)


def redact_confidential_text(text: str) -> str:
    """
    Replace obvious identifiers before retrieval.

    This protects emails, URLs, phone numbers, account/reference identifiers,
    and explicitly labelled client/company/brand/project names.
    """
    value = str(text or "").strip()

    if not value:
        return ""

    value = LABELED_IDENTITY_RE.sub(
        lambda match: f"{match.group(1)}: [redacted]",
        value,
    )

    value = ACCOUNT_RE.sub(
        "[redacted account/reference]",
        value,
    )

    value = EMAIL_RE.sub(
        "[redacted email]",
        value,
    )

    value = URL_RE.sub(
        "[redacted URL]",
        value,
    )

    value = PHONE_RE.sub(
        "[redacted phone]",
        value,
    )

    return value.strip()


# Terragni's own published contact details (from the Contact page and the
# company profile). These are allowed on public pages.
TERRAGNI_PUBLIC_DETAILS = (
    "https://terragni.in/newsletter-the-shift/",
    "engage@terragni.co",
    "info@terragni.in",
    "+91 895 698 2522",
    "terragni.in",
)


def sanitize_public_text(text: str) -> str:
    """
    Final safety pass for text that will be sent to the browser.

    This removes obvious identifiers. It does not attempt to identify every
    possible person's or company's name because a dependency-free regex
    cannot reliably determine that.
    """
    value = str(text or "").strip()

    if not value:
        return ""

    # LLMs often emit non-breaking or soft hyphens and narrow spaces, which
    # some browsers and fonts drop. Normalise them to plain characters.
    value = (
        value.replace("‑", "-")
        .replace("‐", "-")
        .replace("­", "")
        .replace(" ", " ")
        .replace(" ", " ")
    )

    # Terragni's own public contact details must stay visible. Swap them for
    # placeholders, redact everything else, then put them back.
    kept = {}
    for index, public in enumerate(TERRAGNI_PUBLIC_DETAILS):
        if public in value:
            token = f"⁣{index}⁣"
            kept[token] = public
            value = value.replace(public, token)

    value = EMAIL_RE.sub("[redacted email]", value)
    value = URL_RE.sub("[redacted URL]", value)
    value = PHONE_RE.sub("[redacted phone]", value)
    value = ACCOUNT_RE.sub("[redacted account/reference]", value)

    value = LABELED_IDENTITY_RE.sub(
        lambda match: f"{match.group(1)}: [redacted]",
        value,
    )

    for token, public in kept.items():
        value = value.replace(token, public)

    return value.strip()


def sanitize_public_list(items) -> list[str]:
    """Sanitize customer-facing list items."""
    if not isinstance(items, list):
        return []

    cleaned = []

    for item in items:
        value = sanitize_public_text(item)

        if value:
            cleaned.append(value)

    return cleaned


def sanitize_public_page(page: dict) -> dict:
    """
    Sanitize customer-facing AI output while preserving controlled backend
    fields such as offering IDs and case-study IDs.
    """
    if not isinstance(page, dict):
        return {}

    result = dict(page)

    text_fields = (
        "title",
        "problem_summary",
        "diagnosis",
        "solution_title",
        "solution",
        "why_this_fits",
        "recommended_next_step",
    )

    for field in text_fields:
        result[field] = sanitize_public_text(
            result.get(field, "")
        )

    result["how_it_works"] = sanitize_public_list(
        result.get("how_it_works", [])
    )

    result["frameworks"] = sanitize_public_list(
        result.get("frameworks", [])
    )

    result["expected_outcomes"] = sanitize_public_list(
        result.get("expected_outcomes", [])
    )

    return result


def public_source_label(source: str) -> str:
    """
    Replace internal filenames with a neutral public-facing label.

    Raw filenames are not safe to display because they may contain client
    or project information.
    """
    value = str(source or "").strip()

    if not value:
        return "Terragni source material"

    lower = value.lower()

    if lower.endswith((".ppt", ".pptx")):
        return "Terragni presentation"

    if lower.endswith((".pdf", ".doc", ".docx", ".txt")):
        return "Terragni document"

    if lower.endswith(".md"):
        return "Terragni case study"

    return "Terragni source material"


def sanitize_public_evidence(items) -> list[dict]:
    """
    Prepare evidence metadata for the public page.

    Internal case-study IDs and raw source filenames are not exposed.
    """
    if not isinstance(items, list):
        return []

    safe = []

    for item in items:
        if not isinstance(item, dict):
            continue

        safe.append({
            "case_study_id": "",
            "source": public_source_label(
                item.get("source", "")
            ),
            "locator": sanitize_public_text(
                item.get("locator", "")
            ),
            "claim": sanitize_public_text(
                item.get("claim", "")
            ),
        })

    return safe



# ============================================================
# CLIENT-NAME PROTECTION
# ============================================================
# Internal case-study titles in Oracle often contain the client's name
# (for example a bank programme name). Those titles must never reach the
# public page. Names come from two places: this static list of known
# client and programme names, and CASE_STUDY.CLIENT_NAME (registered at
# startup through register_client_names()).

_KNOWN_CLIENT_NAMES = {
    "ABHI",
    "Aditya Birla",
    "Allianz",
    "Axis",
    "Bajaj",
    "Bajaj Allianz",
    "Burgundy",
    "Celesta",
    "Federal Bank",
    "IIFL",
    "Kotak",
    "Privy League",
}

_CLIENT_NAME_RE: re.Pattern | None = None


def _rebuild_client_name_pattern() -> None:
    global _CLIENT_NAME_RE

    names = sorted(
        {name.strip() for name in _KNOWN_CLIENT_NAMES if name and len(name.strip()) >= 3},
        key=len,
        reverse=True,
    )

    _CLIENT_NAME_RE = (
        re.compile(
            r"\b(" + "|".join(re.escape(name) for name in names) + r")\b",
            re.IGNORECASE,
        )
        if names
        else None
    )


_rebuild_client_name_pattern()


def register_client_names(names) -> None:
    """Add client names (e.g. CASE_STUDY.CLIENT_NAME values) to the blocklist."""
    for name in names or []:
        value = str(name or "").strip()
        if len(value) >= 3:
            _KNOWN_CLIENT_NAMES.add(value)

    _rebuild_client_name_pattern()


def contains_client_name(text: str) -> bool:
    return bool(_CLIENT_NAME_RE and _CLIENT_NAME_RE.search(str(text or "")))


def remove_client_names(text: str) -> str:
    """Replace any known client name inside free text with a neutral word."""
    value = str(text or "")

    if not _CLIENT_NAME_RE:
        return value

    return _CLIENT_NAME_RE.sub("a client", value)


_BRAND_PREFIX_RE = re.compile(
    r"^\s*(?:JUMP[_\s]*)?Behaviou?rs?\s+(?:for|For)\s+Business\s*[-–:_]*\s*",
)


def public_case_title(title: str, industry_hint: str = "") -> str:
    """
    Turn an internal case-study title into a safe public title.

    Titles that contain a client name are replaced by a neutral label.
    Marketing prefixes such as "Behaviours for Business -" are trimmed.
    """
    value = str(title or "").strip()

    if not value:
        return ""

    if contains_client_name(value):
        hint = str(industry_hint or "").lower()
        if "insur" in hint:
            return "A Terragni life insurance case study"
        return "A Terragni banking case study"

    trimmed = _BRAND_PREFIX_RE.sub("", value).strip(" -–_")
    return sanitize_public_text(trimmed or value)
