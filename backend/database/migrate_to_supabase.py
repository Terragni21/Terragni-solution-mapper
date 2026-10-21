"""
One-time migration: Oracle export JSON  ->  Supabase PostgreSQL.

Run it ONCE from your own computer (not on Render), from the project root:

    python -m backend.database.migrate_to_supabase            # create + load
    python -m backend.database.migrate_to_supabase --reset    # drop + recreate + load
    python -m backend.database.migrate_to_supabase --check    # only print counts

It reads:
    backend/data/oracle_export.json             (all knowledge tables)
    backend/data/oracle_embeddings_export.json  (803 chunk embeddings)

and writes every row into the database in DATABASE_URL (backend/.env).
Re-running is safe: existing rows are updated, nothing is duplicated.

After it finishes, Render no longer needs either JSON file - the website
reads everything (including the embeddings) from Supabase.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from psycopg2.extras import execute_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.connection import get_connection  # noqa: E402

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
EXPORT_FILE = BACKEND_DIR / "data" / "oracle_export.json"
EMBEDDINGS_FILE = BACKEND_DIR / "data" / "oracle_embeddings_export.json"

# Load order matters because of foreign keys.
# table -> primary-key columns (used for ON CONFLICT)
TABLES: list[tuple[str, tuple[str, ...]]] = [
    ("document", ("document_id",)),
    ("document_section", ("section_id",)),
    ("document_chunk", ("chunk_id",)),
    ("industry", ("industry_id",)),
    ("offering", ("offering_id",)),
    ("framework", ("framework_id",)),
    ("challenge", ("challenge_id",)),
    ("outcome", ("outcome_id",)),
    ("case_study", ("case_study_id",)),
    ("case_study_industry", ("case_study_id", "industry_id")),
    ("case_study_offering", ("case_study_id", "offering_id")),
    ("case_study_framework", ("case_study_id", "framework_id")),
    ("case_study_challenge", ("case_study_id", "challenge_id")),
    ("case_study_outcome", ("case_study_id", "outcome_id")),
    ("case_study_evidence", ("case_study_id", "chunk_id")),
    ("knowledge_extraction_staging", ("staging_id",)),
]

# Tables whose identity sequence must be moved past the imported IDs.
IDENTITY_COLUMNS = {
    "document": "document_id",
    "document_section": "section_id",
    "document_chunk": "chunk_id",
    "document_chunk_embedding": "embedding_id",
    "industry": "industry_id",
    "offering": "offering_id",
    "framework": "framework_id",
    "challenge": "challenge_id",
    "outcome": "outcome_id",
    "case_study": "case_study_id",
    "knowledge_extraction_staging": "staging_id",
    "user_queries": "id",
}

DROP_ORDER = [
    "document_chunk_embedding",
    "case_study_evidence",
    "case_study_outcome",
    "case_study_challenge",
    "case_study_framework",
    "case_study_offering",
    "case_study_industry",
    "case_study",
    "outcome",
    "challenge",
    "framework",
    "offering",
    "industry",
    "knowledge_extraction_staging",
    "document_chunk",
    "document_section",
    "document",
]


def _table_columns(cursor, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row[0] for row in cursor.fetchall()]


def _warn_about_uppercase_tables(cursor) -> None:
    """Tables created as "DOCUMENT" (quoted upper case) are invisible to the code."""
    cursor.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name <> lower(table_name)
        """
    )
    upper = [row[0] for row in cursor.fetchall()]
    if upper:
        print("WARNING: these tables have UPPER-CASE quoted names and will be")
        print("         ignored by the application:", ", ".join(upper))
        print("         Drop them in Supabase (Table editor) once this migration")
        print("         has loaded the lower-case tables.")


def _ensure_unique_key(cursor, table: str, key: tuple[str, ...]) -> None:
    """
    Make sure `key` is unique on `table`, so ON CONFLICT (key) works.

    Tables that already existed before this script (created by hand or by
    an earlier attempt) may lack the primary key / unique rule that
    schema.sql defines - CREATE TABLE IF NOT EXISTS does not add it.
    Duplicate rows are removed first (the newest copy is kept).
    """
    columns = set(_table_columns(cursor, table))
    if not columns or not set(key) <= columns:
        return
    match = " AND ".join(f"a.{c} = b.{c}" for c in key)
    cursor.execute(
        f"DELETE FROM {table} a USING {table} b "
        f"WHERE a.ctid < b.ctid AND {match}"
    )
    if cursor.rowcount:
        print(f"  note: {table}: removed {cursor.rowcount} duplicate rows")
    index_name = f"ux_{table}_{'_'.join(key)}"[:63]
    cursor.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
        f"ON {table} ({', '.join(key)})"
    )


