from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# ============================================================
# PATHS
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(BACKEND_DIR / ".env")

# FastEmbed model that produces 768-dim vectors compatible with stored embeddings.
FASTEMBED_MODEL = os.getenv(
    "FASTEMBED_MODEL",
    "nomic-ai/nomic-embed-text-v1"
).strip()

# The model_name stored in the DB during ingestion (used to filter rows).
DB_EMBEDDING_MODEL = os.getenv(
    "DB_EMBEDDING_MODEL",
    "nomic-embed-text"
).strip()


# ============================================================
# FASTEMBED
# ============================================================

@lru_cache(maxsize=1)
def _get_fastembed_model():
    """Lazy-load the FastEmbed model (downloads on first use)."""
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=FASTEMBED_MODEL)


@lru_cache(maxsize=512)
def _cached_embedding(text: str) -> tuple[float, ...]:
    model = _get_fastembed_model()
    embeddings = list(model.embed([text]))

    if not embeddings:
        raise RuntimeError(
            "FastEmbed returned no embedding."
        )

    return tuple(float(v) for v in embeddings[0])


def create_query_embedding(
    query: str
) -> list[float]:

    query = query.strip()

    if not query:
        raise ValueError(
            "Search query cannot be empty."
        )

    return list(_cached_embedding(query))


# ============================================================
# COSINE SIMILARITY
# ============================================================

def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float]
) -> float:

    if len(vector_a) != len(vector_b):
        raise ValueError(
            "Vector dimensions do not match: "
            f"{len(vector_a)} != {len(vector_b)}"
        )

    dot_product = 0.0
    magnitude_a = 0.0
    magnitude_b = 0.0

    for a, b in zip(vector_a, vector_b):

        dot_product += a * b
        magnitude_a += a * a
        magnitude_b += b * b

    magnitude_a = math.sqrt(
        magnitude_a
    )

    magnitude_b = math.sqrt(
        magnitude_b
    )

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (
        magnitude_a * magnitude_b
    )


# ============================================================
# DATABASE EMBEDDINGS + SOURCE METADATA
# ============================================================

def _load_precomputed_embeddings() -> dict[int, list[float]]:
    """Fast local lookup of 768-dim embeddings from the repository export."""
    data_file = BACKEND_DIR / "data" / "oracle_embeddings_export.json"
    if data_file.exists():
        try:
            raw = json.loads(data_file.read_text(encoding="utf-8"))
            return {
                int(item["chunk_id"]): (
                    json.loads(item["embedding_json"])
                    if isinstance(item["embedding_json"], str)
                    else item["embedding_json"]
                )
                for item in raw
                if item.get("chunk_id") is not None and item.get("embedding_json") is not None
            }
        except Exception as e:
            print(f"Warning: Failed to load precomputed embeddings: {e}")
    return {}


def load_embeddings(
    connection
) -> list[dict[str, Any]]:
    """
    Load semantic embeddings and all available Terragni
    metadata associated with each chunk.

    Uses fast precomputed embeddings joined with database metadata,
    falling back to querying document_chunk_embedding directly if needed.
    """
    local_vectors = _load_precomputed_embeddings()

    with connection.cursor() as cursor:
        # Load reference data into in-memory dictionaries for speed
        cursor.execute("SELECT document_id, title, file_name, document_type FROM document")
        docs = {
            r[0]: {"title": r[1], "file_name": r[2], "document_type": r[3]}
            for r in cursor.fetchall()
        }

        cursor.execute("SELECT section_id, section_type, section_title FROM document_section")
        secs = {
            r[0]: {"section_type": r[1], "section_title": r[2]}
            for r in cursor.fetchall()
        }

        cursor.execute("""
            SELECT case_study_id, case_study_code, title, public_title, client_name,
                   summary, challenge, objective, approach, key_finding, solution, business_outcome
            FROM case_study
        """)
        cases = {
            r[0]: {
                "case_study_id": r[0],
                "case_study_code": r[1],
                "title": r[2],
                "public_title": r[3],
                "client_name": r[4],
                "summary": r[5],
                "challenge": r[6],
                "objective": r[7],
                "approach": r[8],
                "key_finding": r[9],
                "solution": r[10],
                "business_outcome": r[11],
            }
            for r in cursor.fetchall()
        }

        cursor.execute("SELECT chunk_id, case_study_id, evidence_type, relevance_note FROM case_study_evidence")
        evs = {r[0]: (r[1], r[2], r[3]) for r in cursor.fetchall()}

        cursor.execute("""
            SELECT chunk_id, document_id, section_id, chunk_order, chunk_text
            FROM document_chunk
            ORDER BY chunk_id
        """)
        chunks = cursor.fetchall()

    results: list[dict[str, Any]] = []
    for c_id, d_id, s_id, order, text in chunks:
        vec = local_vectors.get(c_id)
        if not vec:
            continue

        cs_info = None
        if c_id in evs:
            cid, etype, rnote = evs[c_id]
            if cid in cases:
                cs_info = dict(cases[cid])
                cs_info["evidence_type"] = etype
                cs_info["relevance_note"] = rnote

        results.append({
            "chunk_id": int(c_id),
            "model_name": DB_EMBEDDING_MODEL,
            "dimensions": len(vec),
            "embedding": vec,
            "document_id": int(d_id),
            "section_id": int(s_id) if s_id is not None else 0,
            "chunk_order": int(order) if order is not None else 0,
            "chunk_text": str(text or ""),
            "document": docs.get(d_id, {}),
            "section": secs.get(s_id, {}),
            "case_study": cs_info,
        })

    return results

