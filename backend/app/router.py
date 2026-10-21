"""Terragni document retrieval + strictly grounded LLM synthesis."""

from __future__ import annotations

import json
from pathlib import Path

from .config import KB_PATH
from .retriever import Retriever
from .llm_mapper import (
    build_messages,
    call_llm,
    parse_llm_response,
)


# -------------------------------------------------------------------
# TERRAGNI KNOWLEDGE BASE
# -------------------------------------------------------------------

KB = json.loads(
    KB_PATH.read_text(
        encoding="utf-8"
    )
)


# -------------------------------------------------------------------
# DOCUMENT RETRIEVER
# -------------------------------------------------------------------

# Built lazily. The production journey does not use this legacy keyword
# retriever, and building it means parsing every PDF/PPTX in raw_sources
# (one is 100 MB) - doing that at import time made every Render boot slow
# and could run the 512 MB instance out of memory.
_RETRIEVER: Retriever | None = None


def get_retriever() -> Retriever:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = Retriever()
    return _RETRIEVER


def retrieve_evidence(
    query: str,
    top_k: int = 15,
) -> list[dict]:
    """
    Search the indexed Terragni source material.

    The retriever is responsible for finding the most relevant
    uploaded documents/chunks for the visitor's challenge.
    """

    query = str(query or "").strip()

    if not query:
        return []

    return get_retriever().search(
        query,
        top_k=top_k,
    )


# -------------------------------------------------------------------
# LLM MAPPING
# -------------------------------------------------------------------

def map_with_llm(
    query: str,
    evidence: list[dict],
) -> dict:
    """
    Send the visitor's challenge plus retrieved Terragni evidence
    to the LLM and return the validated structured result.

    The LLM is not allowed to invent Terragni material.

    The LLM mapper is also responsible for determining whether the
    challenge is:

        - matched
        - needs_clarification
        - not_supported

    A solution page should only be produced when the challenge has
    sufficient Terragni grounding.
    """

    query = str(query or "").strip()

    if not query:
        return {
            "match_status": "needs_clarification",
            "clarification_question": (
                "Please describe the business challenge "
                "you would like to explore."
            ),
            "page_title": "",
            "problem_summary": "",
            "diagnosis": "",
            "primary_offering": "",
            "matched_offerings": [],
            "solution_title": "",
            "solution": "",
            "how_it_works": [],
            "frameworks": [],
            "expected_outcomes": [],
            "case_study_ids": [],
            "why_this_fits": "",
            "recommended_next_step": "",
            "evidence_status": "limited",
            "documented_evidence": [],
        }

    evidence = (
        evidence
        if isinstance(evidence, list)
        else []
    )

    messages = build_messages(
        KB,
        query,
        evidence,
    )

    raw_response = call_llm(
        messages
    )

    result = parse_llm_response(
        raw_response,
        KB,
        evidence,
    )

    # ---------------------------------------------------------------
    # NORMALISE MATCH STATUS
    # ---------------------------------------------------------------

    valid_statuses = {
        "matched",
        "needs_clarification",
        "not_supported",
    }

    status = result.get(
        "match_status"
    )

    if status not in valid_statuses:
        status = "needs_clarification"

    result["match_status"] = status

    # ---------------------------------------------------------------
    # SAFETY: NON-MATCHED RESULTS MUST NOT CARRY A FAKE SOLUTION
    # ---------------------------------------------------------------

    if status != "matched":
        result["primary_offering"] = ""
        result["matched_offerings"] = []
        result["solution_title"] = ""
        result["solution"] = ""
        result["how_it_works"] = []
        result["frameworks"] = []
        result["expected_outcomes"] = []
        result["case_study_ids"] = []
        result["why_this_fits"] = ""
        result["recommended_next_step"] = ""

    # ---------------------------------------------------------------
    # SAFETY: CASE STUDIES MUST HAVE GROUNDED EVIDENCE
    # ---------------------------------------------------------------

    if not result.get(
        "documented_evidence"
    ):
        result["case_study_ids"] = []

    return result


# -------------------------------------------------------------------
# INTERNAL CASE-STUDY LOOKUP
# -------------------------------------------------------------------

def get_case_studies(
    ids,
) -> list[dict]:
    """
    Resolve internal case-study IDs to knowledge-base records.

    IMPORTANT:
    These IDs are internal only. They should NOT be displayed
    directly on the public website.
    """

    if not isinstance(ids, list):
        return []

    by_id = {
        case["id"]: case
        for case in KB.get(
            "case_studies",
            []
        )
        if isinstance(case, dict)
        and case.get("id")
    }

    results = []

    for case_id in ids:
        if case_id in by_id:
            results.append(
                by_id[case_id]
            )

    return results


# -------------------------------------------------------------------
# INTERNAL OFFERING LOOKUP
# -------------------------------------------------------------------

def get_offering(
    offering_id: str,
):
    """
    Resolve an internal Terragni offering ID.

    Returns None when the ID does not exist.
    """

    if not offering_id:
        return None

    for offering in KB.get(
        "offerings",
        [],
    ):
        if (
            isinstance(offering, dict)
            and offering.get("id") == offering_id
        ):
            return offering

    return None


# -------------------------------------------------------------------
# CASE-STUDY CONTENT
# -------------------------------------------------------------------

def load_case_study_content(
    case_study_id: str,
):
    """
    Load the Markdown content for an internal case study.

    The case-study ID is used only internally to locate the file.
    """

    if not case_study_id:
        return None

    # Only allow a simple internal ID.
    # This prevents path traversal such as ../../some-file.
    if (
        "/" in case_study_id
        or "\\" in case_study_id
        or ".." in case_study_id
    ):
        return None

    case_study_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "case_studies"
        / f"{case_study_id}.md"
    )

    if not case_study_path.exists():
        return None

    return case_study_path.read_text(
        encoding="utf-8"
    )

