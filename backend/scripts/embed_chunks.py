"""
Create the AI search data (embeddings) for every text chunk in Oracle
that does not have one yet. Runs on this computer - no Ollama needed.

    python -m backend.scripts.embed_chunks

It uses the SAME model the website uses for visitors' questions
(FASTEMBED_MODEL, default nomic-ai/nomic-embed-text-v1.5-Q) and stores
the vectors under DB_EMBEDDING_MODEL (default "nomic-embed-text").
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import oracledb  # noqa: E402

from backend.database.connection import get_connection  # noqa: E402
from backend.retrieval.semantic_search import (  # noqa: E402
    DB_EMBEDDING_MODEL,
    FASTEMBED_MODEL,
    _get_fastembed_model,
)

BATCH = 16


def main() -> None:
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT c.CHUNK_ID, c.CHUNK_TEXT
            FROM DOCUMENT_CHUNK c
            WHERE NOT EXISTS (
                SELECT 1 FROM DOCUMENT_CHUNK_EMBEDDING e
                WHERE e.CHUNK_ID = c.CHUNK_ID AND e.MODEL_NAME = :model_name
            )
            ORDER BY c.CHUNK_ID
            """,
            {"model_name": DB_EMBEDDING_MODEL},
        )
        rows = [(int(cid), str(text or "").strip()) for cid, text in cursor.fetchall()]
        rows = [(cid, text) for cid, text in rows if text]

        print(f"Model            : {FASTEMBED_MODEL}")
        print(f"Chunks to embed  : {len(rows)}")
        if not rows:
            print("Nothing to do - every chunk already has embeddings.")
            return

        model = _get_fastembed_model()
        started = time.time()
        done = 0

        for start in range(0, len(rows), BATCH):
            batch = rows[start:start + BATCH]
            vectors = list(model.embed([text for _, text in batch], batch_size=BATCH))
            data = [
                {
                    "chunk_id": cid,
                    "model_name": DB_EMBEDDING_MODEL,
                    "dimensions": len(vector),
                    "embedding_json": json.dumps([round(float(x), 7) for x in vector], separators=(",", ":")),
                }
                for (cid, _), vector in zip(batch, vectors)
            ]
            cursor.setinputsizes(embedding_json=oracledb.DB_TYPE_CLOB)
            cursor.executemany(
                """
                INSERT INTO DOCUMENT_CHUNK_EMBEDDING
                    (CHUNK_ID, MODEL_NAME, DIMENSIONS, EMBEDDING_JSON)
                VALUES (:chunk_id, :model_name, :dimensions, :embedding_json)
                """,
                data,
            )
            connection.commit()
            done += len(batch)
            print(f"  embedded {done}/{len(rows)}", end="\r")

        print(f"\nDone in {time.time() - started:.0f}s.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
