import os
import psycopg2


def get_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing. Configure PostgreSQL "
            "in the Render environment."
        )

    sslmode = os.getenv("DATABASE_SSLMODE", "require").strip()

    return psycopg2.connect(
        database_url,
        sslmode=sslmode or "require",
        connect_timeout=10,
    )