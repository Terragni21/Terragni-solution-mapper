from __future__ import annotations

"""
Terragni journey retrieval layer.

Responsibilities:
- Run semantic retrieval against the existing Oracle + Ollama search layer.
- Aggregate retrieved chunks into evidence and case-study candidates.
- Enrich matched case studies with Oracle master-data relationships.
- Keep retrieval semantic/evidence-driven; there is no phrase-to-offering routing.

This module does NOT call Groq. Groq belongs in the journey/orchestration layer,
after this module has produced an evidence package.
"""

import os
from collections import defaultdict
from typing import Any

from dotenv import load_dotenv
import ollama

from backend.database.connection import get_connection
from backend.retrieval.semantic_search import semantic_search


BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

DEFAULT_TOP_K = int(os.getenv("JOURNEY_RETRIEVAL_TOP_K", "24"))
DEFAULT_MIN_SIMILARITY = float(
    os.getenv("JOURNEY_RETRIEVAL_MIN_SIMILARITY", "0.45")
)
DEFAULT_MAX_EVIDENCE = int(
    os.getenv("JOURNEY_RETRIEVAL_MAX_EVIDENCE", "12")
)
DEFAULT_MAX_CASE_STUDIES = int(
    os.getenv("JOURNEY_RETRIEVAL_MAX_CASE_STUDIES", "8")
)


def _clean_text(value: Any) -> str | None:
    """Safely convert Oracle CLOB/scalar values into plain text."""
    if value is None:
        return None

    if hasattr(value, "read"):
        value = value.read()

    text = str(value).strip()
    return text if text else None


def _case_study_key(case_study: dict[str, Any]) -> Any:
    return case_study.get("case_study_id")