# ============================================================
# SEMANTIC SEARCH
# ============================================================

# Embeddings change only when the knowledge pipeline runs, so they are kept in
# memory instead of being re-read from the database on every query.
EMBEDDING_CACHE_SECONDS = int(
    os.getenv("EMBEDDING_CACHE_SECONDS", "900")
)

_EMBEDDING_CACHE: dict[str, Any] = {
    "rows": None,
    "loaded_at": 0.0,
}

_EMBEDDING_CACHE_LOCK = threading.Lock()


def get_cached_embeddings() -> list[dict[str, Any]]:

    with _EMBEDDING_CACHE_LOCK:

        rows = _EMBEDDING_CACHE["rows"]
        age = time.time() - _EMBEDDING_CACHE["loaded_at"]

        if rows is not None and age < EMBEDDING_CACHE_SECONDS:
            return rows

        from backend.database.connection import (
            get_connection
        )

        connection = get_connection()

        try:
            rows = load_embeddings(connection)
        finally:
            connection.close()

        link_chunks_to_document_case_study(rows)

        _EMBEDDING_CACHE["rows"] = rows
        _EMBEDDING_CACHE["loaded_at"] = time.time()

        return rows


def link_chunks_to_document_case_study(
    rows: list[dict[str, Any]],
) -> None:
    """
    Attach untagged chunks to their document's case study.

    In the database only 2-3 chunks per case-study document are linked through
    case_study_evidence; the rest of the same document is untagged, so a
    strong match on an untagged chunk could not be credited to the case
    study. When every linked chunk of a document points to the SAME case
    study, the document is that case study, and its other chunks are
    marked as evidence with evidence_type "same_document".

    Documents linked to several case studies (e.g. a brochure with mini
    cases) and documents with no links (brochures) are left untouched.
    The database itself is not modified.
    """
    by_document: dict[int, dict[int, dict[str, Any]]] = {}

    for row in rows:
        case_study = row.get("case_study")
        if case_study:
            by_document.setdefault(row["document_id"], {})[
                case_study["case_study_id"]
            ] = case_study

    for row in rows:
        if row.get("case_study"):
            continue

        cases = by_document.get(row["document_id"], {})
        if len(cases) != 1:
            continue

        inferred = dict(next(iter(cases.values())))
        inferred["evidence_type"] = "same_document"
        inferred["relevance_note"] = (
            "Part of the same case-study document as the "
            "explicitly linked evidence."
        )
        row["case_study"] = inferred


def clear_embedding_cache() -> None:

    with _EMBEDDING_CACHE_LOCK:
        _EMBEDDING_CACHE["rows"] = None
        _EMBEDDING_CACHE["loaded_at"] = 0.0


def semantic_search(
    query: str,
    top_k: int = 10,
    minimum_similarity: float = 0.0
) -> list[dict[str, Any]]:

    if top_k <= 0:
        raise ValueError(
            "top_k must be greater than zero."
        )

    query_embedding = (
        create_query_embedding(query)
    )

    stored_embeddings = (
        get_cached_embeddings()
    )

    scored_results = []

    for record in stored_embeddings:

        similarity = cosine_similarity(
            query_embedding,
            record["embedding"]
        )

        if similarity < minimum_similarity:
            continue

        result = dict(record)

        # Do not expose the large vector to the rest
        # of the application.
        result.pop(
            "embedding",
            None
        )

        result["similarity"] = similarity

        scored_results.append(
            result
        )

    scored_results.sort(
        key=lambda item: item["similarity"],
        reverse=True
    )

    return scored_results[:top_k]


# ============================================================
# PRINT RESULTS
# ============================================================

def print_search_results(
    query: str,
    results: list[dict[str, Any]]
) -> None:

    print()
    print("=" * 90)
    print("TERRAGNI SEMANTIC SEARCH")
    print("=" * 90)

    print(
        f"Query: {query}"
    )

    print(
        f"Results: {len(results)}"
    )

    print("-" * 90)

    for index, result in enumerate(
        results,
        start=1
    ):

        print()
        print(
            f"RESULT #{index}"
        )

        print(
            f"Similarity : "
            f"{result['similarity']:.6f}"
        )

        print(
            f"Chunk ID   : "
            f"{result['chunk_id']}"
        )

        print(
            f"Document ID: "
            f"{result['document_id']}"
        )

        document = result["document"]

        print(
            f"Document   : "
            f"{document.get('title')}"
        )

        section = result["section"]

        print(
            f"Section    : "
            f"{section.get('section_title')}"
        )

        case_study = result.get(
            "case_study"
        )

        if case_study:

            print(
                f"Case Study : "
                f"{case_study.get('title')}"
            )

            print(
                f"Evidence   : "
                f"{case_study.get('evidence_type')}"
            )

        else:

            print(
                "Case Study : No explicit "
                "case-study evidence relationship"
            )

        print("-" * 90)

        print(
            result["chunk_text"]
        )

        print("-" * 90)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_query = (
        "Our affluent banking customers are happy "
        "but not engaged. What is really driving "
        "that gap?"
    )

    results = semantic_search(
        query=test_query,
        top_k=10
    )

    print_search_results(
        test_query,
        results
    )
