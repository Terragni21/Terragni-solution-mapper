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

def load_embeddings(
    connection
) -> list[dict[str, Any]]:
    """
    Load semantic embeddings and all available Terragni
    metadata associated with each chunk.

    Important:
    A chunk is NOT assumed to belong to a case study.

    case_study_evidence is used to determine whether an
    explicit case-study relationship exists.
    """

    sql = """
        SELECT
            e.chunk_id,
            e.model_name,
            e.dimensions,
            e.embedding_json,

            c.document_id,
            c.section_id,
            c.chunk_order,
            c.chunk_text,

            d.title AS document_title,
            d.file_name,
            d.document_type,

            ds.section_type,
            ds.section_title,

            cse.case_study_id,
            cse.evidence_type,
            cse.relevance_note,

            cs.case_study_code,
            cs.title AS case_study_title,
            cs.public_title,
            cs.client_name,
            cs.summary AS case_study_summary,
            cs.challenge AS case_study_challenge,
            cs.objective AS case_study_objective,
            cs.approach AS case_study_approach,
            cs.key_finding AS case_study_key_finding,
            cs.solution AS case_study_solution,
            cs.business_outcome AS case_study_business_outcome

        FROM document_chunk_embedding e

        INNER JOIN document_chunk c
            ON c.chunk_id = e.chunk_id

        LEFT JOIN document d
            ON d.document_id = c.document_id

        LEFT JOIN document_section ds
            ON ds.section_id = c.section_id

        LEFT JOIN case_study_evidence cse
            ON cse.chunk_id = c.chunk_id

        LEFT JOIN case_study cs
            ON cs.case_study_id = cse.case_study_id

        WHERE e.model_name = %s

        ORDER BY e.chunk_id
    """

    results: list[dict[str, Any]] = []

    with connection.cursor() as cursor:

        cursor.execute(
            sql,
            (DB_EMBEDDING_MODEL,)
        )

        for row in cursor:

            (
                chunk_id,
                model_name,
                dimensions,
                embedding_json,

                document_id,
                section_id,
                chunk_order,
                chunk_text,

                document_title,
                file_name,
                document_type,

                section_type,
                section_title,

                case_study_id,
                evidence_type,
                relevance_note,

                case_study_code,
                case_study_title,
                public_title,
                client_name,
                case_study_summary,
                case_study_challenge,
                case_study_objective,
                case_study_approach,
                case_study_key_finding,
                case_study_solution,
                case_study_business_outcome

            ) = row

            if embedding_json is None:
                continue

            # Handle Oracle CLOBs and plain PostgreSQL text alike.
            if hasattr(
                embedding_json,
                "read"
            ):
                embedding_json = (
                    embedding_json.read()
                )

            embedding = json.loads(
                str(embedding_json)
            )

            if hasattr(
                chunk_text,
                "read"
            ):
                chunk_text = chunk_text.read()

            results.append(
                {
                    "chunk_id": int(chunk_id),
                    "model_name": model_name,
                    "dimensions": int(dimensions),

                    "embedding": embedding,

                    "document_id": int(document_id),
                    "section_id": int(section_id),
                    "chunk_order": int(chunk_order),

                    "chunk_text": str(
                        chunk_text or ""
                    ),

                    "document": {
                        "title": document_title,
                        "file_name": file_name,
                        "document_type": document_type,
                    },

                    "section": {
                        "section_type": section_type,
                        "section_title": section_title,
                    },

                    "case_study": (
                        {
                            "case_study_id": int(
                                case_study_id
                            ),
                            "case_study_code": case_study_code,
                            "title": case_study_title,
                            "public_title": public_title,
                            "client_name": client_name,
                            "summary": case_study_summary,
                            "challenge": case_study_challenge,
                            "objective": case_study_objective,
                            "approach": case_study_approach,
                            "key_finding": case_study_key_finding,
                            "solution": case_study_solution,
                            "business_outcome": case_study_business_outcome,

                            "evidence_type": evidence_type,
                            "relevance_note": relevance_note,
                        }
                        if case_study_id is not None
                        else None
                    ),
                }
            )

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
