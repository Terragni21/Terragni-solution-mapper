"""
Remove the OLD report data from the local Oracle database, so the
knowledge base can be rebuilt from the clean reports only.

    python -m backend.scripts.reset_knowledge

Deletes (from Oracle only - your report FILES are not touched):
  - documents, their sections and text chunks
  - the AI search data (embeddings)
  - case studies and their links, extraction staging
  - challenges and outcomes (they are re-created from the clean reports)

Keeps: Terragni's offerings, frameworks and industries.

It also deletes the processed JSON copies in backend/data1/processed,
because they contain the original report text.

You must type DELETE to confirm. This cannot be undone, so make sure you
still have the original reports stored safely elsewhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.connection import get_connection  # noqa: E402

# Child tables first (foreign keys).
TABLES = [
    "DOCUMENT_CHUNK_EMBEDDING",
    "CASE_STUDY_EVIDENCE",
    "CASE_STUDY_INDUSTRY",
    "CASE_STUDY_OFFERING",
    "CASE_STUDY_FRAMEWORK",
    "CASE_STUDY_CHALLENGE",
    "CASE_STUDY_OUTCOME",
    "CASE_STUDY",
    "KNOWLEDGE_EXTRACTION_STAGING",
    "DOCUMENT_CHUNK",
    "DOCUMENT_SECTION",
    "DOCUMENT",
    "CHALLENGE",
    "OUTCOME",
]

PROCESSED_DIR = PROJECT_ROOT / "backend" / "data1" / "processed"


def count(cursor, table: str):
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except Exception:
        return None


def main() -> None:
    connection = get_connection()
    try:
        cursor = connection.cursor()
        print("Rows that will be deleted:")
        for table in TABLES:
            n = count(cursor, table)
            print(f"  {table:<30} {'(missing)' if n is None else n}")
        json_files = list(PROCESSED_DIR.rglob("*.json")) if PROCESSED_DIR.exists() else []
        print(f"  processed JSON files           {len(json_files)}")
        print()

        answer = input("Type DELETE to remove this data: ").strip()
        if answer != "DELETE":
            print("Cancelled. Nothing was deleted.")
            return

        for table in TABLES:
            if count(cursor, table) is None:
                continue
            cursor.execute(f"DELETE FROM {table}")
            print(f"  cleared {table}")
        connection.commit()

        for path in json_files:
            path.unlink()
        print(f"  deleted {len(json_files)} processed JSON files")
        print("Done. The knowledge base is empty and ready for the clean reports.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
