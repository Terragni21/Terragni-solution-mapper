from __future__ import annotations

from typing import Any


# ============================================================
# GENERAL RESULT FILTERING
# ============================================================

def filter_by_similarity(
    results: list[dict[str, Any]],
    minimum_similarity: float = 0.0
) -> list[dict[str, Any]]:
    """
    Keep results above the requested semantic similarity.

    This is a semantic threshold, not a phrase rule.
    """

    return [
        result
        for result in results
        if result.get(
            "similarity",
            0.0
        ) >= minimum_similarity
    ]


# ============================================================
# DOCUMENT FILTER
# ============================================================

def filter_by_document_ids(
    results: list[dict[str, Any]],
    document_ids: set[int] | None = None
) -> list[dict[str, Any]]:
    """
    Optionally restrict results to specific Oracle documents.

    If document_ids is None, no document filtering occurs.
    """

    if document_ids is None:
        return results

    return [
        result
        for result in results
        if result.get(
            "document_id"
        ) in document_ids
    ]


# ============================================================
# SECTION FILTER
# ============================================================

def filter_by_section_ids(
    results: list[dict[str, Any]],
    section_ids: set[int] | None = None
) -> list[dict[str, Any]]:
    """
    Optionally restrict results to specific Oracle sections.
    """

    if section_ids is None:
        return results

    return [
        result
        for result in results
        if result.get(
            "section_id"
        ) in section_ids
    ]


# ============================================================
# COMBINED FILTER
# ============================================================

def apply_filters(
    results: list[dict[str, Any]],
    minimum_similarity: float = 0.0,
    document_ids: set[int] | None = None,
    section_ids: set[int] | None = None
) -> list[dict[str, Any]]:
    """
    Apply optional metadata and similarity filters.

    Industry-specific filtering will be added after we connect
    the CASE_STUDY / INDUSTRY relationships to retrieval.

    No hard-coded phrase-to-offering rules belong here.
    """

    filtered = filter_by_similarity(
        results,
        minimum_similarity
    )

    filtered = filter_by_document_ids(
        filtered,
        document_ids
    )

    filtered = filter_by_section_ids(
        filtered,
        section_ids
    )

    return filtered