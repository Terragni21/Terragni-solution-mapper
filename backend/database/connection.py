
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BACKEND_DIR / ".env")


# ============================================================
# POSTGRESQL CONFIGURATION
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Render PostgreSQL generally requires SSL.
# Local PostgreSQL can use its normal connection settings.
RENDER_ENV = os.getenv("RENDER", "").strip().lower() == "true"

DATABASE_SSLMODE = os.getenv(
    "DATABASE_SSLMODE",
    "require" if RENDER_ENV else "",
).strip()


# ============================================================
# VALIDATE CONFIGURATION
# ============================================================

def validate_config() -> None:
    """Validate the PostgreSQL connection configuration."""

    if not DATABASE_URL:
        raise RuntimeError(
            "Missing PostgreSQL configuration: DATABASE_URL. "
            "Set it in your .env file or deployment environment."
        )


# ============================================================
# CREATE CONNECTION
# ============================================================

def get_connection():
    """Return an active PostgreSQL database connection."""

    validate_config()

    connection_options = {}

    if DATABASE_SSLMODE:
        connection_options["sslmode"] = DATABASE_SSLMODE

    try:
        connection = psycopg2.connect(
            DATABASE_URL,
            **connection_options,
        )
        return connection

    except psycopg2.Error as exc:
        # Do not log DATABASE_URL because it may contain credentials.
        raise RuntimeError(
            "Could not connect to PostgreSQL. "
            "Check DATABASE_URL, database availability, "
            "network access, and SSL settings."
        ) from exc


# ============================================================
# TEST CONNECTION
# ============================================================

def test_connection() -> None:
    """Connect to PostgreSQL and display basic connection details."""

    print("=" * 60)
    print("POSTGRESQL CONNECTION TEST")
    print("=" * 60)

    connection = None

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    inet_server_addr()::text,
                    inet_server_port()
                """
            )

            row = cursor.fetchone()

        print("POSTGRESQL CONNECTION OK")
        print(f"Database       : {row[0]}")
        print(f"User           : {row[1]}")
        print(f"Server address : {row[2] or 'Not available'}")
        print(f"Server port    : {row[3] or 'Not available'}")

    except Exception as exc:
        print(f"POSTGRESQL CONNECTION FAILED: {exc}")
        raise

    finally:
        if connection is not None:
            connection.close()

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    test_connection()