def _build_evidence_item(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw semantic-search result into API-safe evidence."""
    document = result.get("document") or {}
    section = result.get("section") or {}
    case_study = result.get("case_study")

    return {
        "chunk_id": result.get("chunk_id"),
        "similarity": round(float(result.get("similarity", 0.0)), 6),
        "text": _clean_text(result.get("chunk_text")) or "",
        "document": {
            "document_id": result.get("document_id"),
            "title": _clean_text(document.get("title")),
            "file_name": _clean_text(document.get("file_name")),
            "document_type": _clean_text(document.get("document_type")),
        },
        "section": {
            "section_id": result.get("section_id"),
            "section_type": _clean_text(section.get("section_type")),
            "section_title": _clean_text(section.get("section_title")),
        },
        "case_study_id": (
            case_study.get("case_study_id")
            if case_study
            else None
        ),
        "evidence_type": (
            _clean_text(case_study.get("evidence_type"))
            if case_study
            else None
        ),
        # RELEVANCE_NOTE is an Oracle CLOB locator from the semantic-search
        # connection. That connection has already closed by this stage.
        "relevance_note": None,
    }


def _build_case_study_candidates(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Aggregate multiple retrieved chunks belonging to the same case study.

    A case study's ranking is based on the strongest semantic evidence and
    supporting-chunk count. No phrase matching is used.
    """
    grouped: dict[Any, dict[str, Any]] = {}

    for result in results:
        case_study = result.get("case_study")
        if not case_study:
            continue

        case_id = _case_study_key(case_study)
        if case_id is None:
            continue

        similarity = float(result.get("similarity", 0.0))
        entry = grouped.get(case_id)

        if entry is None:
            entry = {
                "case_study_id": case_id,
                "case_study_code": _clean_text(
                    case_study.get("case_study_code")
                ),
                "title": _clean_text(case_study.get("title")),
                "public_title": _clean_text(
                    case_study.get("public_title")
                ),
                "client_name": _clean_text(
                    case_study.get("client_name")
                ),
                "summary": None,
                "challenge": None,
                "objective": None,
                "approach": None,
                "key_finding": None,
                "solution": None,
                "business_outcome": None,
                "best_similarity": similarity,
                "supporting_chunk_ids": [],
                "supporting_evidence": [],
            }
            grouped[case_id] = entry

        entry["best_similarity"] = max(
            entry["best_similarity"],
            similarity,
        )

        chunk_id = result.get("chunk_id")
        if chunk_id not in entry["supporting_chunk_ids"]:
            entry["supporting_chunk_ids"].append(chunk_id)

        if len(entry["supporting_evidence"]) < 4:
            entry["supporting_evidence"].append(
                _build_evidence_item(result)
            )

    candidates = list(grouped.values())

    # Strongest semantic match first; number of independent supporting chunks
    # acts only as a secondary evidence-strength signal.
    candidates.sort(
        key=lambda item: (
            item["best_similarity"],
            len(item["supporting_chunk_ids"]),
        ),
        reverse=True,
    )

    return candidates


def _load_case_study_master_data(
    connection,
    case_study_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Materialize CASE_STUDY CLOB fields while Oracle connection is live."""
    if not case_study_ids:
        return {}

    placeholders = ", ".join(
        f":id_{index}" for index in range(len(case_study_ids))
    )
    params = {
        f"id_{index}": int(case_id)
        for index, case_id in enumerate(case_study_ids)
    }

    sql = f"""
        SELECT
            CASE_STUDY_ID,
            SUMMARY,
            CHALLENGE,
            OBJECTIVE,
            APPROACH,
            KEY_FINDING,
            SOLUTION,
            BUSINESS_OUTCOME
        FROM CASE_STUDY
        WHERE CASE_STUDY_ID IN ({placeholders})
    """

    result: dict[int, dict[str, Any]] = {}

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row in cursor:
            case_id = int(row[0])
            result[case_id] = {
                "summary": _clean_text(row[1]),
                "challenge": _clean_text(row[2]),
                "objective": _clean_text(row[3]),
                "approach": _clean_text(row[4]),
                "key_finding": _clean_text(row[5]),
                "solution": _clean_text(row[6]),
                "business_outcome": _clean_text(row[7]),
            }

    return result


def _load_case_study_relationships(
    connection,
    case_study_ids: list[int],
) -> dict[int, dict[str, list[dict[str, Any]]]]:
    """Load master-data relationships for the matched case studies."""
    if not case_study_ids:
        return {}

    placeholders = ", ".join(
        f":id_{index}" for index in range(len(case_study_ids))
    )
    params = {
        f"id_{index}": int(case_id)
        for index, case_id in enumerate(case_study_ids)
    }

    result: dict[int, dict[str, list[dict[str, Any]]]] = {
        int(case_id): {
            "industries": [],
            "offerings": [],
            "frameworks": [],
            "challenges": [],
            "outcomes": [],
        }
        for case_id in case_study_ids
    }

    relationship_queries = {
        "industries": f"""
            SELECT
                csi.CASE_STUDY_ID,
                i.INDUSTRY_ID,
                i.INDUSTRY_CODE,
                i.INDUSTRY_NAME,
                i.DESCRIPTION,
                csi.RELATIONSHIP_TYPE
            FROM CASE_STUDY_INDUSTRY csi
            INNER JOIN INDUSTRY i
                ON i.INDUSTRY_ID = csi.INDUSTRY_ID
            WHERE csi.CASE_STUDY_ID IN ({placeholders})
            ORDER BY csi.CASE_STUDY_ID, i.INDUSTRY_NAME
        """,
        "offerings": f"""
            SELECT
                cso.CASE_STUDY_ID,
                o.OFFERING_ID,
                o.OFFERING_CODE,
                o.OFFERING_NAME,
                o.DESCRIPTION,
                cso.RELATIONSHIP_TYPE
            FROM CASE_STUDY_OFFERING cso
            INNER JOIN OFFERING o
                ON o.OFFERING_ID = cso.OFFERING_ID
            WHERE cso.CASE_STUDY_ID IN ({placeholders})
            ORDER BY cso.CASE_STUDY_ID, o.OFFERING_NAME
        """,
        "frameworks": f"""
            SELECT
                csf.CASE_STUDY_ID,
                f.FRAMEWORK_ID,
                f.FRAMEWORK_CODE,
                f.FRAMEWORK_NAME,
                f.DESCRIPTION,
                csf.RELATIONSHIP_TYPE
            FROM CASE_STUDY_FRAMEWORK csf
            INNER JOIN FRAMEWORK f
                ON f.FRAMEWORK_ID = csf.FRAMEWORK_ID
            WHERE csf.CASE_STUDY_ID IN ({placeholders})
            ORDER BY csf.CASE_STUDY_ID, f.FRAMEWORK_NAME
        """,
        "challenges": f"""
            SELECT
                csc.CASE_STUDY_ID,
                c.CHALLENGE_ID,
                c.CHALLENGE_CODE,
                c.CHALLENGE_NAME,
                c.DESCRIPTION,
                csc.RELATIONSHIP_TYPE
            FROM CASE_STUDY_CHALLENGE csc
            INNER JOIN CHALLENGE c
                ON c.CHALLENGE_ID = csc.CHALLENGE_ID
            WHERE csc.CASE_STUDY_ID IN ({placeholders})
            ORDER BY csc.CASE_STUDY_ID, c.CHALLENGE_NAME
        """,
        "outcomes": f"""
            SELECT
                cso.CASE_STUDY_ID,
                o.OUTCOME_ID,
                o.OUTCOME_CODE,
                o.OUTCOME_NAME,
                o.DESCRIPTION,
                cso.RELATIONSHIP_TYPE
            FROM CASE_STUDY_OUTCOME cso
            INNER JOIN OUTCOME o
                ON o.OUTCOME_ID = cso.OUTCOME_ID
            WHERE cso.CASE_STUDY_ID IN ({placeholders})
            ORDER BY cso.CASE_STUDY_ID, o.OUTCOME_NAME
        """,
    }

    with connection.cursor() as cursor:
        for entity_type, sql in relationship_queries.items():
            cursor.execute(sql, params)

            for row in cursor:
                case_id = int(row[0])

                if entity_type == "industries":
                    item = {
                        "industry_id": int(row[1]),
                        "code": _clean_text(row[2]),
                        "name": _clean_text(row[3]),
                        "description": _clean_text(row[4]),
                        "relationship_type": _clean_text(row[5]),
                    }
                elif entity_type == "offerings":
                    item = {
                        "offering_id": int(row[1]),
                        "code": _clean_text(row[2]),
                        "name": _clean_text(row[3]),
                        "description": _clean_text(row[4]),
                        "relationship_type": _clean_text(row[5]),
                    }
                elif entity_type == "frameworks":
                    item = {
                        "framework_id": int(row[1]),
                        "code": _clean_text(row[2]),
                        "name": _clean_text(row[3]),
                        "description": _clean_text(row[4]),
                        "relationship_type": _clean_text(row[5]),
                    }
                elif entity_type == "challenges":
                    item = {
                        "challenge_id": int(row[1]),
                        "code": _clean_text(row[2]),
                        "name": _clean_text(row[3]),
                        "description": _clean_text(row[4]),
                        "relationship_type": _clean_text(row[5]),
                    }
                else:
                    item = {
                        "outcome_id": int(row[1]),
                        "code": _clean_text(row[2]),
                        "name": _clean_text(row[3]),
                        "description": _clean_text(row[4]),
                        "relationship_type": _clean_text(row[5]),
                    }

                result.setdefault(
                    case_id,
                    {
                        "industries": [],
                        "offerings": [],
                        "frameworks": [],
                        "challenges": [],
                        "outcomes": [],
                    },
                )[entity_type].append(item)

    return result


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """Calculate cosine similarity between two embedding vectors."""
    if len(vector_a) != len(vector_b):
        raise ValueError(
            "Vector dimensions do not match: "
            f"{len(vector_a)} != {len(vector_b)}"
        )

    dot_product = 0.0
    magnitude_a = 0.0
    magnitude_b = 0.0

    for a, b in zip(vector_a, vector_b):
        dot_product += a * b
        magnitude_a += a * a
        magnitude_b += b * b

    magnitude_a = magnitude_a ** 0.5
    magnitude_b = magnitude_b ** 0.5

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def _embed_text(text: str) -> list[float]:
    """Create an Ollama embedding for a short master-knowledge record.

    Offering and framework descriptions rarely change, so their embeddings
    are cached instead of being recomputed on every visitor query.
    """
    from backend.retrieval.semantic_search import create_query_embedding

    return create_query_embedding(text)


def _semantic_rank_master_entities(
    query: str,
    rows: list[dict[str, Any]],
    *,
    top_k: int,
    minimum_similarity: float,
) -> list[dict[str, Any]]:
    """
    Rank standalone Terragni master entities semantically.

    This intentionally does NOT create a CASE_STUDY_OFFERING or
    CASE_STUDY_FRAMEWORK relationship. It only identifies relevant
    master knowledge for the reasoning layer.
    """
    if not rows:
        return []

    query_embedding = _embed_text(query)

    ranked: list[dict[str, Any]] = []

    for row in rows:
        searchable_text = " | ".join(
            value
            for value in [
                row.get("name"),
                row.get("code"),
                row.get("description"),
            ]
            if value
        )

        if not searchable_text.strip():
            continue

        entity_embedding = _embed_text(searchable_text)
        similarity = cosine_similarity(
            query_embedding,
            entity_embedding,
        )

        if similarity < minimum_similarity:
            continue

        item = dict(row)
        item["similarity"] = round(float(similarity), 6)
        ranked.append(item)

    ranked.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    return ranked[:top_k]


def _load_master_entity_catalogs(
    connection,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load standalone Offering and Framework master knowledge."""
    offerings: list[dict[str, Any]] = []
    frameworks: list[dict[str, Any]] = []

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                OFFERING_ID,
                OFFERING_CODE,
                OFFERING_NAME,
                DESCRIPTION,
                STATUS
            FROM OFFERING
            WHERE STATUS IS NULL OR UPPER(STATUS) = 'ACTIVE'
            ORDER BY OFFERING_ID
        """)

        for row in cursor:
            offerings.append(
                {
                    "offering_id": int(row[0]),
                    "code": _clean_text(row[1]),
                    "name": _clean_text(row[2]),
                    "description": _clean_text(row[3]),
                    "status": _clean_text(row[4]),
                }
            )

        cursor.execute("""
            SELECT
                FRAMEWORK_ID,
                FRAMEWORK_CODE,
                FRAMEWORK_NAME,
                DESCRIPTION,
                STATUS
            FROM FRAMEWORK
            WHERE STATUS IS NULL OR UPPER(STATUS) = 'ACTIVE'
            ORDER BY FRAMEWORK_ID
        """)

        for row in cursor:
            frameworks.append(
                {
                    "framework_id": int(row[0]),
                    "code": _clean_text(row[1]),
                    "name": _clean_text(row[2]),
                    "description": _clean_text(row[3]),
                    "status": _clean_text(row[4]),
                }
            )

    return offerings, frameworks


def retrieve_journey_evidence(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    minimum_similarity: float = DEFAULT_MIN_SIMILARITY,
    max_evidence: int = DEFAULT_MAX_EVIDENCE,
    max_case_studies: int = DEFAULT_MAX_CASE_STUDIES,
    max_offerings: int = 5,
    max_frameworks: int = 5,
    master_minimum_similarity: float = 0.35,
) -> dict[str, Any]:
    """
    Produce the evidence package consumed by the journey/LLM layer.

    The function intentionally returns raw evidence plus structured master
    entities. It does not decide whether a visitor's challenge is a match.
    That decision belongs to the reasoning layer using this evidence.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Query cannot be empty.")

    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")

    if max_evidence <= 0:
        raise ValueError("max_evidence must be greater than zero.")

    if max_case_studies <= 0:
        raise ValueError("max_case_studies must be greater than zero.")

    semantic_results = semantic_search(
        query=query,
        top_k=top_k,
        minimum_similarity=minimum_similarity,
    )

    evidence = [
        _build_evidence_item(result)
        for result in semantic_results[:max_evidence]
    ]

    case_studies = _build_case_study_candidates(semantic_results)
    case_studies = case_studies[:max_case_studies]

    case_study_ids = [
        int(item["case_study_id"])
        for item in case_studies
        if item.get("case_study_id") is not None
    ]

    relationships: dict[
        int,
        dict[str, list[dict[str, Any]]]
    ] = {}
    master_data: dict[int, dict[str, Any]] = {}
    catalog_offerings: list[dict[str, Any]] = []
    catalog_frameworks: list[dict[str, Any]] = []

    connection = None
    try:
        connection = get_connection()

        if case_study_ids:
            master_data = _load_case_study_master_data(
                connection,
                case_study_ids,
            )
            relationships = _load_case_study_relationships(
                connection,
                case_study_ids,
            )

        catalog_offerings, catalog_frameworks = (
            _load_master_entity_catalogs(connection)
        )
    finally:
        if connection is not None:
            connection.close()

    # Offerings and frameworks are standalone Terragni master knowledge.
    # They are semantically ranked independently of case-study relationships.
    offerings = _semantic_rank_master_entities(
        query,
        catalog_offerings,
        top_k=max_offerings,
        minimum_similarity=master_minimum_similarity,
    )

    frameworks = _semantic_rank_master_entities(
        query,
        catalog_frameworks,
        top_k=max_frameworks,
        minimum_similarity=master_minimum_similarity,
    )

    all_entities: dict[str, list[dict[str, Any]]] = {
        "industries": [],
        "offerings": offerings,
        "frameworks": frameworks,
        "challenges": [],
        "outcomes": [],
    }

    seen_entities: dict[str, set[Any]] = defaultdict(set)

    for case_study in case_studies:
        case_id = int(case_study["case_study_id"])
        rels = relationships.get(case_id, {})
        case_study.update(master_data.get(case_id, {}))
        case_study["relationships"] = rels

        for entity_type, entities in rels.items():
            # Offerings/frameworks are already ranked independently above.
            # Explicit case-study relationships remain attached to the
            # individual case study under case_study["relationships"].
            if entity_type in {"offerings", "frameworks"}:
                continue

            for entity in entities:
                entity_id = (
                    entity.get("industry_id")
                    or entity.get("challenge_id")
                    or entity.get("outcome_id")
                )

                if entity_id in seen_entities[entity_type]:
                    continue

                seen_entities[entity_type].add(entity_id)
                all_entities[entity_type].append(entity)

    return {
        "query": query,
        "retrieval": {
            "top_k": top_k,
            "minimum_similarity": minimum_similarity,
            "returned_results": len(semantic_results),
            "evidence_count": len(evidence),
            "case_study_count": len(case_studies),
        },
        "evidence": evidence,
        "case_studies": case_studies,
        **all_entities,
    }


if __name__ == "__main__":
    test_query = (
        "Our affluent banking customers are happy but not engaged. "
        "What is really driving that gap?"
    )

    package = retrieve_journey_evidence(test_query)

    print("=" * 90)
    print("TERRAGNI JOURNEY RETRIEVAL TEST")
    print("=" * 90)
    print("Query:", package["query"])
    print("Evidence:", package["retrieval"]["evidence_count"])
    print("Case studies:", package["retrieval"]["case_study_count"])
    print("Industries:", len(package["industries"]))
    print("Offerings:", len(package["offerings"]))
    print("Frameworks:", len(package["frameworks"]))
    print("Challenges:", len(package["challenges"]))
    print("Outcomes:", len(package["outcomes"]))

    print("-" * 90)
    print("SEMANTIC OFFERINGS:")
    for item in package["offerings"]:
        print(
            f"  - {item.get('name')} "
            f"(similarity={item.get('similarity'):.6f})"
        )

    print("-" * 90)
    print("SEMANTIC FRAMEWORKS:")
    for item in package["frameworks"]:
        print(
            f"  - {item.get('name')} "
            f"(similarity={item.get('similarity'):.6f})"
        )
    print("-" * 90)

    for index, case_study in enumerate(
        package["case_studies"],
        start=1,
    ):
        print(
            f"{index}. "
            f"{case_study.get('title')} "
            f"(similarity={case_study.get('best_similarity'):.6f})"
        )
        print(
            "   Supporting chunks:",
            case_study.get("supporting_chunk_ids"),
        )
        print(
            "   Offerings:",
            [
                item.get("name")
                for item in case_study["relationships"].get(
                    "offerings",
                    [],
                )
            ],
        )