def _load_rows(cursor, table: str, pk: tuple[str, ...], rows: list[dict]) -> int:
    _ensure_unique_key(cursor, table, pk)

    if not rows:
        return 0

    db_columns = set(_table_columns(cursor, table))
    columns = [c.lower() for c in rows[0].keys() if c.lower() in db_columns]
    missing = [c for c in rows[0].keys() if c.lower() not in db_columns]
    if missing:
        print(f"  note: {table}: ignoring columns not in schema: {missing}")

    values = [
        tuple(row.get(col.upper(), row.get(col)) for col in columns)
        for row in rows
    ]

    update_cols = [c for c in columns if c not in pk]
    if update_cols:
        conflict = (
            f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        )
    else:
        conflict = f"ON CONFLICT ({', '.join(pk)}) DO NOTHING"

    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"{conflict}"
    )
    # De-duplicate on the primary key (Oracle allowed duplicates in a few
    # link tables) - Postgres refuses the same key twice in one statement.
    pk_index = [columns.index(c) for c in pk if c in columns]
    unique: dict[tuple, tuple] = {}
    for value in values:
        unique[tuple(value[i] for i in pk_index)] = value
    execute_values(cursor, sql, list(unique.values()), page_size=500)
    return len(unique)


def _load_embeddings(cursor) -> int:
    if not EMBEDDINGS_FILE.exists():
        print(f"  skip: {EMBEDDINGS_FILE.name} not found")
        return 0

    _ensure_unique_key(cursor, "document_chunk_embedding", ("chunk_id", "model_name"))

    raw = json.loads(EMBEDDINGS_FILE.read_text(encoding="utf-8"))
    cursor.execute("SELECT chunk_id FROM document_chunk")
    known_chunks = {int(row[0]) for row in cursor.fetchall()}

    values = []
    skipped = 0
    for item in raw:
        chunk_id = int(item["chunk_id"])
        if chunk_id not in known_chunks:
            skipped += 1
            continue
        embedding = item["embedding_json"]
        if not isinstance(embedding, str):
            embedding = json.dumps(embedding, separators=(",", ":"))
        values.append((
            chunk_id,
            str(item.get("model_name") or "nomic-embed-text"),
            int(item.get("dimensions") or len(json.loads(embedding))),
            embedding,
        ))

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
    if skipped:
        print(f"  note: {skipped} embeddings skipped (chunk not in document_chunk)")
    return len(values)


def _reset_identity_sequences(cursor) -> None:
    for table, column in IDENTITY_COLUMNS.items():
        if column not in _table_columns(cursor, table):
            continue
        cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", (table, column))
        sequence = cursor.fetchone()[0]
        if not sequence:
            # Column exists but is a plain integer (table made by hand):
            # nothing to move forward.
            continue
        cursor.execute(
            f"""
            SELECT setval(
                %s,
                GREATEST((SELECT COALESCE(MAX({column}), 0) FROM {table}), 1),
                (SELECT COUNT(*) > 0 FROM {table})
            )
            """,
            (sequence,),
        )


def print_counts(cursor) -> None:
    print("-" * 60)
    for table in [t for t, _ in TABLES] + ["document_chunk_embedding", "user_leads", "user_queries"]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:<32} {cursor.fetchone()[0]:>6}")
        except Exception as exc:  # table missing
            cursor.connection.rollback()
            print(f"  {table:<32}  MISSING ({type(exc).__name__})")
    print("-" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--reset", action="store_true",
                        help="drop the knowledge tables first (leads are kept)")
    parser.add_argument("--check", action="store_true",
                        help="only print row counts")
    args = parser.parse_args()

    connection = get_connection()
    try:
        cursor = connection.cursor()

        if args.check:
            print_counts(cursor)
            return

        _warn_about_uppercase_tables(cursor)

        if args.reset:
            print("Dropping knowledge tables ...")
            for table in DROP_ORDER:
                cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

        print("Creating schema ...")
        cursor.execute(SCHEMA_FILE.read_text(encoding="utf-8"))

        if not EXPORT_FILE.exists():
            raise SystemExit(f"Export file not found: {EXPORT_FILE}")

        export = json.loads(EXPORT_FILE.read_text(encoding="utf-8"))
        export = {key.lower(): value for key, value in export.items()}

        for table, pk in TABLES:
            rows = export.get(table, [])
            count = _load_rows(cursor, table, pk, rows)
            print(f"  {table:<32} {count:>6} rows")

        count = _load_embeddings(cursor)
        print(f"  {'document_chunk_embedding':<32} {count:>6} rows")

        _reset_identity_sequences(cursor)
        connection.commit()
        print("Migration committed.")
        print_counts(cursor)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
