from __future__ import annotations
import os
import threading
from pathlib import Path
import markdown as md_lib
from ..journey_service import (
    run_journey,
    continue_journey,
)
from ..journey.intent import (
    detect_intent,
    is_supported_industry,
)
from ..journey.knowledge import answer_knowledge_question
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
)
from .config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    PORT,
    DEBUG,
)
from ..database.connection import get_connection
from .router import (
    KB,
    load_case_study_content,
)
from .confidentiality import (
    public_case_title,
    redact_confidential_text,
    register_client_names,
    remove_client_names,
    sanitize_public_page,
    sanitize_public_evidence,
    sanitize_public_text,
)
from .mailer import send_lead_emails
from .plain_language import plain_language
from .leads import (
    log_visit,
    save_lead,
    validate_lead,
)
# ============================================================
# FLASK APPLICATION
# ============================================================
# Resolve the project root from this file instead of relying on the
# directory from which Flask happens to be started.
BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

MAX_INPUT_CHARS = 6000

app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR / "templates"),
    static_folder=str(FRONTEND_DIR / "static"),
    static_url_path="/static",
)
# ============================================================
# STARTUP WARM-UP
# ============================================================
def _warm_up() -> None:
    """
    Load the slow, rarely-changing data once, in the background:
    the FastEmbed model, chunk embeddings from Supabase, offering/framework
    embeddings, the knowledge catalogue and client names for the
    public-page blocklist.

    Without this the FIRST visitor question has to do all of it inside the
    request and can hit the gunicorn / browser timeout.
    """
    try:
        connection = get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT DISTINCT client_name FROM case_study "
                "WHERE client_name IS NOT NULL"
            )
            register_client_names(row[0] for row in cursor)
            cursor.close()
        finally:
            connection.close()

        from ..retrieval.journey_retrieval import retrieve_journey_evidence
        from ..journey.knowledge import _load_catalog

        retrieve_journey_evidence(
            "banking customer engagement",
            top_k=4,
            minimum_similarity=0.5,
        )
        _load_catalog()
        app.logger.info("Terragni warm-up complete")
    except Exception:
        app.logger.exception("Terragni warm-up failed; first query will be slower")


if os.getenv("WARM_UP_ON_START", "true").strip().lower() == "true":
    threading.Thread(target=_warm_up, daemon=True).start()
# ============================================================
# JSON ERRORS FOR THE API
# ============================================================
# Any crash inside an /api/ route must come back as JSON. Before, Flask
# returned an HTML error page and the website could only say
# "The server returned an invalid response".
from werkzeug.exceptions import HTTPException  # noqa: E402


@app.errorhandler(Exception)
def _api_error(exc):
    if isinstance(exc, HTTPException) and not request.path.startswith("/api/"):
        return exc
    status = exc.code if isinstance(exc, HTTPException) else 500
    if status >= 500:
        app.logger.exception("Unhandled error on %s", request.path)
    if not request.path.startswith("/api/"):
        return exc if isinstance(exc, HTTPException) else ("Internal Server Error", 500)
    return jsonify({
        "ok": False,
        "error": "The Terragni AI hit an internal error. Please try again.",
        "details": f"{type(exc).__name__}: {exc}",
    }), status


# ============================================================
# PUBLIC PAGES
# ============================================================
@app.route("/", strict_slashes=False)
def home():
    return render_template(
        "index.html"
    )
@app.route("/contact", strict_slashes=False)
def contact():
    return render_template(
        "contact.html"
    )
@app.route("/about", strict_slashes=False)
def about():
    return render_template(
        "about.html"
    )
# ============================================================
# HEALTH CHECK
# ============================================================
def _memory_mb() -> dict:
    """Current and peak memory of this process (Render Starter = 512 MB)."""
    info = {}
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    key = "current" if line.startswith("VmRSS") else "peak"
                    info[key] = round(int(line.split()[1]) / 1024)
    except OSError:
        pass
    return info


def _step(label: str) -> None:
    print(f"[step] {label} | memory {_memory_mb().get('current')} MB", flush=True)


