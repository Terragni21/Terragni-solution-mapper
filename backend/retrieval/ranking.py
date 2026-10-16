from __future__ import annotations

from typing import Any


# ============================================================
# SEMANTIC RESULT RANKING
# ============================================================

def rank_results(
    results: list[dict[str, Any]],
    top_k: int = 10
) -> list[dict[str, Any]]:
    """
    Rank semantic retrieval results by cosine similarity.

    This module deliberately does not contain phrase-based
    business rules.

    Similarity comes from the embedding model.
    """

    if not results:
        return []

    ranked = sorted(
        results,
        key=lambda item: item.get(
            "similarity",
            0.0
        ),
        reverse=True
    )

    return ranked[:top_k]


# ============================================================
# REMOVE DUPLICATE CHUNKS
# ============================================================

def deduplicate_results(
    results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Remove duplicate CHUNK_ID values while preserving
    highest-ranked results.
    """

    seen: set[int] = set()
    unique_results = []

    for result in results:

        chunk_id = result.get(
            "chunk_id"
        )

        if chunk_id in seen:
            continue

        seen.add(chunk_id)

        unique_results.append(
            result
        )

    return unique_results


# ============================================================
# FINAL RANKING PIPELINE
# ============================================================

def prepare_ranked_results(
    results: list[dict[str, Any]],
    top_k: int = 10
) -> list[dict[str, Any]]:
    """
    Clean and rank semantic search results.
    """

    unique_results = (
        deduplicate_results(results)
    )

    return rank_results(
        unique_results,
        top_k=top_k
    )