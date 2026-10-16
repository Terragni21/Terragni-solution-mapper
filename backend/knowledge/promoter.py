from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any, Optional

from database.connection import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

ENTITY_TYPES = {
    "CASE_STUDY",
    "INDUSTRY",
    "OFFERING",
    "FRAMEWORK",
    "CHALLENGE",
    "OUTCOME",
}

ENTITY_CONFIG = {
    "INDUSTRY": {
        "table": "INDUSTRY",
        "id_column": "INDUSTRY_ID",
        "name_column": "INDUSTRY_NAME",
        "code_column": "INDUSTRY_CODE",
    },
    "OFFERING": {
        "table": "OFFERING",
        "id_column": "OFFERING_ID",
        "name_column": "OFFERING_NAME",
        "code_column": "OFFERING_CODE",
    },
    "FRAMEWORK": {
        "table": "FRAMEWORK",
        "id_column": "FRAMEWORK_ID",
        "name_column": "FRAMEWORK_NAME",
        "code_column": "FRAMEWORK_CODE",
    },
    "CHALLENGE": {
        "table": "CHALLENGE",
        "id_column": "CHALLENGE_ID",
        "name_column": "CHALLENGE_NAME",
        "code_column": "CHALLENGE_CODE",
    },
    "OUTCOME": {
        "table": "OUTCOME",
        "id_column": "OUTCOME_ID",
        "name_column": "OUTCOME_NAME",
        "code_column": "OUTCOME_CODE",
    },
}

DEFAULT_STATUS = "ACTIVE"
DEFAULT_RELATIONSHIP_TYPE = "SUPPORTING"
DEFAULT_EVIDENCE_TYPE = "SUPPORTING"

RELATIONSHIP_CONFIG = {
    "INDUSTRY": {
        "table": "CASE_STUDY_INDUSTRY",
        "entity_id_column": "INDUSTRY_ID",
    },
    "OFFERING": {
        "table": "CASE_STUDY_OFFERING",
        "entity_id_column": "OFFERING_ID",
    },
    "FRAMEWORK": {
        "table": "CASE_STUDY_FRAMEWORK",
        "entity_id_column": "FRAMEWORK_ID",
    },
    "CHALLENGE": {
        "table": "CASE_STUDY_CHALLENGE",
        "entity_id_column": "CHALLENGE_ID",
    },
    "OUTCOME": {
        "table": "CASE_STUDY_OUTCOME",
        "entity_id_column": "OUTCOME_ID",
    },
}


# ============================================================
# TEXT / NORMALIZATION
# ============================================================

