"""
Quick Supabase connection test.

    python -m backend.database.test_connection      (from the project root)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.connection import get_connection  # noqa: E402


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, current_database(), version()"
            )
            user, database, version = cursor.fetchone()

            print("PostgreSQL connection successful")
            print(f"USER     : {user}")
            print(f"DATABASE : {database}")
            print(f"VERSION  : {version.split(',')[0]}")

            for table in ("document_chunk", "document_chunk_embedding", "case_study"):
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    print(f"{table:<26}: {cursor.fetchone()[0]} rows")
                except Exception as exc:
                    connection.rollback()
                    print(f"{table:<26}: MISSING - run migrate_to_supabase ({exc.__class__.__name__})")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
