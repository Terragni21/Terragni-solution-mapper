"""
Knowledge path for the Terragni Solution Mapper.

Answers questions about Terragni itself (who it is, its services, methods and
past banking work) using only Terragni's own material:

    - brochure and thought-leadership chunks from the database
    - case-study evidence from the database
    - the full catalogue of offerings and frameworks

The LLM sees only this material. Every offering, framework and case study it
returns is checked against what it was given, so nothing can be invented.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from backend.app.confidentiality import (
    public_case_title,
    remove_client_names,
    sanitize_public_text,
)
from backend.journey_service import _call_groq, _clean
from backend.retrieval.journey_retrieval import retrieve_journey_evidence
from backend.retrieval.semantic_search import semantic_search

# Documents whose titles contain these words are brochures or
# thought-leadership material rather than client case studies.
_BROCHURE_WORDS = ("brochure", "lens", "sensemaking", "trunorth", "customer centric culture")

_CATALOG_CACHE: dict[str, Any] = {"value": None, "loaded_at": 0.0}
_CATALOG_LOCK = threading.Lock()
_CATALOG_SECONDS = 900


def _is_brochure(title: str | None) -> bool:
    lower = str(title or "").lower()
    return any(word in lower for word in _BROCHURE_WORDS)


def public_source_name(document_title: str | None, case_title: str | None = None) -> str:
    """A safe, readable name for a source document."""
    title = str(document_title or "").strip()

    if _is_brochure(title):
        # "EAS_Brochure_Terragni Consulting_2023" -> "EAS brochure"
        name = re.split(r"[_\-\s]+brochure", title, flags=re.IGNORECASE)[0]
        name = re.sub(r"[_]+", " ", name)
        name = re.sub(
            r"[-–]\s*(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\b.*$",
            "",
            name,
            flags=re.IGNORECASE,
        )
        name = re.sub(
            r"\bTerragni(?: Consulting)?\b|\b20\d\d\b|\(\d\)",
            "",
            name,
            flags=re.IGNORECASE,
        )
        name = re.sub(r"\s+", " ", name).strip(" -–")
        if "brochure" in title.lower():
            return f"Terragni brochure: {name}" if name else "Terragni brochure"
        return f"Terragni publication: {name}" if name else "Terragni publication"

    # "Leading Bank Goes Experiential_For its Premium Banking Customers_ A Terragni
    # Case Study" -> "Leading Bank Goes Experiential For its Premium Banking Customers"
    cleaned = re.sub(r"_+", " ", case_title or title)
    cleaned = re.sub(
        r"\s*[-–]?\s*A Terragni(?: Consulting)? Case(?: Study)?.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–")

    safe_case = public_case_title(cleaned)
    return f"Terragni case study: {safe_case}" if safe_case else "Terragni case study"


def _load_catalog() -> dict[str, list[dict[str, Any]]]:
    """All active offerings and frameworks, cached for 15 minutes."""
    with _CATALOG_LOCK:
        cached = _CATALOG_CACHE["value"]
        if cached is not None and time.time() - _CATALOG_CACHE["loaded_at"] < _CATALOG_SECONDS:
            return cached

        from backend.database.connection import get_connection
        from backend.retrieval.journey_retrieval import _load_master_entity_catalogs

        connection = get_connection()
        try:
            offerings, frameworks = _load_master_entity_catalogs(connection)
        finally:
            connection.close()

        value = {"offerings": offerings, "frameworks": frameworks}
        _CATALOG_CACHE["value"] = value
        _CATALOG_CACHE["loaded_at"] = time.time()
        return value


def _clip(value: Any, limit: int) -> str:
    text = _clean(value)
    return text[:limit]


PROFILE_PATH = Path(__file__).resolve().parents[1] / "data" / "company_profile.md"
_PROFILE_CACHE: dict[str, Any] = {"mtime": None, "sections": []}


def load_company_profile() -> list[dict[str, Any]]:
    """
    Sections of backend/data/company_profile.md, one per "## " heading.

    The profile holds company facts that are not in the uploaded case
    studies (brand colours, the name, contact details, impact...). It is
    re-read automatically when the file changes.
    """
    try:
        mtime = PROFILE_PATH.stat().st_mtime
    except OSError:
        return []

    if _PROFILE_CACHE["mtime"] == mtime:
        return _PROFILE_CACHE["sections"]

    text = PROFILE_PATH.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    sections = []
    for index, block in enumerate(re.split(r"^## ", text, flags=re.MULTILINE)[1:], start=1):
        heading, _, body = block.partition("\n")
        body = " ".join(body.split())
        if body:
            sections.append(
                {
                    "chunk_id": f"profile-{index}",
                    "kind": "company_profile",
                    "source": "Terragni company profile",
                    "topic": heading.strip(),
                    "text": body,
                }
            )

    _PROFILE_CACHE["mtime"] = mtime
    _PROFILE_CACHE["sections"] = sections
    return sections


def _build_package(question: str) -> dict[str, Any]:
    journey = retrieve_journey_evidence(
        question,
        top_k=12,
        minimum_similarity=float(os.getenv("KNOWLEDGE_MIN_SIMILARITY", "0.45")),
    )

    brochure_hits = [
        hit
        for hit in semantic_search(
            question,
            top_k=40,
            minimum_similarity=float(os.getenv("BROCHURE_MIN_SIMILARITY", "0.40")),
        )
        if _is_brochure((hit.get("document") or {}).get("title"))
    ][:4]

    chunks: dict[int, dict[str, Any]] = {}

    for hit in brochure_hits:
        chunks[int(hit["chunk_id"])] = {
            "chunk_id": int(hit["chunk_id"]),
            "kind": "brochure",
            "source": public_source_name((hit.get("document") or {}).get("title")),
            "text": _clip(hit.get("chunk_text"), 420),
        }

    for item in journey.get("evidence", [])[:4]:
        chunk_id = item.get("chunk_id")
        if chunk_id is None or int(chunk_id) in chunks:
            continue
        document_title = (item.get("document") or {}).get("title")
        chunks[int(chunk_id)] = {
            "chunk_id": int(chunk_id),
            "kind": "brochure" if _is_brochure(document_title) else "case_study",
            "source": public_source_name(document_title),
            "text": _clip(remove_client_names(item.get("text")), 420),
        }

    case_studies = []
    for case in journey.get("case_studies", [])[:3]:
        case_id = case.get("case_study_id")
        if case_id is None:
            continue
        case_studies.append(
            {
                "case_study_id": case_id,
                "title": public_case_title(case.get("public_title") or case.get("title")),
                "summary": _clip(remove_client_names(case.get("summary") or case.get("challenge")), 260),
                "outcome": _clip(remove_client_names(case.get("business_outcome")), 200),
            }
        )

    catalog = _load_catalog()

    return {
        "company_profile": load_company_profile(),
        "chunks": list(chunks.values()),
        "case_studies": case_studies,
        "offerings": [
            {
                "offering_id": item["offering_id"],
                "name": item.get("name"),
                "description": _clip(item.get("description"), 220),
            }
            for item in catalog["offerings"]
        ],
        "frameworks": [
            {
                "framework_id": item["framework_id"],
                "name": item.get("name"),
                "description": _clip(item.get("description"), 180),
            }
            for item in catalog["frameworks"]
        ],
    }


_SYSTEM_PROMPT = """
You answer questions about Terragni Consulting for visitors to its website.
Terragni is a behavioural-science consulting firm.