def normalize_name(value: Optional[str]) -> str:
    """
    Deterministic normalization for exact identity/deduplication.

    This is NOT semantic matching and is NOT used for routing.
    """
    if not value:
        return ""

    value = str(value).strip().lower()

    # Normalize common document typography.
    value = value.replace("–", "-").replace("—", "-")
    value = value.replace("‑", "-").replace("’", "'")
    value = value.replace("&", " and ")

    # Safe spelling normalization for common British/American variants.
    # This is orthographic normalization, not semantic matching.
    spelling_map = {
        "utilisation": "utilization",
        "behaviour": "behavior",
        "behaviours": "behaviors",
        "programme": "program",
        "programmes": "programs",
        "optimisation": "optimization",
        "optimise": "optimize",
        "optimised": "optimized",
        "organisation": "organization",
        "organisations": "organizations",
        "personalisation": "personalization",
        "personalise": "personalize",
        "personalised": "personalized",
    }
    for old, new in spelling_map.items():
        value = re.sub(rf"\b{re.escape(old)}\b", new, value)

    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"[^\w\s/-]", "", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def generate_entity_code(entity_name: str) -> str:
    normalized = normalize_name(entity_name)
    code = re.sub(r"[^a-zA-Z0-9]+", "_", normalized)
    code = code.strip("_").upper() or "ENTITY"

    if len(code) <= 90:
        return code

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{code[:81]}_{digest}"


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def required_text(value: Any, field_name: str, context: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        raise ValueError(
            f"{context}: required field {field_name} is empty."
        )
    return cleaned


def safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def case_study_identity_key(data: dict[str, Any]) -> Optional[tuple]:
    """
    Deterministic cross-document case-study identity.

    Priority:
      1. Explicit source code, when present.
      2. Exact combination of objective + approach + key_finding.

    The second key is deliberately strict: all three fields must exist.
    No semantic similarity or phrase routing is used.
    """
    code = clean_text(data.get("code"))
    if code:
        return ("CODE", normalize_name(code))

    objective = clean_text(data.get("objective"))
    approach = clean_text(data.get("approach"))
    key_finding = clean_text(data.get("key_finding"))

    if objective and approach and key_finding:
        return (
            "CONTENT",
            normalize_name(objective),
            normalize_name(approach),
            normalize_name(key_finding),
        )

    return None


# ============================================================
# ORACLE HELPERS
# ============================================================

def fetch_all(
    cursor,
    sql: str,
    params: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    cursor.execute(sql, params or {})
    columns = [d[0].lower() for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_one(
    cursor,
    sql: str,
    params: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    if row is None:
        return None

    columns = [d[0].lower() for d in cursor.description]
    return dict(zip(columns, row))


def execute_returning_id(
    cursor,
    sql: str,
    params: dict[str, Any],
) -> int:
    bind_params = dict(params)
    out_var = cursor.var(int)
    bind_params["out_id"] = out_var

    cursor.execute(sql, bind_params)

    value = out_var.getvalue()
    if isinstance(value, list):
        value = value[0]

    return int(value)


# ============================================================
# STAGING
# ============================================================

def get_pending_rows(
    cursor,
    document_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            STAGING_ID,
            DOCUMENT_ID,
            CHUNK_ID,
            ENTITY_TYPE,
            ENTITY_NAME,
            ENTITY_CODE,
            RELATIONSHIP_TYPE,
            EXTRACTED_TEXT,
            CONFIDENCE_SCORE,
            EXTRACTION_STATUS,
            PARENT_ENTITY_TYPE,
            PARENT_ENTITY_NAME
        FROM KNOWLEDGE_EXTRACTION_STAGING
        WHERE EXTRACTION_STATUS = 'PENDING'
    """

    params: dict[str, Any] = {}

    if document_id is not None:
        sql += " AND DOCUMENT_ID = :document_id"
        params["document_id"] = document_id

    sql += " ORDER BY STAGING_ID"

    return fetch_all(cursor, sql, params)


def get_relationship_rows(
    cursor,
    document_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Reads both PENDING and PROMOTED relationship staging rows.
    Used by the repair command.
    """
    sql = """
        SELECT
            STAGING_ID,
            DOCUMENT_ID,
            CHUNK_ID,
            ENTITY_TYPE,
            ENTITY_NAME,
            ENTITY_CODE,
            RELATIONSHIP_TYPE,
            EXTRACTED_TEXT,
            CONFIDENCE_SCORE,
            EXTRACTION_STATUS,
            PARENT_ENTITY_TYPE,
            PARENT_ENTITY_NAME
        FROM KNOWLEDGE_EXTRACTION_STAGING
        WHERE PARENT_ENTITY_TYPE = 'CASE_STUDY'
          AND PARENT_ENTITY_NAME IS NOT NULL
    """

    params: dict[str, Any] = {}

    if document_id is not None:
        sql += " AND DOCUMENT_ID = :document_id"
        params["document_id"] = document_id

    sql += " ORDER BY STAGING_ID"

    return fetch_all(cursor, sql, params)


def mark_promoted(cursor, staging_ids: list[int]) -> None:
    for staging_id in staging_ids:
        cursor.execute(
            """
            UPDATE KNOWLEDGE_EXTRACTION_STAGING
            SET
                EXTRACTION_STATUS = 'PROMOTED',
                UPDATED_AT = SYSTIMESTAMP
            WHERE STAGING_ID = :staging_id
            """,
            {"staging_id": staging_id},
        )


# ============================================================
# MASTER ENTITY LOOKUP / PROMOTION
# ============================================================

def find_master_entity(
    cursor,
    entity_type: str,
    entity_name: str,
) -> Optional[dict[str, Any]]:
    config = ENTITY_CONFIG[entity_type]

    rows = fetch_all(
        cursor,
        f"""
        SELECT
            {config["id_column"]},
            {config["name_column"]},
            {config["code_column"]}
        FROM {config["table"]}
        """,
    )

    target = normalize_name(entity_name)
    name_key = config["name_column"].lower()

    for row in rows:
        if normalize_name(row[name_key]) == target:
            return row

    return None


def promote_master_entity(
    cursor,
    row: dict[str, Any],
) -> int:
    entity_type = row["entity_type"]

    if entity_type not in ENTITY_CONFIG:
        raise ValueError(f"Unsupported ENTITY_TYPE: {entity_type}")

    config = ENTITY_CONFIG[entity_type]
    context = f"{entity_type} staging row {row['staging_id']}"

    entity_name = required_text(
        row.get("entity_name"),
        "ENTITY_NAME",
        context,
    )

    data = parse_json(row.get("extracted_text"))

    description = clean_text(
        data.get("description")
        or data.get("summary")
        or data.get("challenge")
        or data.get("outcome")
    )

    code = clean_text(row.get("entity_code")) or clean_text(data.get("code"))
    if not code:
        code = generate_entity_code(entity_name)

    status = clean_text(data.get("status")) or DEFAULT_STATUS

    existing = find_master_entity(
        cursor,
        entity_type,
        entity_name,
    )

    # Exact code fallback prevents UQ_*_CODE collisions when two source
    # documents use different names/spellings for the same master entity.
    if existing is None:
        code_rows = fetch_all(
            cursor,
            f"""
                SELECT
                    {config["id_column"]},
                    {config["name_column"]},
                    {config["code_column"]}
                FROM {config["table"]}
                WHERE {config["code_column"]} = :entity_code
            """,
            {"entity_code": code},
        )
        if code_rows:
            existing = code_rows[0]

    if existing:
        entity_id = int(
            existing[config["id_column"].lower()]
        )

        cursor.execute(
            f"""
            UPDATE {config["table"]}
            SET
                {config["code_column"]} =
                    COALESCE(
                        {config["code_column"]},
                        :entity_code
                    ),
                DESCRIPTION =
                    COALESCE(
                        DESCRIPTION,
                        TO_CLOB(:description)
                    ),
                STATUS =
                    COALESCE(
                        STATUS,
                        :status
                    ),
                UPDATED_AT = SYSTIMESTAMP
            WHERE {config["id_column"]} = :entity_id
            """,
            {
                "entity_code": code,
                "description": description,
                "status": status,
                "entity_id": entity_id,
            },
        )

        return entity_id

    sql = f"""
        INSERT INTO {config["table"]}
        (
            {config["name_column"]},
            {config["code_column"]},
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        )
        VALUES
        (
            :entity_name,
            :entity_code,
            :description,
            :status,
            SYSTIMESTAMP,
            SYSTIMESTAMP
        )
        RETURNING {config["id_column"]}
        INTO :out_id
    """

    return execute_returning_id(
        cursor,
        sql,
        {
            "entity_name": entity_name,
            "entity_code": code,
            "description": description,
            "status": status,
        },
    )


# ============================================================
# CASE STUDY LOOKUP
# ============================================================

def find_case_study_by_title(
    cursor,
    title: str,
) -> Optional[dict[str, Any]]:
    rows = fetch_all(
        cursor,
        """
        SELECT
            CASE_STUDY_ID,
            CASE_STUDY_CODE,
            TITLE,
            STATUS,
            CLIENT_NAME,
            OBJECTIVE,
            APPROACH,
            KEY_FINDING
        FROM CASE_STUDY
        """,
    )

    target = normalize_name(title)

    for row in rows:
        if normalize_name(row["title"]) == target:
            return row

    return None


def find_case_study_by_identity(
    cursor,
    identity_key: Optional[tuple],
) -> Optional[dict[str, Any]]:
    """
    Deterministic cross-document lookup.

    Only exact CONTENT identity keys are compared. This avoids semantic
    matching while allowing source documents whose titles differ slightly
    but whose complete objective/approach/key-finding identity is identical.
    """
    if not identity_key:
        return None

    rows = fetch_all(
        cursor,
        """
        SELECT
            CASE_STUDY_ID,
            CASE_STUDY_CODE,
            TITLE,
            STATUS,
            CLIENT_NAME,
            OBJECTIVE,
            APPROACH,
            KEY_FINDING
        FROM CASE_STUDY
        """,
    )

    for row in rows:
        if identity_key[0] == "CODE":
            # Code identity is only meaningful if the source provided a code.
            continue

        existing_objective = clean_text(row.get("objective"))
        existing_approach = clean_text(row.get("approach"))
        existing_key_finding = clean_text(row.get("key_finding"))

        if not (
            existing_objective
            and existing_approach
            and existing_key_finding
        ):
            continue

        existing_key = (
            "CONTENT",
            normalize_name(existing_objective),
            normalize_name(existing_approach),
            normalize_name(existing_key_finding),
        )

        if existing_key == identity_key:
            return row

    return None


def find_case_study(
    cursor,
    title: str,
    identity_key: Optional[tuple] = None,
) -> Optional[dict[str, Any]]:
    """
    Exact title first, then strict deterministic content identity.
    """
    existing = find_case_study_by_title(cursor, title)
    if existing:
        return existing

    return find_case_study_by_identity(
        cursor,
        identity_key,
    )


# ============================================================
# CASE STUDY PROMOTION
# ============================================================

def promote_case_study(
    cursor,
    row: dict[str, Any],
) -> int:
    data = parse_json(row.get("extracted_text"))
    context = f"CASE_STUDY staging row {row['staging_id']}"

    title = required_text(
        data.get("name") or row.get("entity_name"),
        "TITLE",
        context,
    )

    case_study_code = clean_text(
        data.get("code") or row.get("entity_code")
    )

    if not case_study_code:
        case_study_code = generate_entity_code(title)

    status = clean_text(data.get("status")) or DEFAULT_STATUS

    fields = {
        "case_study_code": case_study_code,
        "title": title,
        "client_name": clean_text(data.get("client_name")),
        "public_title": clean_text(data.get("public_title")),
        "summary": clean_text(data.get("summary")),
        "challenge": clean_text(data.get("challenge")),
        "objective": clean_text(data.get("objective")),
        "approach": clean_text(data.get("approach")),
        "key_finding": clean_text(data.get("key_finding")),
        "solution": clean_text(data.get("solution")),
        "business_outcome": clean_text(data.get("business_outcome")),
        "status": status,
    }

    identity_key = case_study_identity_key(data)

    existing = find_case_study(
        cursor,
        title,
        identity_key,
    )

    if existing:
        case_study_id = int(existing["case_study_id"])

        # Do not overwrite canonical source values with weaker duplicates.
        cursor.execute(
            """
            UPDATE CASE_STUDY
            SET
                CASE_STUDY_CODE =
                    COALESCE(
                        CASE_STUDY_CODE,
                        :case_study_code
                    ),
                TITLE =
                    COALESCE(
                        TITLE,
                        :title
                    ),
                CLIENT_NAME =
                    COALESCE(
                        CLIENT_NAME,
                        :client_name
                    ),
                PUBLIC_TITLE =
                    COALESCE(
                        PUBLIC_TITLE,
                        :public_title
                    ),
                SUMMARY =
                    COALESCE(
                        SUMMARY,
                        TO_CLOB(:summary)
                    ),
                CHALLENGE =
                    COALESCE(
                        CHALLENGE,
                        TO_CLOB(:challenge)
                    ),
                OBJECTIVE =
                    COALESCE(
                        OBJECTIVE,
                        TO_CLOB(:objective)
                    ),
                APPROACH =
                    COALESCE(
                        APPROACH,
                        TO_CLOB(:approach)
                    ),
                KEY_FINDING =
                    COALESCE(
                        KEY_FINDING,
                        TO_CLOB(:key_finding)
                    ),
                SOLUTION =
                    COALESCE(
                        SOLUTION,
                        TO_CLOB(:solution)
                    ),
                BUSINESS_OUTCOME =
                    COALESCE(
                        BUSINESS_OUTCOME,
                        TO_CLOB(:business_outcome)
                    ),
                STATUS =
                    COALESCE(
                        STATUS,
                        :status
                    ),
                UPDATED_AT = SYSTIMESTAMP
            WHERE CASE_STUDY_ID = :case_study_id
            """,
            {
                **fields,
                "case_study_id": case_study_id,
            },
        )

        return case_study_id

    return execute_returning_id(
        cursor,
        """
        INSERT INTO CASE_STUDY
        (
            CASE_STUDY_CODE,
            TITLE,
            CLIENT_NAME,
            PUBLIC_TITLE,
            SUMMARY,
            CHALLENGE,
            OBJECTIVE,
            APPROACH,
            KEY_FINDING,
            SOLUTION,
            BUSINESS_OUTCOME,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        )
        VALUES
        (
            :case_study_code,
            :title,
            :client_name,
            :public_title,
            :summary,
            :challenge,
            :objective,
            :approach,
            :key_finding,
            :solution,
            :business_outcome,
            :status,
            SYSTIMESTAMP,
            SYSTIMESTAMP
        )
        RETURNING CASE_STUDY_ID
        INTO :out_id
        """,
        fields,
    )


# ============================================================
# CASE STUDY EVIDENCE
# ============================================================

def evidence_exists(
    cursor,
    case_study_id: int,
    chunk_id: int,
) -> bool:
    row = fetch_one(
        cursor,
        """
        SELECT 1 AS EXISTS_FLAG
        FROM CASE_STUDY_EVIDENCE
        WHERE CASE_STUDY_ID = :case_study_id
          AND CHUNK_ID = :chunk_id
          AND ROWNUM = 1
        """,
        {
            "case_study_id": case_study_id,
            "chunk_id": chunk_id,
        },
    )
    return row is not None


def create_case_study_evidence(
    cursor,
    case_study_id: int,
    row: dict[str, Any],
) -> bool:
    chunk_id = safe_int(row.get("chunk_id"))

    if not chunk_id:
        return False

    if evidence_exists(cursor, case_study_id, chunk_id):
        return False

    data = parse_json(row.get("extracted_text"))

    notes: list[str] = []
    evidence = data.get("evidence")

    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue

            evidence_text = clean_text(
                item.get("evidence_text")
            )

            if evidence_text:
                notes.append(evidence_text)

    relevance_note = " ".join(notes) if notes else None

    evidence_type = (
        clean_text(row.get("relationship_type"))
        or DEFAULT_EVIDENCE_TYPE
    )

    cursor.execute(
        """
        INSERT INTO CASE_STUDY_EVIDENCE
        (
            CASE_STUDY_ID,
            CHUNK_ID,
            EVIDENCE_TYPE,
            RELEVANCE_NOTE,
            CREATED_AT
        )
        VALUES
        (
            :case_study_id,
            :chunk_id,
            :evidence_type,
            :relevance_note,
            SYSTIMESTAMP
        )
        """,
        {
            "case_study_id": case_study_id,
            "chunk_id": chunk_id,
            "evidence_type": evidence_type,
            "relevance_note": relevance_note,
        },
    )

    return True


# ============================================================
# RELATIONSHIPS
# ============================================================

def find_relation(
    cursor,
    table: str,
    case_study_id: int,
    entity_id_column: str,
    entity_id: int,
) -> Optional[dict[str, Any]]:
    return fetch_one(
        cursor,
        f"""
        SELECT RELATIONSHIP_TYPE
        FROM {table}
        WHERE CASE_STUDY_ID = :case_study_id
          AND {entity_id_column} = :entity_id
          AND ROWNUM = 1
        """,
        {
            "case_study_id": case_study_id,
            "entity_id": entity_id,
        },
    )


def create_relation(
    cursor,
    table: str,
    entity_id_column: str,
    case_study_id: int,
    entity_id: int,
    relationship_type: str = DEFAULT_RELATIONSHIP_TYPE,
) -> bool:
    """
    Returns True when a row is inserted OR an existing relationship is
    normalized to the source-supported relationship type.
    """
    relationship_type = (
        clean_text(relationship_type)
        or DEFAULT_RELATIONSHIP_TYPE
    )

    existing = find_relation(
        cursor,
        table,
        case_study_id,
        entity_id_column,
        entity_id,
    )

    if existing:
        existing_type = clean_text(
            existing.get("relationship_type")
        )

        if existing_type != relationship_type:
            cursor.execute(
                f"""
                UPDATE {table}
                SET RELATIONSHIP_TYPE = :relationship_type
                WHERE CASE_STUDY_ID = :case_study_id
                  AND {entity_id_column} = :entity_id
                """,
                {
                    "relationship_type": relationship_type,
                    "case_study_id": case_study_id,
                    "entity_id": entity_id,
                },
            )
            return True

        return False

    cursor.execute(
        f"""
        INSERT INTO {table}
        (
            CASE_STUDY_ID,
            {entity_id_column},
            RELATIONSHIP_TYPE,
            CREATED_AT
        )
        VALUES
        (
            :case_study_id,
            :entity_id,
            :relationship_type,
            SYSTIMESTAMP
        )
        """,
        {
            "case_study_id": case_study_id,
            "entity_id": entity_id,
            "relationship_type": relationship_type,
        },
    )

    return True


def find_entity_by_exact_name(
    cursor,
    entity_type: str,
    name: str,
) -> Optional[int]:
    entity = find_master_entity(
        cursor,
        entity_type,
        name,
    )

    if not entity:
        return None

    config = ENTITY_CONFIG[entity_type]

    return int(
        entity[config["id_column"].lower()]
    )


def promote_staging_relationships(
    cursor,
    rows: list[dict[str, Any]],
    case_study_cache: dict[str, int],
) -> int:
    """
    Promote ONLY explicit parent-child relationships from staging.

    Parent case-study aliases are first resolved from the current document's
    case-study cache. This is important when two source documents use slightly
    different titles for the same deterministic case-study identity.
    """
    relationship_count = 0

    for row in rows:
        child_type = clean_text(row.get("entity_type"))
        parent_type = clean_text(row.get("parent_entity_type"))
        parent_name = clean_text(row.get("parent_entity_name"))
        child_name = clean_text(row.get("entity_name"))

        if not child_type or child_type == "CASE_STUDY":
            continue

        if parent_type != "CASE_STUDY" or not parent_name:
            continue

        relationship_config = RELATIONSHIP_CONFIG.get(child_type)
        if relationship_config is None:
            continue

        parent_key = normalize_name(parent_name)
        case_study_id = case_study_cache.get(parent_key)

        if case_study_id is None:
            existing_case = find_case_study_by_title(
                cursor,
                parent_name,
            )

            if existing_case:
                case_study_id = int(
                    existing_case["case_study_id"]
                )
                case_study_cache[parent_key] = case_study_id

        if case_study_id is None:
            raise ValueError(
                f"Staging relationship row {row['staging_id']} "
                f"references CASE_STUDY '{parent_name}', but that "
                f"case study was not found."
            )

        if not child_name:
            raise ValueError(
                f"Staging relationship row {row['staging_id']} "
                f"has no child ENTITY_NAME."
            )

        child_id = find_entity_by_exact_name(
            cursor,
            child_type,
            child_name,
        )

        if child_id is None:
            raise ValueError(
                f"Staging relationship row {row['staging_id']} "
                f"references {child_type} '{child_name}', but the "
                f"master entity was not found."
            )

        changed = create_relation(
            cursor,
            relationship_config["table"],
            relationship_config["entity_id_column"],
            case_study_id,
            child_id,
            clean_text(row.get("relationship_type"))
            or DEFAULT_RELATIONSHIP_TYPE,
        )

        if changed:
            relationship_count += 1

    return relationship_count


# ============================================================
# REPAIR RELATIONSHIPS
# ============================================================

def repair_relationships(
    document_id: Optional[int] = None,
) -> dict[str, int]:
    """
    Rebuild explicit relationships from PENDING or PROMOTED staging rows.
    """
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        rows = get_relationship_rows(
            cursor,
            document_id=document_id,
        )

        if not rows:
            connection.commit()
            return {
                "relationship_rows": 0,
                "relationship_links": 0,
            }

        case_study_cache: dict[str, int] = {}

        # First, map every explicit parent title to an existing case study.
        for row in rows:
            parent_name = clean_text(
                row.get("parent_entity_name")
            )
            if not parent_name:
                continue

            parent_key = normalize_name(parent_name)

            if parent_key in case_study_cache:
                continue

            existing_case = find_case_study_by_title(
                cursor,
                parent_name,
            )

            if existing_case:
                case_study_cache[parent_key] = int(
                    existing_case["case_study_id"]
                )

        relationship_count = promote_staging_relationships(
            cursor,
            rows,
            case_study_cache,
        )

        connection.commit()

        return {
            "relationship_rows": len(rows),
            "relationship_links": relationship_count,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        connection.close()


# ============================================================
# MAIN PROMOTION
# ============================================================

def promote(
    document_id: Optional[int] = None,
) -> dict[str, int]:
    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        rows = get_pending_rows(
            cursor,
            document_id=document_id,
        )

        if not rows:
            connection.commit()
            return {
                "staging_rows": 0,
                "promoted_rows": 0,
                "case_studies": 0,
                "master_entities": 0,
                "evidence_links": 0,
                "relationship_links": 0,
            }

        # Validate before making changes.
        for row in rows:
            entity_type = row["entity_type"]

            if entity_type not in ENTITY_TYPES:
                raise ValueError(
                    f"Unsupported ENTITY_TYPE: {entity_type}"
                )

            if not clean_text(row.get("entity_name")):
                raise ValueError(
                    f"Staging row {row['staging_id']} "
                    f"has no ENTITY_NAME."
                )

        # ----------------------------------------------------
        # PASS 1: master entities
        # ----------------------------------------------------

        master_entity_count = 0

        for row in rows:
            if row["entity_type"] == "CASE_STUDY":
                continue

            promote_master_entity(cursor, row)
            master_entity_count += 1

        # ----------------------------------------------------
        # PASS 2: case studies + evidence
        # ----------------------------------------------------

        case_study_cache: dict[str, int] = {}
        case_study_identity_cache: dict[tuple, int] = {}

        case_study_count = 0
        evidence_count = 0

        for row in rows:
            if row["entity_type"] != "CASE_STUDY":
                continue

            data = parse_json(row.get("extracted_text"))

            title = required_text(
                data.get("name") or row.get("entity_name"),
                "TITLE",
                f"CASE_STUDY staging row {row['staging_id']}",
            )

            normalized_title = normalize_name(title)
            identity_key = case_study_identity_key(data)

            if normalized_title in case_study_cache:
                case_study_id = case_study_cache[normalized_title]

            elif identity_key and identity_key in case_study_identity_cache:
                case_study_id = case_study_identity_cache[identity_key]

            else:
                case_study_id = promote_case_study(
                    cursor,
                    row,
                )

                case_study_count += 1

                if identity_key:
                    case_study_identity_cache[
                        identity_key
                    ] = case_study_id

            # IMPORTANT:
            # Cache the source title even when it differs from the canonical
            # production title. This lets relationship rows such as
            # "Leading Financial Institution Goes Experiential" resolve to
            # the already-existing canonical case study.
            case_study_cache[normalized_title] = case_study_id

            created = create_case_study_evidence(
                cursor,
                case_study_id,
                row,
            )

            if created:
                evidence_count += 1

        # ----------------------------------------------------
        # PASS 3: explicit relationships
        # ----------------------------------------------------

        relationship_count = promote_staging_relationships(
            cursor,
            rows,
            case_study_cache,
        )

        # ----------------------------------------------------
        # PASS 4: mark staging rows promoted
        # ----------------------------------------------------

        staging_ids = [
            int(row["staging_id"])
            for row in rows
        ]

        mark_promoted(
            cursor,
            staging_ids,
        )

        connection.commit()

        return {
            "staging_rows": len(rows),
            "promoted_rows": len(staging_ids),
            "case_studies": case_study_count,
            "master_entities": master_entity_count,
            "evidence_links": evidence_count,
            "relationship_links": relationship_count,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        connection.close()


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Promote extracted Terragni knowledge from "
            "KNOWLEDGE_EXTRACTION_STAGING into Oracle."
        )
    )

    parser.add_argument(
        "--document-id",
        type=int,
        default=None,
        help=(
            "Promote only PENDING extraction rows belonging "
            "to this document."
        ),
    )

    parser.add_argument(
        "--repair-relationships",
        action="store_true",
        help=(
            "Repair explicit case-study relationships from "
            "PENDING or PROMOTED staging rows."
        ),
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Terragni Knowledge Promoter")
    print("=" * 70)

    if args.document_id is not None:
        print(f"Document ID : {args.document_id}")
    else:
        print("Scope       : ALL PENDING")

    print()

    if args.repair_relationships:
        result = repair_relationships(
            document_id=args.document_id
        )

        print("Relationship repair complete.")
        print()
        print(
            f"Relationship rows : "
            f"{result['relationship_rows']}"
        )
        print(
            f"Relationship links: "
            f"{result['relationship_links']}"
        )

    else:
        result = promote(
            document_id=args.document_id
        )

        print("Promotion complete.")
        print()
        print(
            f"Staging rows     : "
            f"{result['staging_rows']}"
        )
        print(
            f"Promoted rows    : "
            f"{result['promoted_rows']}"
        )
        print(
            f"Case studies     : "
            f"{result['case_studies']}"
        )
        print(
            f"Master entities  : "
            f"{result['master_entities']}"
        )
        print(
            f"Evidence links   : "
            f"{result['evidence_links']}"
        )
        print(
            f"Relationship links: "
            f"{result['relationship_links']}"
        )

    print("=" * 70)


if __name__ == "__main__":
    main()
