from __future__ import annotations

from typing import Any, Iterable, Optional

from database.connection import get_connection

def fetch_all(
    sql: str,
    params: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """
    Execute a SELECT query and return rows as dictionaries.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(sql, params or {})

        columns = [
            description[0].lower()
            for description in cursor.description
        ]

        rows = cursor.fetchall()

        return [
            dict(zip(columns, row))
            for row in rows
        ]

    finally:
        try:
            cursor.close()
        except Exception:
            pass

        connection.close()


def fetch_one(
    sql: str,
    params: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Execute a SELECT query and return one row as a dictionary.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(sql, params or {})

        row = cursor.fetchone()

        if row is None:
            return None

        columns = [
            description[0].lower()
            for description in cursor.description
        ]

        return dict(zip(columns, row))

    finally:
        try:
            cursor.close()
        except Exception:
            pass

        connection.close()


def execute(
    sql: str,
    params: Optional[dict[str, Any]] = None,
) -> int:
    """
    Execute INSERT / UPDATE / DELETE.

    Returns:
        Number of affected rows.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            sql,
            params or {},
        )

        affected_rows = cursor.rowcount

        connection.commit()

        return affected_rows

    except Exception:
        connection.rollback()
        raise

    finally:
        try:
            cursor.close()
        except Exception:
            pass

        connection.close()


def execute_many(
    sql: str,
    rows: Iterable[dict[str, Any]],
) -> int:
    """
    Execute the same INSERT / UPDATE statement for multiple rows.
    """
    rows = list(rows)

    if not rows:
        return 0

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.executemany(
            sql,
            rows,
        )

        affected_rows = cursor.rowcount

        connection.commit()

        return affected_rows

    except Exception:
        connection.rollback()
        raise

    finally:
        try:
            cursor.close()
        except Exception:
            pass

        connection.close()


def execute_returning_id(
    sql: str,
    params: Optional[dict[str, Any]] = None,
    *,
    id_column: str = "ID",
) -> int:
    """
    Execute an INSERT statement containing:

        RETURNING <id_column> INTO :out_id

    Example:

        INSERT INTO INDUSTRY (...)
        VALUES (...)
        RETURNING INDUSTRY_ID INTO :out_id

    Returns the generated Oracle ID.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor()

        bind_params = dict(params or {})

        out_var = cursor.var(int)

        bind_params["out_id"] = out_var

        cursor.execute(
            sql,
            bind_params,
        )

        connection.commit()

        value = out_var.getvalue()

        if isinstance(value, list):
            value = value[0]

        return int(value)

    except Exception:
        connection.rollback()
        raise

    finally:
        try:
            cursor.close()
        except Exception:
            pass

        connection.close()


def exists(
    sql: str,
    params: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Return True when the supplied existence query returns at least one row.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            sql,
            params or {},
        )

        return cursor.fetchone() is not None

    finally:
        try:
            cursor.close()
        except Exception:
            pass

        connection.close()
