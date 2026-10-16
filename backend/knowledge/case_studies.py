from __future__ import annotations

from typing import Any, Optional

from .db import fetch_all, fetch_one, execute, execute_returning_id


# ============================================================
# CASE STUDY
# ============================================================

def get_case_studies() -> list[dict[str, Any]]:
    """Return all case studies stored in Oracle."""
    return fetch_all(
        """
        SELECT
            CASE_STUDY_ID,
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
        FROM CASE_STUDY
        ORDER BY TITLE
        """
    )


def get_case_study(
    case_study_id: int,
) -> Optional[dict[str, Any]]:
    """Return one case study by ID."""
    return fetch_one(
        """
        SELECT
            CASE_STUDY_ID,
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
        FROM CASE_STUDY
        WHERE CASE_STUDY_ID = :case_study_id
        """,
        {
            "case_study_id": case_study_id,
        },
    )


def get_case_study_by_code(
    case_study_code: str,
) -> Optional[dict[str, Any]]:
    """Return one case study by business code."""
    return fetch_one(
        """
        SELECT
            CASE_STUDY_ID,
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
        FROM CASE_STUDY
        WHERE UPPER(CASE_STUDY_CODE) = UPPER(:case_study_code)
        """,
        {
            "case_study_code": case_study_code,
        },
    )


def create_case_study(
    case_study_code: str,
    title: str,
    client_name: Optional[str] = None,
    public_title: Optional[str] = None,
    summary: Optional[str] = None,
    challenge: Optional[str] = None,
    objective: Optional[str] = None,
    approach: Optional[str] = None,
    key_finding: Optional[str] = None,
    solution: Optional[str] = None,
    business_outcome: Optional[str] = None,
    status: str = "ACTIVE",
) -> int:
    """
    Create a case study and return CASE_STUDY_ID.

    If the case-study code already exists, the existing
    ID is returned instead of creating a duplicate.
    """
    existing = get_case_study_by_code(case_study_code)

    if existing:
        return int(existing["case_study_id"])

    return execute_returning_id(
        """
        INSERT INTO CASE_STUDY (
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
        VALUES (
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
        RETURNING CASE_STUDY_ID INTO :out_id
        """,
        {
            "case_study_code": case_study_code,
            "title": title,
            "client_name": client_name,
            "public_title": public_title,
            "summary": summary,
            "challenge": challenge,
            "objective": objective,
            "approach": approach,
            "key_finding": key_finding,
            "solution": solution,
            "business_outcome": business_outcome,
            "status": status,
        },
        id_column="CASE_STUDY_ID",
    )


# ============================================================
# CASE STUDY → CHALLENGE
# ============================================================

def link_challenge(
    case_study_id: int,
    challenge_id: int,
    relationship_type: str = "PRIMARY",
) -> int:
    """Link a case study to a challenge."""
    return execute(
        """
        INSERT INTO CASE_STUDY_CHALLENGE (
            CASE_STUDY_ID,
            CHALLENGE_ID,
            RELATIONSHIP_TYPE,
            CREATED_AT
        )
        SELECT
            :case_study_id,
            :challenge_id,
            :relationship_type,
            SYSTIMESTAMP
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1
            FROM CASE_STUDY_CHALLENGE
            WHERE CASE_STUDY_ID = :case_study_id
              AND CHALLENGE_ID = :challenge_id
        )
        """,
        {
            "case_study_id": case_study_id,
            "challenge_id": challenge_id,
            "relationship_type": relationship_type,
        },
    )


def get_case_study_challenges(
    case_study_id: int,
) -> list[dict[str, Any]]:
    """Return challenges linked to a case study."""
    return fetch_all(
        """
        SELECT
            csc.CASE_STUDY_ID,
            csc.CHALLENGE_ID,
            csc.RELATIONSHIP_TYPE,
            c.CHALLENGE_CODE,
            c.CHALLENGE_NAME,
            c.DESCRIPTION
        FROM CASE_STUDY_CHALLENGE csc
        JOIN CHALLENGE c
          ON c.CHALLENGE_ID = csc.CHALLENGE_ID
        WHERE csc.CASE_STUDY_ID = :case_study_id
        ORDER BY c.CHALLENGE_NAME
        """,
        {
            "case_study_id": case_study_id,
        },
    )


# ============================================================
# CASE STUDY → OFFERING
# ============================================================

