"""
Single PostgreSQL (Supabase) connection point for the whole project.

Every module - the Flask website, retrieval, leads, the knowledge pipeline
and the ingestion scripts - gets its database connection from here.

Configuration (backend/.env locally, Environment tab on Render):

    DATABASE_URL      postgresql://USER:PASSWORD@HOST:PORT/postgres
    DATABASE_SSLMODE  require (default)

On Render use the Supabase *pooler* connection string
(host  aws-0-<region>.pooler.supabase.com, port 6543 or 5432).
The "direct" host db.<project>.supabase.co is IPv6-only and Render cannot
reach it.

ORACLE COMPATIBILITY
--------------------
The older ingestion / knowledge-pipeline scripts were written for Oracle
(named binds like :document_id, SYSTIMESTAMP, NVL, ROWNUM = 1,
cursor.var(int) + RETURNING ... INTO :out_id, execute(sql, name=value)).
Instead of rewriting thousands of lines, the cursor returned by this module
translates those few Oracle idioms to PostgreSQL on the fly. SQL already
written for psycopg2 (%s / %(name)s placeholders) is passed through
untouched.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extensions
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


# ============================================================
# ORACLE -> POSTGRESQL SQL TRANSLATION
# ============================================================

# :name  (but not ::type casts, not inside 'string literals', not 10:30)
_BIND_RE = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")
_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_RETURNING_INTO_RE = re.compile(
    r"RETURNING\s+([A-Za-z_][\w]*)\s+INTO\s+:([A-Za-z_]\w*)",
    re.IGNORECASE,
)
_ROWNUM_RE = re.compile(
    r"\s+(AND|WHERE)\s+ROWNUM\s*(?:=\s*1|<=\s*1|<\s*2)\b",
    re.IGNORECASE,
)


def _uses_pg_placeholders(sql: str) -> bool:
    return "%s" in sql or "%(" in sql


def translate_sql(sql: str) -> str:
    """Translate the Oracle idioms used in this project into PostgreSQL."""
    if _uses_pg_placeholders(sql):
        return sql

    sql = re.sub(r"\bSYSTIMESTAMP\b", "CURRENT_TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bSYSDATE\b", "CURRENT_TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bNVL\s*\(", "COALESCE(", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s+FROM\s+DUAL\b", "", sql, flags=re.IGNORECASE)

    # "... WHERE X = 1 AND ROWNUM = 1"  ->  "... WHERE X = 1 LIMIT 1"
    if _ROWNUM_RE.search(sql):
        def _drop_rownum(match: re.Match) -> str:
            # "WHERE ROWNUM = 1" with no other condition -> drop WHERE too
            return "" if match.group(1).upper() == "AND" else " WHERE TRUE"
        sql = _ROWNUM_RE.sub(_drop_rownum, sql).rstrip().rstrip(";") + "\nLIMIT 1"

    # Escape literal % (e.g. LIKE 'abc%') before adding %(name)s placeholders.
    pieces = []
    last = 0
    for literal in _STRING_RE.finditer(sql):
        code = sql[last:literal.start()]
        pieces.append(_BIND_RE.sub(r"%(\1)s", code.replace("%", "%%")))
        pieces.append(literal.group(0).replace("%", "%%"))
        last = literal.end()
    code = sql[last:]
    pieces.append(_BIND_RE.sub(r"%(\1)s", code.replace("%", "%%")))
    return "".join(pieces)


class OutVar:
    """Stand-in for oracledb's cursor.var(int) used with RETURNING ... INTO."""

    def __init__(self, kind: Any = int):
        self.kind = kind
        self.value: Any = None

    def getvalue(self, pos: int = 0) -> Any:
        return self.value

    def setvalue(self, pos: int, value: Any) -> None:
        self.value = value


class CompatCursor(psycopg2.extensions.cursor):
    """psycopg2 cursor that also accepts the Oracle style used by old scripts."""

    def var(self, kind: Any = int, *args, **kwargs) -> OutVar:  # noqa: D401
        return OutVar(kind)

    def execute(self, query, vars=None, **kwargs):  # type: ignore[override]
        if kwargs:
            merged = dict(vars or {})
            merged.update(kwargs)
            vars = merged

        if not isinstance(query, str):
            return super().execute(query, vars)

        out_vars: dict[str, OutVar] = {}
        if isinstance(vars, dict):
            out_vars = {k: v for k, v in vars.items() if isinstance(v, OutVar)}
            if out_vars:
                vars = {k: v for k, v in vars.items() if k not in out_vars}

        if out_vars:
            # RETURNING ID INTO :out_id  ->  RETURNING ID  (then fetch it)
            query = _RETURNING_INTO_RE.sub(r"RETURNING \1", query)

        if isinstance(vars, dict) and not vars:
            vars = None

        sql = translate_sql(query)
        if vars is None and not _uses_pg_placeholders(query):
            # No parameters: psycopg2 must not interpret %% escapes.
            sql = sql.replace("%%", "%")

        result = super().execute(sql, vars)

        if out_vars:
            row = super().fetchone()
            value = row[0] if row else None
            for out in out_vars.values():
                out.value = value
        return result

    def executemany(self, query, vars_list):  # type: ignore[override]
        if isinstance(query, str):
            query = translate_sql(query)
        return super().executemany(query, vars_list)


# ============================================================
# CONNECTION
# ============================================================

def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing. Add your Supabase pooler connection "
            "string to backend/.env (local) or the Render Environment tab."
        )
    # Some dashboards hand out postgres:// - psycopg2 accepts both, but
    # normalise for clarity.
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    return database_url


def get_connection():
    """
    Open a new PostgreSQL connection.

    The caller is responsible for closing it (use try/finally or `with
    closing(get_connection())`).
    """
    sslmode = (os.getenv("DATABASE_SSLMODE", "require").strip() or "require")

    return psycopg2.connect(
        get_database_url(),
        sslmode=sslmode,
        connect_timeout=int(os.getenv("DATABASE_CONNECT_TIMEOUT", "15")),
        cursor_factory=CompatCursor,
        application_name="terragni-solution-mapper",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
