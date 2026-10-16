from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

import ollama
from dotenv import load_dotenv


# ============================================================
# PROJECT PATH
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(BACKEND_DIR / ".env")


# ============================================================
# OLLAMA CONFIGURATION
# ============================================================

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://localhost:11434"
).strip()

OLLAMA_EMBEDDING_MODEL = os.getenv(
    "OLLAMA_EMBEDDING_MODEL",
    "nomic-embed-text"
).strip()

BATCH_SIZE = int(
    os.getenv(
        "OLLAMA_EMBEDDING_BATCH_SIZE",
        "16"
    ).strip()
)


# ============================================================
# VALIDATE CONFIGURATION
# ============================================================

def validate_config() -> None:

    if not OLLAMA_HOST:
        raise RuntimeError(
            "OLLAMA_HOST cannot be empty."
        )

    if not OLLAMA_EMBEDDING_MODEL:
        raise RuntimeError(
            "OLLAMA_EMBEDDING_MODEL cannot be empty."
        )

    if BATCH_SIZE <= 0:
        raise RuntimeError(
            "OLLAMA_EMBEDDING_BATCH_SIZE must be greater than 0."
        )


# ============================================================
# CREATE OLLAMA CLIENT
# ============================================================

def get_ollama_client():

    validate_config()

    return ollama.Client(
        host=OLLAMA_HOST
    )


# ============================================================
# TEST OLLAMA CONNECTION
# ============================================================

def test_ollama_connection() -> None:

    print("=" * 70)
    print("TERRAGNI OLLAMA EMBEDDING TEST")
    print("=" * 70)

    print(
        f"Ollama host  : {OLLAMA_HOST}"
    )

    print(
        f"Model        : {OLLAMA_EMBEDDING_MODEL}"
    )

    print("-" * 70)

    client = get_ollama_client()

    test_text = (
        "Our affluent banking customers are happy "
        "but not engaged. What is driving the gap?"
    )

    print(
        "Generating local embedding..."
    )

    response = client.embed(
        model=OLLAMA_EMBEDDING_MODEL,
        input=test_text
    )

    embeddings = response["embeddings"]

    if not embeddings:
        raise RuntimeError(
            "Ollama returned no embeddings."
        )

    embedding = embeddings[0]

    print(
        f"Embedding dimensions : {len(embedding)}"
    )

    print(
        f"First 5 values       : {embedding[:5]}"
    )

    print("-" * 70)
    print("OLLAMA EMBEDDING API OK")
    print("=" * 70)


# ============================================================
# FETCH DOCUMENT CHUNKS
# ============================================================

def fetch_chunks(
    connection
) -> List[Tuple[int, str]]:

    sql = """
        SELECT
            CHUNK_ID,
            CHUNK_TEXT
        FROM DOCUMENT_CHUNK
        ORDER BY CHUNK_ID
    """

    rows: List[Tuple[int, str]] = []

    with connection.cursor() as cursor:

        cursor.execute(sql)

        for chunk_id, chunk_text in cursor:

            if chunk_text is None:
                continue

            if hasattr(chunk_text, "read"):
                chunk_text = chunk_text.read()

            if chunk_text is None:
                continue

            chunk_text = str(chunk_text).strip()

            if not chunk_text:
                continue

            rows.append(
                (
                    int(chunk_id),
                    chunk_text
                )
            )

    return rows


# ============================================================
# FETCH EXISTING EMBEDDINGS
# ============================================================

def fetch_existing_chunk_ids(
    connection
) -> set[int]:

    sql = """
        SELECT CHUNK_ID
        FROM DOCUMENT_CHUNK_EMBEDDING
        WHERE MODEL_NAME = :model_name
    """

    existing_ids: set[int] = set()

    with connection.cursor() as cursor:

        cursor.execute(
            sql,
            model_name=OLLAMA_EMBEDDING_MODEL
        )

        for row in cursor:
            existing_ids.add(
                int(row[0])
            )

    return existing_ids


# ============================================================
# CREATE EMBEDDINGS
# ============================================================

def create_embeddings(
    client,
    texts: List[str]
) -> List[List[float]]:

    if not texts:
        return []

    response = client.embed(
        model=OLLAMA_EMBEDDING_MODEL,
        input=texts
    )

    embeddings = response["embeddings"]

    if len(embeddings) != len(texts):

        raise RuntimeError(
            "Ollama returned an unexpected number "
            "of embeddings. "
            f"Expected {len(texts)}, "
            f"received {len(embeddings)}."
        )

    return embeddings


# ============================================================
# STORE EMBEDDINGS
# ============================================================

def insert_embeddings(
    connection,
    rows: List[Tuple[int, List[float]]]
) -> None:

    if not rows:
        return

    sql = """
        INSERT INTO DOCUMENT_CHUNK_EMBEDDING (
            CHUNK_ID,
            MODEL_NAME,
            DIMENSIONS,
            EMBEDDING_JSON
        )
        VALUES (
            :chunk_id,
            :model_name,
            :dimensions,
            :embedding_json
        )
    """

    data = []

    for chunk_id, embedding in rows:

        embedding_json = json.dumps(
            embedding,
            separators=(",", ":")
        )

        data.append(
            {
                "chunk_id": chunk_id,
                "model_name": OLLAMA_EMBEDDING_MODEL,
                "dimensions": len(embedding),
                "embedding_json": embedding_json
            }
        )

    with connection.cursor() as cursor:

        cursor.executemany(
            sql,
            data
        )

    connection.commit()


