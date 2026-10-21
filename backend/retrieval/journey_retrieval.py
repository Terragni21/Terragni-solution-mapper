import os
from collections import defaultdict
from typing import Any

import psycopg2
from dotenv import load_dotenv

from backend.database.connection import get_connection
from backend.retrieval.semantic_search import (
    cosine_similarity,
    create_query_embedding,
    semantic_search,
)

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
    """Convert a database value (PostgreSQL TEXT, or a legacy LOB) to text."""
    if value is None:
        return None

    if hasattr(value, "read"):
        value = value.read()

    text = str(value).strip()
    return text if text else None

def _case_study_key(case_study: dict[str, Any]) -> Any:
    return case_study.get("case_study_id")

def _build_evidence_item(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw semantic-search result into API‑safe evidence."""
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
        "relevance_note": None,
    }

def _build_case_study_candidates(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate multiple retrieved chunks belonging to the same case study.

    Ranking uses strongest semantic evidence and supporting‑chunk count.
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
                "case_study_code": _clean_text(case_study.get("case_study_code")),
                "title": _clean_text(case_study.get("title")),
                "public_title": _clean_text(case_study.get("public_title")),
                "client_name": _clean_text(case_study.get("client_name")),
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
        entry["best_similarity"] = max(entry["best_similarity"], similarity)
        chunk_id = result.get("chunk_id")
        if chunk_id not in entry["supporting_chunk_ids"]:
            entry["supporting_chunk_ids"].append(chunk_id)
        if len(entry["supporting_evidence"]) < 4:
            entry["supporting_evidence"].append(_build_evidence_item(result))
    candidates = list(grouped.values())
    candidates.sort(
        key=lambda item: (item["best_similarity"], len(item["supporting_chunk_ids"])),
        reverse=True,
    )
    return candidates

def _load_case_study_master_data(
    connection,
    case_study_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Load the long text fields of the given case studies."""
    if not case_study_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(case_study_ids))
    sql = f"""
        SELECT
            case_study_id,
            summary,
            challenge,
            objective,
            approach,
            key_finding,
            solution,
            business_outcome
        FROM case_study
        WHERE case_study_id IN ({placeholders})
    """
    result: dict[int, dict[str, Any]] = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(case_study_ids))
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
    """Load relationships (industries, offerings, frameworks, challenges, outcomes)."""
    if not case_study_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(case_study_ids))
    params = tuple(case_study_ids)
    result: dict[int, dict[str, list[dict[str, Any]]]] = {
        int(case_id): {"industries": [], "offerings": [], "frameworks": [], "challenges": [], "outcomes": []}
        for case_id in case_study_ids
    }
    relationship_queries = {
        "industries": f"""
            SELECT
                csi.case_study_id,
                i.industry_id,
                i.industry_code,
                i.industry_name,
                i.description,
                csi.relationship_type
            FROM case_study_industry csi
            INNER JOIN industry i ON i.industry_id = csi.industry_id
            WHERE csi.case_study_id IN ({placeholders})
            ORDER BY csi.case_study_id, i.industry_name
        """,
        "offerings": f"""
            SELECT
                cso.case_study_id,
                o.offering_id,
                o.offering_code,
                o.offering_name,
                o.description,
                cso.relationship_type
            FROM case_study_offering cso
            INNER JOIN offering o ON o.offering_id = cso.offering_id
            WHERE cso.case_study_id IN ({placeholders})
            ORDER BY cso.case_study_id, o.offering_name
        """,
        "frameworks": f"""
            SELECT
                csf.case_study_id,
                f.framework_id,
                f.framework_code,
                f.framework_name,
                f.description,
                csf.relationship_type
            FROM case_study_framework csf
            INNER JOIN framework f ON f.framework_id = csf.framework_id
            WHERE csf.case_study_id IN ({placeholders})
            ORDER BY csf.case_study_id, f.framework_name
        """,
        "challenges": f"""
            SELECT
                csc.case_study_id,
                c.challenge_id,
                c.challenge_code,
                c.challenge_name,
                c.description,
                csc.relationship_type
            FROM case_study_challenge csc
            INNER JOIN challenge c ON c.challenge_id = csc.challenge_id
            WHERE csc.case_study_id IN ({placeholders})
            ORDER BY csc.case_study_id, c.challenge_name
        """,
        "outcomes": f"""
            SELECT
                cso.case_study_id,
                o.outcome_id,
                o.outcome_code,
                o.outcome_name,
                o.description,
                cso.relationship_type
            FROM case_study_outcome cso
            INNER JOIN outcome o ON o.outcome_id = cso.outcome_id
            WHERE cso.case_study_id IN ({placeholders})
            ORDER BY cso.case_study_id, o.outcome_name
        """,
    }
    with connection.cursor() as cursor:
        for entity_type, sql in relationship_queries.items():
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            except psycopg2.Error as exc:
                # A missing/empty link table (e.g. case_study_offering was
                # never exported from Oracle) must not break the whole answer.
                connection.rollback()
                print(f"Warning: could not load case-study {entity_type}: {exc}")
                continue
            for row in rows:
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
                else:  # outcomes
                    item = {
                        "outcome_id": int(row[1]),
                        "code": _clean_text(row[2]),
                        "name": _clean_text(row[3]),
                        "description": _clean_text(row[4]),
                        "relationship_type": _clean_text(row[5]),
                    }
                result.setdefault(
                    case_id,
                    {"industries": [], "offerings": [], "frameworks": [], "challenges": [], "outcomes": []},
                )[entity_type].append(item)
    return result

