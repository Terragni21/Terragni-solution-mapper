from __future__ import annotations

from typing import Any, Optional

from .db import fetch_all, fetch_one, execute, execute_returning_id


def get_industries() -> list[dict[str, Any]]:
    """
    Return all industries stored in Oracle.
    """
    return fetch_all(
        """
        SELECT
            INDUSTRY_ID,
            INDUSTRY_CODE,
            INDUSTRY_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM INDUSTRY
        ORDER BY INDUSTRY_NAME
        """
    )


def get_industry(
    industry_id: int,
) -> Optional[dict[str, Any]]:
    """
    Return one industry by ID.
    """
    return fetch_one(
        """
        SELECT
            INDUSTRY_ID,
            INDUSTRY_CODE,
            INDUSTRY_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM INDUSTRY
        WHERE INDUSTRY_ID = :industry_id
        """,
        {
            "industry_id": industry_id,
        },
    )


def get_industry_by_code(
    industry_code: str,
) -> Optional[dict[str, Any]]:
    """
    Return one industry by its business code.
    """
    return fetch_one(
        """
        SELECT
            INDUSTRY_ID,
            INDUSTRY_CODE,
            INDUSTRY_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM INDUSTRY
        WHERE UPPER(INDUSTRY_CODE) = UPPER(:industry_code)
        """,
        {
            "industry_code": industry_code,
        },
    )


def get_industry_by_name(
    industry_name: str,
) -> Optional[dict[str, Any]]:
    """
    Return one industry by its exact stored name,
    case-insensitively.
    """
    return fetch_one(
        """
        SELECT
            INDUSTRY_ID,
            INDUSTRY_CODE,
            INDUSTRY_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        FROM INDUSTRY
        WHERE UPPER(INDUSTRY_NAME) = UPPER(:industry_name)
        """,
        {
            "industry_name": industry_name,
        },
    )


def create_industry(
    industry_code: str,
    industry_name: str,
    description: Optional[str] = None,
    status: str = "ACTIVE",
) -> int:
    """
    Create an industry and return its Oracle INDUSTRY_ID.
    """
    existing = get_industry_by_code(industry_code)

    if existing:
        return int(existing["industry_id"])

    return execute_returning_id(
        """
        INSERT INTO INDUSTRY (
            INDUSTRY_CODE,
            INDUSTRY_NAME,
            DESCRIPTION,
            STATUS,
            CREATED_AT,
            UPDATED_AT
        )
        VALUES (
            :industry_code,
            :industry_name,
            :description,
            :status,
            SYSTIMESTAMP,
            SYSTIMESTAMP
        )
        RETURNING INDUSTRY_ID INTO :out_id
        """,
        {
            "industry_code": industry_code,
            "industry_name": industry_name,
            "description": description,
            "status": status,
        },
        id_column="INDUSTRY_ID",
    )


def update_industry(
    industry_id: int,
    industry_name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """
    Update an existing industry.

    Only supplied values are changed.
    """
    current = get_industry(industry_id)

    if not current:
        raise ValueError(
            f"Industry {industry_id} does not exist."
        )

    return execute(
        """
        UPDATE INDUSTRY
        SET
            INDUSTRY_NAME = :industry_name,
            DESCRIPTION = :description,
            STATUS = :status,
            UPDATED_AT = SYSTIMESTAMP
        WHERE INDUSTRY_ID = :industry_id
        """,
        {
            "industry_id": industry_id,
            "industry_name": (
                industry_name
                if industry_name is not None
                else current["industry_name"]
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