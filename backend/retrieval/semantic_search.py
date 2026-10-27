from __future__ import annotations

import json
import os
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
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

# FastEmbed model used to embed the visitor's question at query time.
#
# It must match the model that produced the chunk vectors stored in the local
# Oracle table DOCUMENT_CHUNK_EMBEDDING. Those were made with Ollama
# "nomic-embed-text" (= nomic-embed-text v1.5), so the query is embedded with
# the same model. Everything runs on this computer.
FASTEMBED_MODEL = os.getenv(
    "FASTEMBED_MODEL",
    "nomic-ai/nomic-embed-text-v1.5-Q"
).strip()

# Where the ONNX model is cached. It must live INSIDE the project so the
# copy downloaded during the Render build is still there at run time
# (/tmp is wiped between the build and the running service).
FASTEMBED_CACHE_DIR = os.getenv(
    "FASTEMBED_CACHE_DIR",
    str(BACKEND_DIR / "model_cache"),
).strip()

# The model_name stored in document_chunk_embedding during ingestion.
DB_EMBEDDING_MODEL = os.getenv(
    "DB_EMBEDDING_MODEL",
    "nomic-embed-text"
).strip()


def memory_mb() -> int | None:
    """Resident memory of this process in MB (Linux only)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024)
    except OSError:
        return None
    return None


def log_memory(stage: str) -> None:
    """Print memory use so it shows in the Render Logs tab."""
    print(f"[memory] {stage}: {memory_mb()} MB", flush=True)


# ============================================================
# FASTEMBED
# ============================================================

_FASTEMBED_LOCK = threading.Lock()
_FASTEMBED_INSTANCE = None


def _get_fastembed_model():
    """Thread-safe singleton loader for the FastEmbed model."""
    global _FASTEMBED_INSTANCE
    if _FASTEMBED_INSTANCE is None:
        with _FASTEMBED_LOCK:
            if _FASTEMBED_INSTANCE is None:
                from fastembed import TextEmbedding
                _FASTEMBED_INSTANCE = TextEmbedding(
                    model_name=FASTEMBED_MODEL,
                    cache_dir=FASTEMBED_CACHE_DIR,
                    threads=int(os.getenv("FASTEMBED_THREADS", "1")),
                    # ONNX's memory arena keeps large buffers after each
                    # call; on a 512 MB instance that is what pushed the
                    # process over the limit (Render then returns 502).
                    enable_cpu_mem_arena=False,
                )
                log_memory(f"after loading embedding model {FASTEMBED_MODEL}")
    return _FASTEMBED_INSTANCE


@lru_cache(maxsize=512)
def _cached_embedding(text: str) -> tuple[float, ...]:
    model = _get_fastembed_model()
    embeddings = list(model.embed([text], batch_size=1))

    if not embeddings:
        raise RuntimeError(
            "FastEmbed returned no embedding."
        )

    return tuple(float(v) for v in embeddings[0])


def create_query_embedding(
    query: str
) -> list[float]:

    query = (query or "").strip()

    if not query:
        raise ValueError(
            "Search query cannot be empty."
        )

    return list(_cached_embedding(query))


# ============================================================
# COSINE SIMILARITY
# ============================================================

def cosine_similarity(
    vector_a,
    vector_b,
) -> float:

    a = np.asarray(vector_a, dtype=np.float32)
    b = np.asarray(vector_b, dtype=np.float32)

    if a.shape != b.shape:
        raise ValueError(
            "Vector dimensions do not match: "
            f"{a.shape[0]} != {b.shape[0]}"
        )

    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm == 0.0:
        return 0.0
    return float(np.dot(a, b) / norm)


# ============================================================
# DATABASE EMBEDDINGS + SOURCE METADATA
# ============================================================

def _parse_vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return None
    return [float(v) for v in parsed] if isinstance(parsed, list) else None


def _load_db_embeddings(cursor) -> dict[int, list[float]]:
    """Chunk embeddings stored in Oracle (DOCUMENT_CHUNK_EMBEDDING)."""
    cursor.execute(
        """
        SELECT chunk_id, embedding_json
        FROM document_chunk_embedding
        WHERE model_name = %s
        """,
        (DB_EMBEDDING_MODEL,),
    )
    vectors: dict[int, list[float]] = {}
    for chunk_id, embedding_json in cursor.fetchall():
        vector = _parse_vector(embedding_json)
        if vector:
            vectors[int(chunk_id)] = vector
    return vectors


def _load_precomputed_embeddings() -> dict[int, list[float]]:
    """
    Optional local fallback: backend/data/oracle_embeddings_export.json.

    This file is git-ignored, so it does NOT exist on Render. It is only
    used on a developer machine when the database table is empty.
    """
    data_file = BACKEND_DIR / "data" / "oracle_embeddings_export.json"
    if not data_file.exists():
        return {}
    try:
        raw = json.loads(data_file.read_text(encoding="utf-8"))
        vectors = {}
        for item in raw:
            if item.get("chunk_id") is None:
                continue
            vector = _parse_vector(item.get("embedding_json"))
            if vector:
                vectors[int(item["chunk_id"])] = vector
        return vectors
    except Exception as exc:
        print(f"Warning: failed to load {data_file.name}: {exc}")
        return {}


def load_embeddings(
    connection
) -> list[dict[str, Any]]:
    """
    Load chunk embeddings and the Terragni metadata for each chunk.

    Embeddings come from the DOCUMENT_CHUNK_EMBEDDING table in the local Oracle database.
    
    """
    with connection.cursor() as cursor:
        vectors = _load_db_embeddings(cursor)

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

        cursor.execute(
            "SELECT chunk_id, case_study_id, evidence_type, relevance_note "
            "FROM case_study_evidence ORDER BY case_study_id"
        )
        evs = {r[0]: (r[1], r[2], r[3]) for r in cursor.fetchall()}

        cursor.execute("""
            SELECT chunk_id, document_id, section_id, chunk_order, chunk_text
            FROM document_chunk
            ORDER BY chunk_id
        """)
        chunks = cursor.fetchall()

    if not vectors:
        vectors = _load_precomputed_embeddings()

    if not vectors:
        raise RuntimeError(
            "No chunk embeddings found. document_chunk_embedding is empty for "
            f"model_name='{DB_EMBEDDING_MODEL}'. Run "
            "'python -m backend.embeddings.ollama_embeddings' to create them "
            "in Oracle."
        )

    results: list[dict[str, Any]] = []
    for c_id, d_id, s_id, order, text in chunks:
        vec = vectors.get(int(c_id))
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
    "matrix": None,
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

        if not rows:
            raise RuntimeError(
                "Embeddings were found but none matched a document_chunk row. "
                "Re-run the migration so chunk IDs and embeddings line up."
            )

        link_chunks_to_document_case_study(rows)

        # Pre-normalised matrix so one query is a single matrix product.
        matrix = np.asarray([row["embedding"] for row in rows], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms

        # The matrix now holds the vectors; free the Python lists (memory
        # matters on a 512 MB Render instance).
        for row in rows:
            row.pop("embedding", None)

        _EMBEDDING_CACHE["rows"] = rows
        _EMBEDDING_CACHE["matrix"] = matrix
        _EMBEDDING_CACHE["loaded_at"] = time.time()

        import gc
        gc.collect()
        log_memory(f"after loading {len(rows)} chunk embeddings")

        return rows


def _get_cached_matrix() -> tuple[list[dict[str, Any]], Any]:
    get_cached_embeddings()
    with _EMBEDDING_CACHE_LOCK:
        return _EMBEDDING_CACHE["rows"], _EMBEDDING_CACHE["matrix"]


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
        _EMBEDDING_CACHE["matrix"] = None
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

    query_vector = np.asarray(create_query_embedding(query), dtype=np.float32)
    query_norm = float(np.linalg.norm(query_vector)) or 1.0
    query_vector = query_vector / query_norm

    stored_embeddings, matrix = _get_cached_matrix()

    if matrix is None or not len(stored_embeddings):
        return []

    if matrix.shape[1] != query_vector.shape[0]:
        raise ValueError(
            "Query embedding has "
            f"{query_vector.shape[0]} dimensions but stored embeddings have "
            f"{matrix.shape[1]}. Check FASTEMBED_MODEL."
        )

    similarities = matrix @ query_vector

    scored_results = []

    for index in np.argsort(-similarities):
        similarity = float(similarities[index])

        if similarity < minimum_similarity:
            break

        result = dict(stored_embeddings[index])
        result["similarity"] = similarity

        scored_results.append(result)

        if len(scored_results) >= top_k:
            break

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
