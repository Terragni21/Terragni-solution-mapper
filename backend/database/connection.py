"""
Single connection point to the LOCAL Oracle database.

Every module (website, retrieval, knowledge pipeline, ingestion) gets its
connection from here. Nothing is sent to any cloud database.

Settings (backend/.env):

    ORACLE_USER=...
    ORACLE_PASSWORD=...
    ORACLE_HOST=localhost          (or the PC/server name)
    ORACLE_HOST_IP=                (optional fallback IP if the name fails)
    ORACLE_PORT=1521
    ORACLE_SID=XE                  (use ORACLE_SERVICE_NAME instead if your
                                    database uses a service name, e.g. XEPDB1)
    ORACLE_CLIENT_LIB_DIR=         (optional: only for Oracle 11g or older -
                                    path to Oracle Instant Client, enables
                                    "thick" mode)

The newer code uses psycopg2-style placeholders (%s and %(name)s); the
cursor returned here converts them to Oracle binds (:1, :name) so the same
SQL works. Oracle-style SQL (:name binds) passes through unchanged.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

# Return CLOB/NCLOB columns as normal Python strings.
oracledb.defaults.fetch_lobs = False

_CLIENT_DIR = os.getenv("ORACLE_CLIENT_LIB_DIR", "").strip()
if _CLIENT_DIR:
    # Thick mode: needed only for Oracle Database 11.2 or older.
    oracledb.init_oracle_client(lib_dir=_CLIENT_DIR)


# ============================================================
# %s / %(name)s  ->  :1 / :name
# ============================================================

_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_NAMED_RE = re.compile(r"%\(([A-Za-z_]\w*)\)s")


def translate_sql(sql: str) -> str:
    """Convert psycopg2 placeholders to Oracle binds (outside string literals)."""
    if "%s" not in sql and "%(" not in sql:
        return sql

    counter = 0

    def convert(code: str) -> str:
        nonlocal counter
        code = _NAMED_RE.sub(r":\1", code)

        def positional(_match: re.Match) -> str:
            nonlocal counter
            counter += 1
            return f":{counter}"

        code = re.sub(r"%s", positional, code)
        return code.replace("%%", "%")

    pieces = []
    last = 0
    for literal in _STRING_RE.finditer(sql):
        pieces.append(convert(sql[last:literal.start()]))
        pieces.append(literal.group(0).replace("%%", "%"))
        last = literal.end()
    pieces.append(convert(sql[last:]))
    return "".join(pieces).rstrip().rstrip(";")


class CompatCursor:
    """Thin wrapper around an oracledb cursor that accepts %s placeholders."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None, **kwargs):
        if isinstance(sql, str):
            sql = translate_sql(sql)
        if kwargs:
            merged = dict(params or {})
            merged.update(kwargs)
            params = merged
        if isinstance(params, tuple):
            params = list(params)
        if params is None or params == {} or params == []:
            return self._cursor.execute(sql)
        return self._cursor.execute(sql, params)

    def executemany(self, sql, rows):
        if isinstance(sql, str):
            sql = translate_sql(sql)
        rows = [list(r) if isinstance(r, tuple) else r for r in rows]
        return self._cursor.executemany(sql, rows)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        # fetchone, fetchall, description, rowcount, var, arraysize, ...
        return getattr(self._cursor, name)


class CompatConnection:
    """oracledb connection whose cursors accept %s placeholders."""

    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *args, **kwargs):
        return CompatCursor(self._connection.cursor(*args, **kwargs))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        try:
            self._connection.close()
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        # commit, rollback, autocommit, ...
        return getattr(self._connection, name)


# ============================================================
# CONNECTION
# ============================================================

def _dsn(host: str) -> str:
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = os.getenv("ORACLE_SERVICE_NAME", "").strip()
    sid = os.getenv("ORACLE_SID", "").strip()
    if service:
        return oracledb.makedsn(host, port, service_name=service)
    if sid:
        return oracledb.makedsn(host, port, sid=sid)
    raise RuntimeError(
        "Set ORACLE_SID or ORACLE_SERVICE_NAME in backend/.env."
    )


def get_connection():
    user = os.getenv("ORACLE_USER", "").strip()
    password = os.getenv("ORACLE_PASSWORD", "")
    host = os.getenv("ORACLE_HOST", "localhost").strip() or "localhost"
    host_ip = os.getenv("ORACLE_HOST_IP", "").strip()

    if not user or not password:
        raise RuntimeError(
            "ORACLE_USER / ORACLE_PASSWORD are missing in backend/.env."
        )

    try:
        connection = oracledb.connect(user=user, password=password, dsn=_dsn(host))
    except oracledb.Error:
        if not host_ip:
            raise
        connection = oracledb.connect(user=user, password=password, dsn=_dsn(host_ip))

    return CompatConnection(connection)
