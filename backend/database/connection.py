from __future__ import annotations

import os
import socket
from pathlib import Path

import oracledb
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BACKEND_DIR / ".env")


# ============================================================
# ORACLE CONFIGURATION
# ============================================================

ORACLE_HOST = os.getenv(
    "ORACLE_HOST",
    "Terragni-10"
).strip()

ORACLE_HOST_IP = os.getenv(
    "ORACLE_HOST_IP",
    ""
).strip()

ORACLE_PORT = int(
    os.getenv(
        "ORACLE_PORT",
        "1521"
    ).strip()
)

ORACLE_USER = os.getenv(
    "ORACLE_USER",
    ""
).strip()

ORACLE_PASSWORD = os.getenv(
    "ORACLE_PASSWORD",
    ""
).strip()

ORACLE_SERVICE_NAME = os.getenv(
    "ORACLE_SERVICE_NAME",
    ""
).strip()

ORACLE_SID = os.getenv(
    "ORACLE_SID",
    ""
).strip()


# ============================================================
# VALIDATE CONFIGURATION
# ============================================================

def validate_config() -> None:

    missing = []

    if not ORACLE_USER:
        missing.append("ORACLE_USER")

    if not ORACLE_PASSWORD:
        missing.append("ORACLE_PASSWORD")

    if not ORACLE_HOST:
        missing.append("ORACLE_HOST")

    if not ORACLE_SERVICE_NAME and not ORACLE_SID:
        missing.append(
            "ORACLE_SERVICE_NAME or ORACLE_SID"
        )

    if missing:
        raise RuntimeError(
            "Missing Oracle configuration: "
            + ", ".join(missing)
        )


# ============================================================
# RESOLVE ORACLE HOST
# ============================================================

def resolve_oracle_host() -> str:
    """
    Resolve Terragni-10 to an IP address.

    Primary:
        Windows hostname resolution.

    Fallback:
        ORACLE_HOST_IP from .env.

    The application still uses Terragni-10 as the configured
    Oracle server name.
    """

    # --------------------------------------------------------
    # 1. Try normal hostname resolution
    # --------------------------------------------------------

    try:

        resolved_ip = socket.gethostbyname(
            ORACLE_HOST
        )

        print(
            f"Oracle host resolved: "
            f"{ORACLE_HOST} -> {resolved_ip}"
        )

        return resolved_ip

    except socket.gaierror:

        print(
            f"WARNING: Windows could not resolve "
            f"'{ORACLE_HOST}'."
        )

    # --------------------------------------------------------
    # 2. Use explicitly configured fallback IP
    # --------------------------------------------------------

    if ORACLE_HOST_IP:

        print(
            f"Using Oracle fallback IP: "
            f"{ORACLE_HOST_IP}"
        )

        return ORACLE_HOST_IP

    # --------------------------------------------------------
    # 3. Nothing worked
    # --------------------------------------------------------

    raise RuntimeError(
        f"Could not resolve Oracle host "
        f"'{ORACLE_HOST}' and no "
        f"ORACLE_HOST_IP fallback was configured."
    )


# ============================================================
# CREATE CONNECTION
# ============================================================

def get_connection():
    """Return a PostgreSQL connection when DATABASE_URL is defined, otherwise Oracle.
    This mirrors the historic behaviour while making Render work out‑of‑the‑box.
    """
    if os.getenv("DATABASE_URL"):
        # PostgreSQL via psycopg2 (the pooler URL works with sslmode=require)
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
        return conn
    else:
        # Fall back to original Oracle connection logic
        validate_config()
        resolved_host = resolve_oracle_host()
        if ORACLE_SERVICE_NAME:
            dsn = oracledb.makedsn(
                resolved_host,
                ORACLE_PORT,
                service_name=ORACLE_SERVICE_NAME,
            )
        else:
            dsn = oracledb.makedsn(
                resolved_host,
                ORACLE_PORT,
                sid=ORACLE_SID,
            )
        connection = oracledb.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=dsn,
        )
        return connection


# ============================================================
# TEST CONNECTION
# ============================================================

def test_connection() -> None:

    print("=" * 60)
    print("TERRAGNI ORACLE CONNECTION TEST")
    print("=" * 60)

    print(
        f"Configured host : {ORACLE_HOST}"
    )

    if ORACLE_HOST_IP:

        print(
            f"Fallback IP     : {ORACLE_HOST_IP}"
        )

    print(
        f"Port            : {ORACLE_PORT}"
    )

    if ORACLE_SERVICE_NAME:

        print(
            f"Service name    : "
            f"{ORACLE_SERVICE_NAME}"
        )

    else:

        print(
            f"SID             : {ORACLE_SID}"
        )

    print(
        f"User            : {ORACLE_USER}"
    )

    print("-" * 60)

    connection = None

    try:

        connection = get_connection()

        print(
            "ORACLE CONNECTION OK"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    SYS_CONTEXT(
                        'USERENV',
                        'DB_NAME'
                    ),
                    SYS_CONTEXT(
                        'USERENV',
                        'SERVICE_NAME'
                    ),
                    SYS_CONTEXT(
                        'USERENV',
                        'CURRENT_SCHEMA'
                    )
                FROM dual
                """
            )

            row = cursor.fetchone()

            print(
                f"Database       : {row[0]}"
            )

            print(
                f"Service        : {row[1]}"
            )

            print(
                f"Current schema : {row[2]}"
            )

    finally:

        if connection is not None:
            connection.close()

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    test_connection()