Rules:
1. Use ONLY the supplied Terragni material (company_profile, chunks, catalogue). It is the only source of truth.
   The company_profile answers questions about Terragni itself: who it is, beliefs, approach,
   services, industries, impact, the name, brand colours, logo, font, publications and contact details.
2. Never invent services, methods, clients, numbers, results or claims.
3. Never name a client company. Describe them generally, e.g. "a leading private bank".
4. If the material does not answer the question, set answer_found=false and say so honestly.
5. Write in plain, simple English for a busy senior banker. No jargon, no internal IDs.
6. Tailor the emphasis to the visitor's role and industry when it is natural.
7. Return ONLY valid JSON.
""".strip()


def _build_user_prompt(*, question: str, industry: str | None, role: str | None, package: dict[str, Any]) -> str:
    schema = {
        "answer_found": True,
        "title": "short page title",
        "answer": "2-3 sentence direct answer",
        "for_your_role": "1-2 sentences on why this matters to the visitor's role",
        "key_points": ["up to 4 short points"],
        "how_it_helps": [{"title": "2-5 words", "text": "1-2 plain sentences"}],
        "deep_dive": [{"heading": "a question the visitor would ask next", "text": "2-3 plain sentences answering it"}],
        "how_it_works": [{"title": "2-4 words", "text": "1 sentence"}],
        "offerings": [{"offering_id": 0, "name": "", "what_it_is": "", "why_relevant": ""}],
        "frameworks": [{"framework_id": 0, "name": "", "what_it_is": ""}],
        "case_studies": [{"case_study_id": 0, "why_relevant": "", "what_was_done": "1-2 plain sentences"}],
        "suggested_questions": ["up to 3 follow-up questions the visitor could ask"],
        "source_chunk_ids": [0],
    }

    return f"""
VISITOR
Industry: {industry or "Not provided"}
Role: {role or "Not provided"}
Question: {question}

OUTPUT SHAPE
{json.dumps(schema)}

TERRAGNI MATERIAL
{json.dumps(package, ensure_ascii=False)}

DECISION RULES
- Pick at most 3 offerings, 2 frameworks and 2 case studies, only from the material above.
- how_it_helps: 2-3 concrete ways Terragni helps with what the visitor asked,
  each different from the answer and key_points.