def link_offering(
    case_study_id: int,
    offering_id: int,
    relationship_type: str = "PRIMARY",
) -> int:
    """Link a case study to an offering."""
    return execute(
        """
        INSERT INTO CASE_STUDY_OFFERING (
            CASE_STUDY_ID,
            OFFERING_ID,
            RELATIONSHIP_TYPE,
            CREATED_AT
        )
        SELECT
            :case_study_id,
            :offering_id,
            :relationship_type,
            SYSTIMESTAMP
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1
            FROM CASE_STUDY_OFFERING
            WHERE CASE_STUDY_ID = :case_study_id
              AND OFFERING_ID = :offering_id
        )
        """,
        {
            "case_study_id": case_study_id,
            "offering_id": offering_id,
            "relationship_type": relationship_type,
        },
    )


def get_case_study_offerings(
    case_study_id: int,
) -> list[dict[str, Any]]:
    """Return offerings linked to a case study."""
    return fetch_all(
        """
        SELECT
            cso.CASE_STUDY_ID,
            cso.OFFERING_ID,
            cso.RELATIONSHIP_TYPE,
            o.OFFERING_CODE,
            o.OFFERING_NAME,
            o.DESCRIPTION
        FROM CASE_STUDY_OFFERING cso
        JOIN OFFERING o
          ON o.OFFERING_ID = cso.OFFERING_ID
        WHERE cso.CASE_STUDY_ID = :case_study_id
        ORDER BY o.OFFERING_NAME
        """,
        {
            "case_study_id": case_study_id,
        },
    )


# ============================================================
# CASE STUDY → INDUSTRY
# ============================================================

def link_industry(
    case_study_id: int,
    industry_id: int,
    relationship_type: str = "PRIMARY",
) -> int:
    """Link a case study to an industry."""
    return execute(
        """
        INSERT INTO CASE_STUDY_INDUSTRY (
            CASE_STUDY_ID,
            INDUSTRY_ID,
            RELATIONSHIP_TYPE,
            CREATED_AT
        )
        SELECT
            :case_study_id,
            :industry_id,
            :relationship_type,
            SYSTIMESTAMP
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1
            FROM CASE_STUDY_INDUSTRY
            WHERE CASE_STUDY_ID = :case_study_id
              AND INDUSTRY_ID = :industry_id
        )
        """,
        {
            "case_study_id": case_study_id,
            "industry_id": industry_id,
            "relationship_type": relationship_type,
        },
    )


def get_case_study_industries(
    case_study_id: int,
) -> list[dict[str, Any]]:
    """Return industries linked to a case study."""
    return fetch_all(
        """
        SELECT
            csi.CASE_STUDY_ID,
            csi.INDUSTRY_ID,
            csi.RELATIONSHIP_TYPE,
            i.INDUSTRY_CODE,
            i.INDUSTRY_NAME,
            i.DESCRIPTION
        FROM CASE_STUDY_INDUSTRY csi
        JOIN INDUSTRY i
          ON i.INDUSTRY_ID = csi.INDUSTRY_ID
        WHERE csi.CASE_STUDY_ID = :case_study_id
        ORDER BY i.INDUSTRY_NAME
        """,
        {
            "case_study_id": case_study_id,
        },
    )


# ============================================================
# CASE STUDY → FRAMEWORK
# ============================================================

def link_framework(
    case_study_id: int,
    framework_id: int,
    relationship_type: str = "USED",
) -> int:
    """Link a case study to a framework."""
    return execute(
        """
        INSERT INTO CASE_STUDY_FRAMEWORK (
            CASE_STUDY_ID,
            FRAMEWORK_ID,
            RELATIONSHIP_TYPE,
            CREATED_AT
        )
        SELECT
            :case_study_id,
            :framework_id,
            :relationship_type,
            SYSTIMESTAMP
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1
            FROM CASE_STUDY_FRAMEWORK
            WHERE CASE_STUDY_ID = :case_study_id
              AND FRAMEWORK_ID = :framework_id
        )
        """,
        {
            "case_study_id": case_study_id,
            "framework_id": framework_id,
            "relationship_type": relationship_type,
        },
    )


def get_case_study_frameworks(
    case_study_id: int,
) -> list[dict[str, Any]]:
    """Return frameworks linked to a case study."""
    return fetch_all(
        """
        SELECT
            csf.CASE_STUDY_ID,
            csf.FRAMEWORK_ID,
            csf.RELATIONSHIP_TYPE,
            f.FRAMEWORK_CODE,
            f.FRAMEWORK_NAME,
            f.DESCRIPTION
        FROM CASE_STUDY_FRAMEWORK csf
        JOIN FRAMEWORK f
          ON f.FRAMEWORK_ID = csf.FRAMEWORK_ID
        WHERE csf.CASE_STUDY_ID = :case_study_id
        ORDER BY f.FRAMEWORK_NAME
        """,
        {
            "case_study_id": case_study_id,
        },
    )


