"""
Re-create the chunk embeddings with a small model that fits Render's
free / 512 MB instance.

Run ONCE on your own computer, from the project folder:

    python -m backend.scripts.reembed_chunks

What it does:
  1. Reads all rows of document_chunk from Supabase.
  2. Embeds them with FastEmbed (default BAAI/bge-small-en-v1.5, ~67 MB).
  3. Saves them in document_chunk_embedding with
     model_name = 'bge-small-en-v1.5' (the old nomic rows are kept).
  4. Prints a short calibration report: similarity scores for banking
     questions vs. off-topic questions, so the match thresholds can be
     checked.

Safe to run again - existing rows for this model are updated.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

from backend.database.connection import get_connection  # noqa: E402

MODEL = os.getenv("REEMBED_MODEL", "BAAI/bge-small-en-v1.5")
MODEL_NAME = os.getenv("REEMBED_MODEL_NAME", "bge-small-en-v1.5")
BATCH = 32

ON_TOPIC = [
    "Our affluent banking customers are happy but not engaged. What is driving that gap?",
    "Customers abandon our mobile banking app during onboarding.",
    "How can we increase wallet share among premium bank customers?",
    "Relationship managers are not able to deepen engagement with clients.",
    "Life insurance policy holders are not renewing their premiums.",
]
OFF_TOPIC = [
    "What is the best recipe for chocolate cake?",
    "Who won the football world cup?",
    "How do I fix a flat bicycle tyre?",
]


def _load_model():
    from fastembed import TextEmbedding

    cache_dir = os.getenv(
        "FASTEMBED_CACHE_DIR",
        str(PROJECT_ROOT / "backend" / "model_cache"),
    )
    # A Linux path from Render in a Windows .env is useless locally.
    if os.name == "nt" and cache_dir.startswith("/"):
        cache_dir = str(PROJECT_ROOT / "backend" / "model_cache")
    print(f"Loading {MODEL} (first time downloads it) ...")
    return TextEmbedding(model_name=MODEL, cache_dir=cache_dir)


def _allow_several_models(cursor) -> None:
    """
    The table may have been created with PRIMARY KEY (chunk_id), which allows
    only ONE embedding per chunk. Replace it with a unique (chunk_id,
    model_name) rule so the old nomic vectors and the new ones can coexist.
    """
    cursor.execute(
        """
        SELECT con.conname, array_agg(att.attname ORDER BY att.attname)
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_attribute att
          ON att.attrelid = rel.oid AND att.attnum = ANY (con.conkey)
        WHERE rel.relname = 'document_chunk_embedding'
          AND con.contype IN ('p', 'u')
        GROUP BY con.conname
        """
    )
    for name, columns in cursor.fetchall():
        if list(columns) == ["chunk_id"]:
            print(f"Removing one-embedding-per-chunk rule ({name}) ...")
            cursor.execute(
                f'ALTER TABLE document_chunk_embedding DROP CONSTRAINT "{name}"'
            )
    # Unique indexes on chunk_id alone (not constraints) block it too.
    cursor.execute(
        """
        SELECT i.relname
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        WHERE t.relname = 'document_chunk_embedding'
          AND x.indisunique AND NOT x.indisprimary
          AND x.indnatts = 1
          AND (SELECT attname FROM pg_attribute
               WHERE attrelid = t.oid AND attnum = x.indkey[0]) = 'chunk_id'
        """
    )
    for (index_name,) in cursor.fetchall():
        print(f"Removing unique index {index_name} ...")
        cursor.execute(f'DROP INDEX "{index_name}"')
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_document_chunk_embedding_chunk_id_model_name "
        "ON document_chunk_embedding (chunk_id, model_name)"
    )


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def main() -> None:
    model = _load_model()

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT chunk_id, chunk_text FROM document_chunk ORDER BY chunk_id"
        )
        rows = [
            (int(chunk_id), str(text or "").strip())
            for chunk_id, text in cursor.fetchall()
        ]
        rows = [(chunk_id, text) for chunk_id, text in rows if text]
        print(f"Chunks to embed: {len(rows)}")

        # Re-use vectors from a previous run (saves ~2 minutes).
        cache_file = PROJECT_ROOT / "backend" / "model_cache" / f"{MODEL_NAME}_vectors.json"
        cached: dict[str, list[float]] = {}
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
            except ValueError:
                cached = {}
        if cached and all(str(chunk_id) in cached for chunk_id, _ in rows):
            print(f"Using saved vectors from {cache_file.name}")
            vectors = [cached[str(chunk_id)] for chunk_id, _ in rows]
        else:
            started = time.time()
            vectors = []
            for start in range(0, len(rows), BATCH):
                texts = [text for _, text in rows[start:start + BATCH]]
                vectors.extend(v.tolist() for v in model.embed(texts, batch_size=BATCH))
                print(f"  embedded {min(start + BATCH, len(rows))}/{len(rows)}", end="\r")
            print(f"\nEmbedding took {time.time() - started:.0f}s")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({str(c): v for (c, _), v in zip(rows, vectors)}),
                encoding="utf-8",
            )

        _allow_several_models(cursor)

        values = [
            (
                chunk_id,
                MODEL_NAME,
                len(vector),
                json.dumps([round(x, 7) for x in vector], separators=(",", ":")),
            )
            for (chunk_id, _), vector in zip(rows, vectors)
        ]
        execute_values(
            cursor,
            """
            INSERT INTO document_chunk_embedding
                (chunk_id, model_name, dimensions, embedding_json)
            VALUES %s
            ON CONFLICT (chunk_id, model_name) DO UPDATE SET
                dimensions = EXCLUDED.dimensions,
                embedding_json = EXCLUDED.embedding_json
            """,
            values,
            page_size=100,
        )
        connection.commit()
        print(f"Saved {len(values)} embeddings as model_name='{MODEL_NAME}'.")

        cursor.execute(
            "SELECT model_name, COUNT(*) FROM document_chunk_embedding "
            "GROUP BY model_name ORDER BY model_name"
        )
        for name, count in cursor.fetchall():
            print(f"  {name:<24} {count}")
    finally:
        connection.close()

    # ---------------- calibration report ----------------
    matrix = _normalise(np.asarray(vectors, dtype=np.float32))

    def best_scores(question: str) -> list[float]:
        query = _normalise(np.asarray([next(iter(model.embed([question])))], dtype=np.float32))[0]
        scores = np.sort(matrix @ query)[::-1]
        return [float(scores[0]), float(scores[min(11, len(scores) - 1)])]

    print()
    print("=" * 70)
    print("CALIBRATION  (best match / 12th match)")
    print("=" * 70)
    on = []
    for question in ON_TOPIC:
        top, twelfth = best_scores(question)
        on.append(top)
        print(f"  banking  {top:.2f} / {twelfth:.2f}   {question[:50]}")
    off = []
    for question in OFF_TOPIC:
        top, twelfth = best_scores(question)
        off.append(top)
        print(f"  other    {top:.2f} / {twelfth:.2f}   {question[:50]}")
    print("-" * 70)
    print(f"  lowest banking best-match : {min(on):.2f}")
    print(f"  highest off-topic match   : {max(off):.2f}")
    print("Send this report to Claude to confirm the thresholds.")


if __name__ == "__main__":
    main()