# ============================================================
# GENERATE ALL MISSING EMBEDDINGS
# ============================================================

def generate_all_embeddings() -> None:

    print("=" * 70)
    print("TERRAGNI LOCAL EMBEDDING GENERATOR")
    print("=" * 70)

    print(
        f"Model       : {OLLAMA_EMBEDDING_MODEL}"
    )

    print(
        f"Ollama host : {OLLAMA_HOST}"
    )

    print(
        f"Batch size  : {BATCH_SIZE}"
    )

    print("-" * 70)

    validate_config()

    client = get_ollama_client()

    # --------------------------------------------------------
    # Existing Oracle connection
    # --------------------------------------------------------

    from backend.database.connection import get_connection

    connection = None

    try:

        print(
            "Connecting to Oracle..."
        )

        connection = get_connection()

        print(
            "Oracle connection established."
        )

        print("-" * 70)

        # ----------------------------------------------------
        # Read chunks
        # ----------------------------------------------------

        print(
            "Reading DOCUMENT_CHUNK..."
        )

        chunks = fetch_chunks(
            connection
        )

        print(
            f"Chunks found       : {len(chunks)}"
        )

        if not chunks:

            print(
                "No document chunks found."
            )

            return

        # ----------------------------------------------------
        # Existing embeddings
        # ----------------------------------------------------

        print(
            "Checking existing embeddings..."
        )

        existing_ids = fetch_existing_chunk_ids(
            connection
        )

        print(
            f"Existing embeddings: {len(existing_ids)}"
        )

        # ----------------------------------------------------
        # Only process missing embeddings
        # ----------------------------------------------------

        pending_chunks = [
            (chunk_id, chunk_text)
            for chunk_id, chunk_text in chunks
            if chunk_id not in existing_ids
        ]

        print(
            f"Pending embeddings : {len(pending_chunks)}"
        )

        print("-" * 70)

        if not pending_chunks:

            print(
                "All chunks already have embeddings "
                f"for model '{OLLAMA_EMBEDDING_MODEL}'."
            )

            return

        total_pending = len(
            pending_chunks
        )

        total_inserted = 0

        # ----------------------------------------------------
        # Process batches
        # ----------------------------------------------------

        for batch_start in range(
            0,
            total_pending,
            BATCH_SIZE
        ):

            batch = pending_chunks[
                batch_start:
                batch_start + BATCH_SIZE
            ]

            batch_number = (
                batch_start // BATCH_SIZE
            ) + 1

            total_batches = (
                total_pending + BATCH_SIZE - 1
            ) // BATCH_SIZE

            print(
                f"Batch {batch_number}/{total_batches}"
            )

            print(
                f"  Chunks: "
                f"{batch_start + 1}-"
                f"{batch_start + len(batch)} "
                f"of {total_pending}"
            )

            texts = [
                chunk_text
                for _, chunk_text in batch
            ]

            # ------------------------------------------------
            # Local embedding
            # ------------------------------------------------

            print(
                "  Generating local embeddings..."
            )

            embeddings = create_embeddings(
                client,
                texts
            )

            # ------------------------------------------------
            # Pair chunk IDs with embeddings
            # ------------------------------------------------

            embedding_rows = [
                (
                    batch[index][0],
                    embeddings[index]
                )
                for index in range(
                    len(batch)
                )
            ]

            # ------------------------------------------------
            # Store in Oracle
            # ------------------------------------------------

            print(
                "  Storing embeddings in Oracle..."
            )

            insert_embeddings(
                connection,
                embedding_rows
            )

            batch_inserted = len(
                embedding_rows
            )

            total_inserted += batch_inserted

            print(
                f"  Stored this batch : "
                f"{batch_inserted}"
            )

            print(
                f"  Total stored      : "
                f"{total_inserted}/{total_pending}"
            )

            print()

        # ----------------------------------------------------
        # Final verification
        # ----------------------------------------------------

        print("=" * 70)
        print("LOCAL EMBEDDING GENERATION COMPLETE")
        print("=" * 70)

        print(
            f"Model used         : "
            f"{OLLAMA_EMBEDDING_MODEL}"
        )

        print(
            f"Chunks in source   : "
            f"{len(chunks)}"
        )

        print(
            f"Already existed    : "
            f"{len(existing_ids)}"
        )

        print(
            f"New embeddings     : "
            f"{total_inserted}"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    MIN(DIMENSIONS),
                    MAX(DIMENSIONS)
                FROM DOCUMENT_CHUNK_EMBEDDING
                WHERE MODEL_NAME = :model_name
                """,
                model_name=OLLAMA_EMBEDDING_MODEL
            )

            count, min_dimensions, max_dimensions = (
                cursor.fetchone()
            )

        print(
            f"Oracle embeddings  : {count}"
        )

        print(
            f"Dimensions         : "
            f"{min_dimensions} - {max_dimensions}"
        )

        print("=" * 70)

    finally:

        if connection is not None:

            connection.close()

            print(
                "Oracle connection closed."
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    generate_all_embeddings()