@app.route("/api/debug/<step>")
def api_debug(step: str):
    """
    Temporary diagnostics: run ONE part of the answer pipeline.
      /api/debug/embed     - embed a test sentence
      /api/debug/retrieve  - full Supabase retrieval
      /api/debug/groq      - one tiny Groq call
    """
    import time as _time
    started = _time.time()
    _step(f"debug {step}: start")
    question = "Our affluent banking customers are happy but not engaged."
    if step == "embed":
        from ..retrieval.semantic_search import create_query_embedding
        detail = f"{len(create_query_embedding(question + ' ' + str(started)))} dims"
    elif step == "retrieve":
        from ..retrieval.journey_retrieval import retrieve_journey_evidence
        detail = retrieve_journey_evidence(question)["retrieval"]
    elif step == "groq":
        from ..journey_service import _call_groq
        detail = _call_groq(
            system_prompt='Reply with JSON {"ok": true}.',
            user_prompt="Say ok.",
        )
    else:
        return jsonify({"ok": False, "error": "unknown step"}), 404
    _step(f"debug {step}: done")
    return jsonify({
        "ok": True,
        "step": step,
        "detail": detail,
        "seconds": round(_time.time() - started, 2),
        "memory_mb": _memory_mb(),
    })


@app.route("/api/health")
def health():
    """
    Production health check.
    Supabase PostgreSQL is the source of truth for the production journey.
    Open https://<your-app>.onrender.com/api/health to diagnose a deploy.
    """
    from ..retrieval.semantic_search import DB_EMBEDDING_MODEL, FASTEMBED_MODEL
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM document_chunk"
        )
        document_chunks = int(
            cursor.fetchone()[0]
        )
        cursor.execute(
            "SELECT COUNT(*) FROM document_chunk_embedding"
        )
        embeddings = int(
            cursor.fetchone()[0]
        )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM document_chunk_embedding
            WHERE model_name = %s
            """,
            (DB_EMBEDDING_MODEL,),
        )
        nomic_embeddings = int(
            cursor.fetchone()[0]
        )
        return jsonify({
            "memory_mb": _memory_mb(),
            "ok": bool(document_chunks and nomic_embeddings and GROQ_API_KEY),
            "database": "connected",
            "query_embedding_model": FASTEMBED_MODEL,
            "stored_embedding_model": DB_EMBEDDING_MODEL,
            "llm_configured": bool(
                GROQ_API_KEY
            ),
            "model": GROQ_MODEL,
            "retrieval_backend": "supabase_fastembed",
            "document_chunks": document_chunks,
            "embeddings": embeddings,
            "nomic_embeddings": nomic_embeddings,
        })
    except Exception as exc:
        app.logger.exception(
            "Production health check failed"
        )
        return jsonify({
            "ok": False,
            "database": "error",
            "llm_configured": bool(
                GROQ_API_KEY
            ),
            "model": GROQ_MODEL,
            "retrieval_backend": "supabase_fastembed",
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }), 503
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if connection:
                connection.close()
        except Exception:
            pass
# PUBLIC CASE-STUDY REPRESENTATION
# ============================================================
def build_public_case_study(
    case_study: dict,
) -> dict:
    """
    Convert an internal Terragni case-study record into a
    customer-facing record.
    Internal IDs are deliberately NOT returned here.
    The public website receives only understandable,
    non-identifying information.
    """
    if not isinstance(
        case_study,
        dict,
    ):
        return {}
    # --------------------------------------------------------
    # Public title
    # --------------------------------------------------------
    title = (
        case_study.get("public_title")
        or case_study.get("title")
        or case_study.get("name")
        or case_study.get("public_name")
        or ""
    )
    # --------------------------------------------------------
    # Public description
    # --------------------------------------------------------
    description = (
        case_study.get("public_description")
        or case_study.get("description")
        or case_study.get("summary")
        or case_study.get("finding")
        or ""
    )
    # --------------------------------------------------------
    # Optional public industry/context
    # --------------------------------------------------------
    industry = (
        case_study.get("public_industry")
        or case_study.get("industry")
        or ""
    )
    # --------------------------------------------------------
    # Optional documented outcome
    # --------------------------------------------------------
    outcome = (
        case_study.get("outcome")
        or ""
    )
    public_case = {
        "title": public_case_title(
            title
        ),
        "description": sanitize_public_text(
            remove_client_names(description)
        ),
        "industry": sanitize_public_text(
            industry
        ),
        "outcome": sanitize_public_text(
            remove_client_names(outcome)
        ),
    }
    # Remove empty optional values.
    public_case = {
        key: value
        for key, value in public_case.items()
        if value
    }
    return public_case
def build_public_case_studies(
    case_studies: list[dict],
) -> list[dict]:
    """
    Build the complete customer-facing case-study list.
    No internal case-study IDs are returned.
    """
    public_cases = []
    for case_study in case_studies:
        public_case = build_public_case_study(
            case_study
        )
        if public_case:
            public_cases.append(
                public_case
            )
    return public_cases[:3]
# ============================================================
# CHALLENGE RESPONSE (shared by every challenge route)
# ============================================================
def _public(text) -> str:
    return sanitize_public_text(remove_client_names(text or ""))


def _plain_visitor_text(value, skip=("offerings", "frameworks")):
    """Apply the plain-language filter to every text the visitor reads."""
    if isinstance(value, str):
        return plain_language(value)
    if isinstance(value, list):
        return [_plain_visitor_text(item, skip) for item in value]
    if isinstance(value, dict):
        return {
            key: item if key in skip else _plain_visitor_text(item, skip)
            for key, item in value.items()
        }
    return value


def _public_records(items, *keys: str, limit: int = 4) -> list[dict]:
    """Public-safe list of small text records (reasons, steps, ideas...)."""
    values = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        record = {key: _public(item.get(key)) for key in keys}
        if any(record.values()):
            values.append(record)
    return values[:limit]


def _public_journey(items) -> list[dict]:
    stages = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and _public(item.get("stage")):
            stages.append({
                "stage": _public(item.get("stage")),
                "what_happens": _public(item.get("what_happens")),
                "friction": bool(item.get("friction")),
            })
    return stages[:5]


def _public_entities(result: dict, key: str, name_key: str) -> list[dict]:
    """Public-safe list of case studies, offerings or frameworks."""
    values = []
    raw_entities = result.get(key, [])
    if not isinstance(raw_entities, list):
        return values
    alternate_name_keys = {
        "title": ("title", "name", "public_title"),
        "name": ("name", "offering_name", "framework_name", "public_name"),
    }.get(name_key, (name_key,))
    for entity in raw_entities:
        if isinstance(entity, str):
            public_name = entity.strip()
            why_relevant = ""
        elif isinstance(entity, dict):
            public_name = ""
            for candidate in alternate_name_keys:
                candidate_value = entity.get(candidate)
                if candidate_value:
                    public_name = str(candidate_value).strip()
                    break
            why_relevant = str(
                entity.get("why_relevant")
                or entity.get("relevance")
                or ""
            ).strip()
        else:
            continue
        # Case-study titles in the database can carry client names.
        public_name = (
            public_case_title(public_name)
            if key == "case_studies"
            else _public(public_name)
        )
        if not public_name:
            continue
        item = {name_key: public_name}
        if _public(why_relevant):
            item["why_relevant"] = _public(why_relevant)
        if isinstance(entity, dict):
            for extra in ("their_challenge", "what_was_done", "result"):
                if _public(entity.get(extra)):
                    item[extra] = _public(entity.get(extra))
        values.append(item)
    return values[:3]


def build_challenge_response(
    result: dict,
    *,
    industry: str,
    role: str,
) -> dict:
    """Turn a run_journey() result into the public /api/query response."""
    has_match = bool(result.get("has_terragni_solved_this"))
    questions = [
        str(q)
        for q in result.get("probing_questions", [])
        if str(q).strip()
    ][:3]
    match_status = (
        "matched"
        if has_match
        else (
            "needs_clarification"
            if questions
            else "not_supported"
        )
    )
    conceptual = result.get("conceptual_translation", {})
    if not isinstance(conceptual, dict):
        conceptual = {}
    return _plain_visitor_text({
        "ok": True,
        "match_status": match_status,
        "industry": sanitize_public_text(industry),
        "role": sanitize_public_text(role),
        "conceptual_translation": {
            "business_problem": _public(
                conceptual.get("business_problem")
            ),
            "confidence": conceptual.get("confidence", "low"),
        },
        "has_terragni_solved_this": has_match,
        "match_confidence": result.get("match_confidence", "low"),
        "summary": _public(result.get("summary")),
        "perspective": _public(result.get("perspective")),
        "for_your_role": _public(result.get("for_your_role")),
        "what_you_see": _public(result.get("what_you_see")),
        "journey": _public_journey(result.get("journey")),
        "why_it_happens": _public_records(
            result.get("why_it_happens"), "title", "explanation", "customer_thought"),
        "approach": _public_records(result.get("approach"), "title", "what_we_do", "you_get"),
        "early_ideas": _public_records(result.get("early_ideas"), "title", "text", limit=3),
        "expected_outcomes": _public_records(
            result.get("expected_outcomes"), "outcome", "how_to_measure", limit=3),
        "discussion_questions": [
            _public(x)
            for x in result.get("discussion_questions", [])
            if isinstance(x, str) and _public(x)
        ][:3],
        "areas_of_concern": [
            _public(x)
            for x in result.get("areas_of_concern", [])
            if isinstance(x, str) and x.strip()
        ],
        "case_studies": _public_entities(result, "case_studies", "title"),
        "offerings": _public_entities(result, "offerings", "name"),
        "frameworks": _public_entities(result, "frameworks", "name"),
        "probing_questions": [_public(x) for x in questions],
        "closing": _public(result.get("closing")),
        "next_step": result.get("next_step"),
        "retrieval": result.get("retrieval", {}),
    }, skip=("offerings", "frameworks", "retrieval", "match_status", "next_step", "industry", "role"))
# ============================================================
# AI BUSINESS CHALLENGE
# ============================================================
@app.route(
    "/api/query",
    methods=["POST"],
)
def api_query():
    """Run the production Terragni semantic journey."""
    payload = request.get_json(silent=True) or {}
    challenge = str(
        payload.get("challenge")
        or payload.get("query")
        or ""
    ).strip()
    industry = str(
        payload.get("industry") or ""
    ).strip()
    role = str(
        payload.get("role")
        or payload.get("designation")
        or ""
    ).strip()
    if not challenge:
        return jsonify({
            "ok": False,
            "error": "Please describe your business challenge.",
        }), 400
    if len(challenge) > MAX_INPUT_CHARS:
        return jsonify({
            "ok": False,
            "error": (
                "Please keep the challenge description below "
                "6,000 characters."
            ),
        }), 400
    try:
        safe_challenge = redact_confidential_text(challenge)
        if not safe_challenge:
            return jsonify({
                "ok": False,
                "error": (
                    "Please describe the business challenge without "
                    "confidential identifying information."
                ),
            }), 400
        result = run_journey(
            industry=industry,
            role=role,
            challenge=safe_challenge,
        )
        return jsonify(
            build_challenge_response(result, industry=industry, role=role)
        )
    except Exception as exc:
        app.logger.exception(
            "Terragni journey query failed"
        )
        return jsonify({
            "ok": False,
            "error": (
                "The Terragni AI journey could not "
                "build a grounded answer."
            ),
            "details": (
                f"{type(exc).__name__}: {exc}"
            ),
        }), 503
@app.route(
    "/api/query/continue",
    methods=["POST"],
)
def api_query_continue():
    """Continue after the visitor answers probing questions."""
    payload = request.get_json(silent=True) or {}
    original_challenge = str(
        payload.get("original_challenge")
        or payload.get("challenge")
        or ""
    ).strip()
    probing_answers = payload.get(
        "probing_answers",
        [],
    )
    if not original_challenge:
        return jsonify({
            "ok": False,
            "error": "original_challenge is required.",
        }), 400
    if not isinstance(probing_answers, list):
        return jsonify({
            "ok": False,
            "error": "probing_answers must be a list.",
        }), 400
    probing_answers = [
        str(x).strip()
        for x in probing_answers[:3]
        if str(x).strip()
    ]
    if not probing_answers:
        return jsonify({
            "ok": False,
            "error": "At least one probing answer is required.",
        }), 400
    industry = str(payload.get("industry") or "").strip()
    role = str(
        payload.get("role")
        or payload.get("designation")
        or ""
    ).strip()
    try:
        result = continue_journey(
            industry=industry,
            role=role,
            original_challenge=redact_confidential_text(
                original_challenge
            ),
            probing_answers=[
                redact_confidential_text(x)
                for x in probing_answers
            ],
        )
        return jsonify(
            build_challenge_response(result, industry=industry, role=role)
        )
    except Exception as exc:
        app.logger.exception(
            "Terragni journey continuation failed"
        )
        return jsonify({
            "ok": False,
            "error": "The Terragni journey could not continue.",
            "details": (
                f"{type(exc).__name__}: {exc}"
            ),
        }), 503
# ============================================================
# ONE ENTRY POINT FOR BOTH PATHS
# ============================================================
OUT_OF_SCOPE_QUESTIONS = [
    "What does Terragni do?",
    "How does Terragni use behavioural science?",
    "What services does Terragni offer?",
]


@app.route(
    "/api/ask",
    methods=["POST"],
)
def api_ask():
    """
    Single entry point used by the website.

    Body: {industry, role, text, mode, force}
      mode  - the button the visitor chose: "challenge" or "knowledge"
      force - true to skip intent detection (used after clarification)

    Response "path" tells the page what to render:
      "challenge"    - same fields as /api/query
      "knowledge"    - fields under "knowledge"
      "out_of_scope" - the industry is outside this banking prototype
    """
    payload = request.get_json(silent=True) or {}
    text = str(
        payload.get("text")
        or payload.get("challenge")
        or payload.get("query")
        or ""
    ).strip()
    industry = str(payload.get("industry") or "").strip()
    role = str(
        payload.get("role")
        or payload.get("designation")
        or ""
    ).strip()
    mode = str(payload.get("mode") or "").strip().lower()
    force = bool(payload.get("force"))

    if not industry or not role:
        return jsonify({
            "ok": False,
            "error": "Please tell us your industry and your role first.",
        }), 400
    if not text:
        return jsonify({
            "ok": False,
            "error": "Please type your question or describe your challenge.",
        }), 400
    if len(text) > MAX_INPUT_CHARS:
        return jsonify({
            "ok": False,
            "error": "Please keep your text below 6,000 characters.",
        }), 400

    safe_text = redact_confidential_text(text)
    if not safe_text:
        return jsonify({
            "ok": False,
            "error": (
                "Please describe it without confidential "
                "identifying information."
            ),
        }), 400

    industry_supported = is_supported_industry(industry)
    _step("ask: received")

    try:
        if force and mode in ("challenge", "knowledge"):
            intent = {"intent": mode, "confidence": "high", "method": "visitor_choice"}
        else:
            intent = detect_intent(safe_text, chosen_path=mode)
        _step(f"ask: intent = {intent.get('intent')} ({intent.get('method')})")

        path = "challenge" if intent["intent"] == "challenge" else "knowledge"

        # The prototype only diagnoses banking challenges.
        if path == "challenge" and not industry_supported:
            log_visit(
                industry=industry,
                role=role,
                path="challenge",
                outcome="out_of_scope",
                text=safe_text,
            )
            return jsonify({
                "ok": True,
                "path": "out_of_scope",
                "intent": intent,
                "industry": sanitize_public_text(industry),
                "role": sanitize_public_text(role),
                "message": (
                    "This first version of the Solution Mapper covers "
                    "banking only, so we cannot match your challenge to "
                    "past work yet. You can still learn about Terragni "
                    "below, or talk to our team directly."
                ),
                "suggested_questions": OUT_OF_SCOPE_QUESTIONS,
            })

        if path == "knowledge":
            knowledge = answer_knowledge_question(
                question=safe_text,
                industry=industry,
                role=role,
            )
            log_visit(
                industry=industry,
                role=role,
                path="knowledge",
                outcome="answered" if knowledge["answer_found"] else "no_match",
                text=safe_text,
            )
            return jsonify({
                "ok": True,
                "path": "knowledge",
                "intent": intent,
                "industry": sanitize_public_text(industry),
                "role": sanitize_public_text(role),
                "industry_supported": industry_supported,
                # A mixed question gets the answer first, then an offer to
                # diagnose the visitor's own challenge.
                "offer_challenge": intent["intent"] == "mixed",
                "knowledge": _plain_visitor_text(
                    knowledge, skip=("offerings", "frameworks", "sources")),
            })

        _step("ask: running journey")
        result = run_journey(
            industry=industry,
            role=role,
            challenge=safe_text,
        )
        _step("ask: journey done")
        response = build_challenge_response(result, industry=industry, role=role)
        log_visit(
            industry=industry,
            role=role,
            path="challenge",
            outcome={
                "matched": "matched",
                "needs_clarification": "needs_clarification",
            }.get(response["match_status"], "no_match"),
            text=safe_text,
        )
        response["path"] = "challenge"
        response["intent"] = intent
        return jsonify(response)
    except Exception as exc:
        app.logger.exception("Terragni /api/ask failed")
        return jsonify({
            "ok": False,
            "error": (
                "The Terragni AI could not build a grounded answer "
                "right now. Please try again in a minute."
            ),
            "details": f"{type(exc).__name__}: {exc}",
        }), 503
# ============================================================
# CONTACT FORM (LEADS)
# ============================================================
@app.route(
    "/api/lead",
    methods=["POST"],
)
def api_lead():
    payload = request.get_json(silent=True) or {}
    errors = validate_lead(payload)
    if errors:
        return jsonify({
            "ok": False,
            "error": " ".join(errors),
        }), 400
    try:
        lead = save_lead(payload)
    except Exception:
        app.logger.exception("Saving lead failed")
        return jsonify({
            "ok": False,
            "error": (
                "We could not save your details. Please email "
                "engage@terragni.co instead."
            ),
        }), 500
    email_sent = send_lead_emails(lead)
    return jsonify({
        "ok": True,
        "reference": lead["reference"],
        "email_sent": email_sent,
        "email": lead["email"],
    })
# ============================================================
# CASE STUDY DETAIL
# ============================================================
@app.route(
    "/api/case-study/<case_study_id>"
)
def api_case_study_detail(
    case_study_id: str,
):
    # --------------------------------------------------------
    # Validate ID
    # --------------------------------------------------------
    if (
        not case_study_id
        or "/" in case_study_id
        or "\\" in case_study_id
        or ".." in case_study_id
    ):
        return jsonify({
            "error": "Invalid case study."
        }), 400
    # --------------------------------------------------------
    # Only allow IDs that exist in the controlled KB
    # --------------------------------------------------------
    valid_ids = {
        case.get("id")
        for case in KB.get(
            "case_studies",
            []
        )
        if isinstance(case, dict)
    }
    if case_study_id not in valid_ids:
        return jsonify({
            "error": "Case study not found."
        }), 404
    # --------------------------------------------------------
    # Load content
    # --------------------------------------------------------
    content = load_case_study_content(
        case_study_id
    )
    if content is None:
        return jsonify({
            "error": (
                "Case study content unavailable."
            )
        }), 404
    # --------------------------------------------------------
    # Convert Markdown to HTML
    # --------------------------------------------------------
    html = md_lib.markdown(
        content
    )
    # --------------------------------------------------------
    # Sanitize obvious identifying information
    # --------------------------------------------------------
    safe_html = sanitize_public_text(
        remove_client_names(html)
    )
    return jsonify({
        "html": safe_html
    })
# ============================================================
# START SERVER
# ============================================================
if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=PORT,
        debug=DEBUG,
    )