# ============================================================
# CASE STUDY → OUTCOME
# ============================================================

def link_outcome(
    case_study_id: int,
    outcome_id: int,
    relationship_type: str = "PRIMARY",
) -> int:
    """Link a case study to an outcome."""
    return execute(
        """
        INSERT INTO CASE_STUDY_OUTCOME (
            CASE_STUDY_ID,
            OUTCOME_ID,
            RELATIONSHIP_TYPE,
            CREATED_AT
        )
        SELECT
            :case_study_id,
            :outcome_id,
            :relationship_type,
            SYSTIMESTAMP
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1
            FROM CASE_STUDY_OUTCOME
            WHERE CASE_STUDY_ID = :case_study_id
              AND OUTCOME_ID = :outcome_id
        )
        """,
        {
            "case_study_id": case_study_id,
            "outcome_id": outcome_id,
            "relationship_type": relationship_type,
        },
    )


def get_case_study_outcomes(
    case_study_id: int,
) -> list[dict[str, Any]]:
    """Return outcomes linked to a case study."""
    return fetch_all(
        """
        SELECT
            cso.CASE_STUDY_ID,
            cso.OUTCOME_ID,
            cso.RELATIONSHIP_TYPE,
            o.OUTCOME_CODE,
            o.OUTCOME_NAME,
            o.DESCRIPTION
        FROM CASE_STUDY_OUTCOME cso
        JOIN OUTCOME o
          ON o.OUTCOME_ID = cso.OUTCOME_ID
        WHERE cso.CASE_STUDY_ID = :case_study_id
        ORDER BY o.OUTCOME_NAME
        """,
        {
            "case_study_id": case_study_id,
        },
    )


# ============================================================
# CASE STUDY → EVIDENCE
# ============================================================

def link_evidence(
    case_study_id: int,
    chunk_id: int,
    evidence_type: str = "SOURCE",
    relevance_note: Optional[str] = None,
) -> int:
    """
    Link a case study to a source document chunk.

    This is the important evidence trail that lets us
    trace structured knowledge back to the original
    Terragni document.
    """
    return execute(
        """
        INSERT INTO CASE_STUDY_EVIDENCE (
            CASE_STUDY_ID,
            CHUNK_ID,
            EVIDENCE_TYPE,
            RELEVANCE_NOTE,
            CREATED_AT
        )
        SELECT
            :case_study_id,
            :chunk_id,
            :evidence_type,
            :relevance_note,
            SYSTIMESTAMP
        FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1
            FROM CASE_STUDY_EVIDENCE
            WHERE CASE_STUDY_ID = :case_study_id
              AND CHUNK_ID = :chunk_id
        )
        """,
        {
            "case_study_id": case_study_id,
            "chunk_id": chunk_id,
            "evidence_type": evidence_type,
            "relevance_note": relevance_note,
        },
    )


def get_case_study_evidence(
    case_study_id: int,
) -> list[dict[str, Any]]:
    """Return evidence chunks linked to a case study."""
    return fetch_all(
        """
        SELECT
            cse.CASE_STUDY_ID,
            cse.CHUNK_ID,
            cse.EVIDENCE_TYPE,
            cse.RELEVANCE_NOTE,
            cse.CREATED_AT
        FROM CASE_STUDY_EVIDENCE cse
        WHERE cse.CASE_STUDY_ID = :case_study_id
        ORDER BY cse.CHUNK_ID
        """,
        {
            "case_study_id": case_study_id,
        },
    )


# ============================================================
# COMPLETE CASE STUDY
# ============================================================

def get_case_study_details(
    case_study_id: int,
) -> Optional[dict[str, Any]]:
    """
    Return a case study together with all of its
    structured relationships and evidence.
    """
    case_study = get_case_study(case_study_id)

    if not case_study:
        return None

    case_study["challenges"] = get_case_study_challenges(
        case_study_id
    )

    case_study["offerings"] = get_case_study_offerings(
        case_study_id
    )

    case_study["industries"] = get_case_study_industries(
        case_study_id
    )

    case_study["frameworks"] = get_case_study_frameworks(
        case_study_id
    )

    case_study["outcomes"] = get_case_study_outcomes(
        case_study_id
    )

    case_study["evidence"] = get_case_study_evidence(
        case_study_id
    )

    return case_study