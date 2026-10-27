"""
Quick test of the local Oracle database.

    python -m backend.database.test_connection      (from the project folder)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.connection import get_connection  # noqa: E402

TABLES = (
    "DOCUMENT",
    "DOCUMENT_CHUNK",
    "DOCUMENT_CHUNK_EMBEDDING",
    "CASE_STUDY",
    "CASE_STUDY_EVIDENCE",
    "OFFERING",
    "FRAMEWORK",
)


def main():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT USER, SYS_CONTEXT('USERENV', 'DB_NAME') FROM dual"
        )
        user, database = cursor.fetchone()
        print("Oracle connection successful")
        print(f"USER     : {user}")
        print(f"DATABASE : {database}")
        print("-" * 50)

        for table in TABLES:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"{table:<26}: {cursor.fetchone()[0]} rows")
            except Exception as exc:
                print(f"{table:<26}: MISSING ({str(exc).splitlines()[0]})")

        try:
            cursor.execute(
                "SELECT MODEL_NAME, COUNT(*) FROM DOCUMENT_CHUNK_EMBEDDING "
                "GROUP BY MODEL_NAME"
            )
            print("-" * 50)
            for name, count in cursor.fetchall():
                print(f"embeddings '{name}': {count}")
        except Exception:
            pass
    finally:
        connection.close()


if __name__ == "__main__":
    main()
