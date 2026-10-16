from __future__ import annotations

from typing import Any, Optional

from .db import fetch_all, fetch_one, execute, execute_returning_id


def get_frameworks() -> list[dict[str, Any]]:
    """Return all frameworks stored in Oracle."""
    return fetch_all(
        """
        SELECT
            FRAMEWORK_ID,
            FRAMEWORK_CODE,
            FRAMEWORK_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM FRAMEWORK
        ORDER BY FRAMEWORK_NAME
        """
    )


def get_framework(
    framework_id: int,
) -> Optional[dict[str, Any]]:
    """Return one framework by ID."""
    return fetch_one(
        """
        SELECT
            FRAMEWORK_ID,
            FRAMEWORK_CODE,
            FRAMEWORK_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM FRAMEWORK
        WHERE FRAMEWORK_ID = :framework_id
        """,
        {
            "framework_id": framework_id,
        },
    )


def get_framework_by_code(
    framework_code: str,
) -> Optional[dict[str, Any]]:
    """Return one framework by business code."""
    return fetch_one(
        """
        SELECT
            FRAMEWORK_ID,
            FRAMEWORK_CODE,
            FRAMEWORK_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM FRAMEWORK
        WHERE UPPER(FRAMEWORK_CODE) = UPPER(:framework_code)
        """,
        {
            "framework_code": framework_code,
        },
    )


def get_framework_by_name(
    framework_name: str,
) -> Optional[dict[str, Any]]:
    """Return one framework by name."""
    return fetch_one(
        """
        SELECT
            FRAMEWORK_ID,
            FRAMEWORK_CODE,
            FRAMEWORK_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM FRAMEWORK
        WHERE UPPER(FRAMEWORK_NAME) = UPPER(:framework_name)
        """,
        {
            "framework_name": framework_name,
        },
    )


def create_framework(
    framework_code: str,
    framework_name: str,
    description: Optional[str] = None,
    status: str = "ACTIVE",
) -> int:
    """
    Create a framework and return its Oracle FRAMEWORK_ID.
    """
    existing = get_framework_by_code(framework_code)

    if existing:
        return int(existing["framework_id"])

    return execute_returning_id(
        """
        INSERT INTO FRAMEWORK (
            FRAMEWORK_CODE,
            FRAMEWORK_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        )
        VALUES (
            :framework_code,
            :framework_name,
            :description,
            :status,
            SYSTIMESTAMP,
            SYSTIMESTAMP
        )
        RETURNING FRAMEWORK_ID INTO :out_id
        """,
        {
            "framework_code": framework_code,
            "framework_name": framework_name,
            "description": description,
            "status": status,
        },
        id_column="FRAMEWORK_ID",
    )


def update_framework(
    framework_id: int,
    framework_name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """Update an existing framework."""
    current = get_framework(framework_id)

    if not current:
        raise ValueError(
            f"Framework {framework_id} does not exist."
        )

    return execute(
        """
        UPDATE FRAMEWORK
        SET
            FRAMEWORK_NAME = :framework_name,
            DESCRIPTION = :description,
            STATUS = :status,
            UPDATED_AT = SYSTIMESTAMP
        WHERE FRAMEWORK_ID = :framework_id
        """,
        {
            "framework_id": framework_id,
            "framework_name": (
                framework_name
                if framework_name is not None
                else current["framework_name"]
            ),
            "description": (
                description
                if description is not None
                else current["description"]
            ),
            "status": (
                status
                if status is not None
                else current["status"]
            ),
        },
    )