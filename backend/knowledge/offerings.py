from __future__ import annotations

from typing import Any, Optional

from .db import fetch_all, fetch_one, execute, execute_returning_id


def get_offerings() -> list[dict[str, Any]]:
    """Return all offerings stored in Oracle."""
    return fetch_all(
        """
        SELECT
            OFFERING_ID,
            OFFERING_CODE,
            OFFERING_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM OFFERING
        ORDER BY OFFERING_NAME
        """
    )


def get_offering(
    offering_id: int,
) -> Optional[dict[str, Any]]:
    """Return one offering by ID."""
    return fetch_one(
        """
        SELECT
            OFFERING_ID,
            OFFERING_CODE,
            OFFERING_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM OFFERING
        WHERE OFFERING_ID = :offering_id
        """,
        {
            "offering_id": offering_id,
        },
    )


def get_offering_by_code(
    offering_code: str,
) -> Optional[dict[str, Any]]:
    """Return one offering by business code."""
    return fetch_one(
        """
        SELECT
            OFFERING_ID,
            OFFERING_CODE,
            OFFERING_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM OFFERING
        WHERE UPPER(OFFERING_CODE) = UPPER(:offering_code)
        """,
        {
            "offering_code": offering_code,
        },
    )


def get_offering_by_name(
    offering_name: str,
) -> Optional[dict[str, Any]]:
    """Return one offering by name."""
    return fetch_one(
        """
        SELECT
            OFFERING_ID,
            OFFERING_CODE,
            OFFERING_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM OFFERING
        WHERE UPPER(OFFERING_NAME) = UPPER(:offering_name)
        """,
        {
            "offering_name": offering_name,
        },
    )


def create_offering(
    offering_code: str,
    offering_name: str,
    description: Optional[str] = None,
    status: str = "ACTIVE",
) -> int:
    """
    Create an offering and return its Oracle OFFERING_ID.
    """
    existing = get_offering_by_code(offering_code)

    if existing:
        return int(existing["offering_id"])

    return execute_returning_id(
        """
        INSERT INTO OFFERING (
            OFFERING_CODE,
            OFFERING_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        )
        VALUES (
            :offering_code,
            :offering_name,
            :description,
            :status,
            SYSTIMESTAMP,
            SYSTIMESTAMP
        )
        RETURNING OFFERING_ID INTO :out_id
        """,
        {
            "offering_code": offering_code,
            "offering_name": offering_name,
            "description": description,
            "status": status,
        },
        id_column="OFFERING_ID",
    )


def update_offering(
    offering_id: int,
    offering_name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """Update an existing offering."""
    current = get_offering(offering_id)

    if not current:
        raise ValueError(
            f"Offering {offering_id} does not exist."
        )

    return execute(
        """
        UPDATE OFFERING
        SET
            OFFERING_NAME = :offering_name,
            DESCRIPTION = :description,
            STATUS = :status,
            UPDATED_AT = SYSTIMESTAMP
        WHERE OFFERING_ID = :offering_id
        """,
        {
            "offering_id": offering_id,
            "offering_name": (
                offering_name
                if offering_name is not None
                else current["offering_name"]
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