def _embed_text(text: str) -> list[float]:
    """Create a FastEmbed embedding for a short master‑knowledge record.
    Uses the same embedding function as query generation.
    """
    return create_query_embedding(text)

def _semantic_rank_master_entities(
    query: str,
    rows: list[dict[str, Any]],
    *,
    top_k: int,
    minimum_similarity: float,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    query_embedding = _embed_text(query)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        searchable = " | ".join(v for v in [row.get("name"), row.get("code"), row.get("description")] if v)
        if not searchable.strip():
            continue
        entity_emb = _embed_text(searchable)
        sim = cosine_similarity(query_embedding, entity_emb)
        if sim < minimum_similarity:
            continue
        item = dict(row)
        item["similarity"] = round(float(sim), 6)
        ranked.append(item)
    ranked.sort(key=lambda i: i["similarity"], reverse=True)
    return ranked[:top_k]

def _load_master_entity_catalogs(connection) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load standalone Offering and Framework master knowledge."""
    offerings: list[dict[str, Any]] = []
    frameworks: list[dict[str, Any]] = []
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT offering_id, offering_code, offering_name, description, status
            FROM offering
            WHERE status IS NULL OR UPPER(status) = 'ACTIVE'
            ORDER BY offering_id
        """)
        for row in cursor:
            offerings.append({
                "offering_id": int(row[0]),
                "code": _clean_text(row[1]),
                "name": _clean_text(row[2]),
                "description": _clean_text(row[3]),
                "status": _clean_text(row[4]),
            })
        cursor.execute("""
            SELECT framework_id, framework_code, framework_name, description, status
            FROM framework
            WHERE status IS NULL OR UPPER(status) = 'ACTIVE'
            ORDER BY framework_id
        """)
        for row in cursor:
            frameworks.append({
                "framework_id": int(row[0]),
                "code": _clean_text(row[1]),
                "name": _clean_text(row[2]),
                "description": _clean_text(row[3]),
                "status": _clean_text(row[4]),
            })
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
    query = (query or "").strip()
    if not query:
        raise ValueError("Query cannot be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")
    if max_evidence <= 0:
        raise ValueError("max_evidence must be greater than zero.")
    if max_case_studies <= 0:
        raise ValueError("max_case_studies must be greater than zero.")
    semantic_results = semantic_search(query=query, top_k=top_k, minimum_similarity=minimum_similarity)
    evidence = [_build_evidence_item(r) for r in semantic_results[:max_evidence]]
    case_studies = _build_case_study_candidates(semantic_results)[:max_case_studies]
    case_study_ids = [int(cs["case_study_id"]) for cs in case_studies if cs.get("case_study_id")]
    relationships = {}
    master_data = {}
    catalog_offerings = []
    catalog_frameworks = []
    conn = get_connection()
    try:
        if case_study_ids:
            master_data = _load_case_study_master_data(conn, case_study_ids)
            relationships = _load_case_study_relationships(conn, case_study_ids)
        catalog_offerings, catalog_frameworks = _load_master_entity_catalogs(conn)
    finally:
        conn.close()
    offerings = _semantic_rank_master_entities(
        query, catalog_offerings, top_k=max_offerings, minimum_similarity=master_minimum_similarity
    )
    frameworks = _semantic_rank_master_entities(
        query, catalog_frameworks, top_k=max_frameworks, minimum_similarity=master_minimum_similarity
    )
    all_entities: dict[str, list[dict[str, Any]]] = {
        "industries": [],
        "offerings": offerings,
        "frameworks": frameworks,
        "challenges": [],
        "outcomes": [],
    }
    seen: dict[str, set[Any]] = defaultdict(set)
    for cs in case_studies:
        cid = int(cs["case_study_id"])
        rels = relationships.get(cid, {})
        cs.update(master_data.get(cid, {}))
        cs["relationships"] = rels
        for entity_type, entities in rels.items():
            if entity_type in {"offerings", "frameworks"}:
                continue
            for entity in entities:
                eid = entity.get("industry_id") or entity.get("challenge_id") or entity.get("outcome_id")
                if eid in seen[entity_type]:
                    continue
                seen[entity_type].add(eid)
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
    pkg = retrieve_journey_evidence(test_query)
    print("=" * 90)
    print("TERRAGNI JOURNEY RETRIEVAL TEST")
    print("=" * 90)
    print("Query:", pkg["query"])
    print("Evidence:", pkg["retrieval"]["evidence_count"])
    print("Case studies:", pkg["retrieval"]["case_study_count"])
    print("Industries:", len(pkg["industries"]))
    print("Offerings:", len(pkg["offerings"]))
    print("Frameworks:", len(pkg["frameworks"]))
    print("Challenges:", len(pkg["challenges"]))
    print("Outcomes:", len(pkg["outcomes"]))
    print("-" * 90)
    for i, off in enumerate(pkg["offerings"], 1):
        print(f"{i}. {off.get('name')} (sim={off.get('similarity'):.6f})")
    print("-" * 90)
    for i, fw in enumerate(pkg["frameworks"], 1):
        print(f"{i}. {fw.get('name')} (sim={fw.get('similarity'):.6f})")
    print("-" * 90)
    for i, cs in enumerate(pkg["case_studies"], 1):
        print(f"{i}. {cs.get('title')} (sim={cs.get('best_similarity'):.6f})")
        print("   Supporting chunks:", cs.get("supporting_chunk_ids"))
        print("   Offerings:", [it.get('name') for it in cs["relationships"].get('offerings', [])])