- deep_dive: 2-3 short explainers that take the visitor deeper, each answering
  a natural follow-up (e.g. "What makes this different?", "What would a bank
  actually get?"). Only use facts from the material.
- how_it_works: 3-4 steps describing how working with Terragni on this
  typically unfolds, if the material supports it; otherwise leave empty.
- case_studies what_was_done: what Terragni did there, in plain words.
- PLAIN LANGUAGE: the visitor does not know Terragni's product, tool or framework
  names. In title, answer, key_points and how_it_helps describe what is done and
  why it matters; do NOT use offering/framework names or acronyms (e.g. "JUMP",
  "EAS") unless the visitor asked about that name. Only the offerings/frameworks
  arrays may hold those names.
- Never repeat the same idea in two fields.
- source_chunk_ids must list the chunk_id values you relied on.
- Any question about Terragni the company (including brand colours, logo, name, contact,
  office, publications) should be answered from company_profile when it covers it.
- Cite company_profile sections by their chunk_id (e.g. "profile-11") in source_chunk_ids.
- If the question is not about Terragni or cannot be answered from the material,
  set answer_found=false, keep answer to one honest sentence, and suggest related questions.
""".strip()


def answer_knowledge_question(
    *,
    question: str,
    industry: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    """Run the Knowledge path and return a public-safe page structure."""
    question = _clean(question)
    if not question:
        raise ValueError("question is required")

    package = _build_package(question)

    raw = _call_groq(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(
            question=question,
            industry=_clean(industry) or None,
            role=_clean(role) or None,
            package=package,
        ),
    )

    return _normalise(raw, package)


def _safe(text: Any) -> str:
    return sanitize_public_text(remove_client_names(_clean(text)))


def _normalise(raw: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    offerings_by_id = {str(item["offering_id"]): item for item in package["offerings"]}
    frameworks_by_id = {str(item["framework_id"]): item for item in package["frameworks"]}
    cases_by_id = {str(item["case_study_id"]): item for item in package["case_studies"]}
    chunks_by_id = {
        str(item["chunk_id"]): item
        for item in package["chunks"] + package.get("company_profile", [])
    }

    offerings = []
    for item in raw.get("offerings") or []:
        if not isinstance(item, dict):
            continue
        known = offerings_by_id.get(str(item.get("offering_id")))
        if not known:
            continue
        offerings.append(
            {
                "name": _safe(known.get("name")),
                "what_it_is": _safe(item.get("what_it_is")) or _safe(known.get("description")),
                "why_relevant": _safe(item.get("why_relevant")),
            }
        )

    frameworks = []
    for item in raw.get("frameworks") or []:
        if not isinstance(item, dict):
            continue
        known = frameworks_by_id.get(str(item.get("framework_id")))
        if not known:
            continue
        frameworks.append(
            {
                "name": _safe(known.get("name")),
                "what_it_is": _safe(item.get("what_it_is")) or _safe(known.get("description")),
            }
        )

    case_studies = []
    for item in raw.get("case_studies") or []:
        if not isinstance(item, dict):
            continue
        known = cases_by_id.get(str(item.get("case_study_id")))
        if not known:
            continue
        case_studies.append(
            {
                "title": known["title"],
                "summary": _safe(known.get("summary")),
                "outcome": _safe(known.get("outcome")),
                "why_relevant": _safe(item.get("why_relevant")),
                "what_was_done": _safe(item.get("what_was_done")),
            }
        )

    sources = []
    for chunk_id in raw.get("source_chunk_ids") or []:
        known = chunks_by_id.get(str(chunk_id))
        if known and known["source"] not in sources:
            sources.append(known["source"])

    answer_found = bool(raw.get("answer_found")) and bool(_clean(raw.get("answer")))

    return {
        "answer_found": answer_found,
        "title": _safe(raw.get("title")) or "What Terragni can tell you",
        "answer": _safe(raw.get("answer")),
        "key_points": [_safe(x) for x in (raw.get("key_points") or [])[:4] if _safe(x)],
        "for_your_role": _safe(raw.get("for_your_role")),
        "deep_dive": [
            {"heading": _safe(item.get("heading")), "text": _safe(item.get("text"))}
            for item in (raw.get("deep_dive") or [])[:3]
            if isinstance(item, dict) and _safe(item.get("text"))
        ],
        "how_it_works": [
            {"title": _safe(item.get("title")), "text": _safe(item.get("text"))}
            for item in (raw.get("how_it_works") or [])[:4]
            if isinstance(item, dict) and (_safe(item.get("title")) or _safe(item.get("text")))
        ],
        "how_it_helps": [
            {"title": _safe(item.get("title")), "text": _safe(item.get("text"))}
            for item in (raw.get("how_it_helps") or [])[:3]
            if isinstance(item, dict) and (_safe(item.get("title")) or _safe(item.get("text")))
        ],
        "offerings": offerings[:3],
        "frameworks": frameworks[:2],
        "case_studies": case_studies[:2],
        "suggested_questions": [
            _safe(x) for x in (raw.get("suggested_questions") or [])[:3] if _safe(x)
        ],
        "sources": sources[:4],
    }
