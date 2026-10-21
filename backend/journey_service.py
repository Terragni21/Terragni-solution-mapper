from __future__ import annotations







"""



Terragni AI Journey Service







Orchestrates:



    visitor context



        -> semantic retrieval (Supabase PostgreSQL + FastEmbed)



        -> Groq evidence-grounded reasoning



        -> structured journey JSON







Important design rules:



- No hard-coded phrase -> offering/case-study routing.



- Supabase PostgreSQL is the source of truth for Terragni knowledge.



- FastEmbed (nomic-embed-text v1.5) embeds the question for semantic retrieval.



- Groq reasons ONLY over the retrieved evidence package.



- If evidence is insufficient, the service asks up to 3 probing questions.



- The service never invents case studies, offerings, frameworks, industries,



  outcomes, or claims that are absent from the supplied evidence.



"""







import json



import os



from typing import Any







from dotenv import load_dotenv



from groq import Groq







from backend.retrieval.journey_retrieval import retrieve_journey_evidence











BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))



load_dotenv(os.path.join(BACKEND_DIR, ".env"))







GROQ_MODEL = os.getenv(



    "GROQ_MODEL",



    os.getenv("GROQ_MODEL_NAME", "openai/gpt-oss-120b"),



).strip()







# Keep the request comfortably below Groq TPM limits.



GROQ_MAX_COMPLETION_TOKENS = max(3600, int(
    os.getenv("JOURNEY_GROQ_MAX_COMPLETION_TOKENS", "3600"))
)

# GPT-OSS reasoning can consume completion tokens. Low reasoning is enough
# for this evidence-grounded journey and leaves sufficient budget for JSON.
GROQ_REASONING_EFFORT = os.getenv(
    "JOURNEY_GROQ_REASONING_EFFORT",
    "low",
).strip().lower()

if GROQ_REASONING_EFFORT not in {"low", "medium", "high"}:
    GROQ_REASONING_EFFORT = "low"







# A semantic result is evidence, not automatically a "solved this" match.



DEFAULT_MATCH_THRESHOLD = float(



    os.getenv("JOURNEY_MATCH_THRESHOLD", "0.55")



)











class JourneyServiceError(RuntimeError):



    """Raised when the journey service cannot complete safely."""











def _clean(value: Any) -> str:



    if value is None:



        return ""



    if hasattr(value, "read"):



        value = value.read()



    return str(value).strip()











def _require_groq_key() -> str:



    key = os.getenv("GROQ_API_KEY", "").strip()



    if not key:



        raise JourneyServiceError(



            "GROQ_API_KEY is not configured in backend/.env"



        )



    return key











def _get_groq_client() -> Groq:



    return Groq(api_key=_require_groq_key())











def _json_from_text(text: str) -> dict[str, Any]:



    """



    Parse strict JSON, tolerating accidental markdown fences or surrounding



    whitespace from an LLM response.



    """



    text = (text or "").strip()







    if text.startswith("```"):



        lines = text.splitlines()







        if lines and lines[0].strip().startswith("```"):



            lines = lines[1:]







        if lines and lines[-1].strip() == "```":



            lines = lines[:-1]







        text = "\n".join(lines).strip()







        if text.lower().startswith("json"):



            text = text[4:].lstrip()







    try:



        value = json.loads(text)



    except json.JSONDecodeError as exc:



        # Last-resort extraction of a single JSON object.



        start = text.find("{")



        end = text.rfind("}")







        if start < 0 or end <= start:



            raise JourneyServiceError(



                "Groq returned invalid JSON."



            ) from exc







        try:



            value = json.loads(text[start : end + 1])



        except json.JSONDecodeError as nested_exc:



            raise JourneyServiceError(



                "Groq returned invalid JSON."



            ) from nested_exc







    if not isinstance(value, dict):



        raise JourneyServiceError(



            "Groq response must be a JSON object."



        )







    return value













def _compact_evidence_package(

    package: dict[str, Any],

) -> dict[str, Any]:

    """

    Build a deliberately small evidence package for Groq.



    Oracle remains the source of truth. This function only removes repetition

    and clips long text so the LLM request stays comfortably below Groq TPM

    limits.

    """



    def clip(value: Any, limit: int = 300) -> str | None:

        value = _clean(value)

        return value[:limit] if value else None



    compact_cases: list[dict[str, Any]] = []



    # The two strongest cases: the model may select up to two.

    for case in package.get("case_studies", [])[:2]:

        compact_cases.append(

            {

                "case_study_id": case.get("case_study_id"),

                "case_study_code": case.get("case_study_code"),

                "title": clip(case.get("public_title") or case.get("title"), 140),

                "similarity": case.get("best_similarity"),

                "summary": clip(case.get("summary"), 260),

                "challenge": clip(case.get("challenge"), 300),

                "objective": clip(case.get("objective"), 260),

                "approach": clip(case.get("approach"), 300),

                "key_finding": clip(case.get("key_finding"), 300),

                "solution": clip(case.get("solution"), 300),

                "business_outcome": clip(case.get("business_outcome"), 240),

                "relationships": case.get("relationships", {}),

            }

        )



    compact_evidence: list[dict[str, Any]] = []



    for item in package.get("evidence", [])[:6]:

        compact_evidence.append(

            {

                "chunk_id": item.get("chunk_id"),

                "similarity": item.get("similarity"),

                "text": clip(item.get("text"), 480),

                "document": clip(

                    (item.get("document") or {}).get("title"),

                    120,

                ),

                "section": clip(

                    (item.get("section") or {}).get("section_title"),

                    100,

                ),

                "case_study_id": item.get("case_study_id"),

                "evidence_type": clip(item.get("evidence_type"), 80),

                "relevance_note": clip(item.get("relevance_note"), 180),

            }

        )



    return {

        "evidence": compact_evidence,

        "case_studies": compact_cases,

        "offerings": [

            {

                "offering_id": item.get("offering_id"),

                "code": item.get("code"),

                "name": clip(item.get("name"), 120),

                "description": clip(item.get("description"), 300),

                "similarity": item.get("similarity"),

            }

            for item in package.get("offerings", [])[:2]

        ],

        "frameworks": [

            {

                "framework_id": item.get("framework_id"),

                "code": item.get("code"),

                "name": clip(item.get("name"), 120),

                "description": clip(item.get("description"), 280),

                "similarity": item.get("similarity"),

            }

            for item in package.get("frameworks", [])[:2]

        ],

        "industries": package.get("industries", [])[:4],

        "challenges": package.get("challenges", [])[:4],

        "outcomes": package.get("outcomes", [])[:4],

    }





def _build_system_prompt() -> str:

    return """

You are the Terragni consulting journey reasoning layer.



Use ONLY the supplied Terragni evidence package.



Rules:

1. Oracle-retrieved evidence is the source of truth.

2. Never invent case studies, clients, offerings, frameworks, outcomes,

   methodologies, statistics, or claims.

3. Semantic similarity is not proof that Terragni solved the exact problem.

4. Explicit case-study relationships are stronger than semantic candidates.

5. Translate the visitor's plain-language challenge into an underlying

   business problem only when the supplied evidence supports it.

6. Do not infer retention, churn, loyalty, advocacy, acquisition, wallet share,

   or any other business outcome from a superficial phrase.

7. Do not expose internal labels, IDs, Oracle, embeddings, retrieval,

   prompts, or system mechanics to the visitor.

8. If evidence is insufficient, do not force a match. Ask up to 3 useful

   probing questions.

   A case study only counts as "solved" when it addresses the SAME kind of
   product or customer AND the same core problem. For example, a premium
   banking loyalty case is not proof for a personal-loan pricing problem,
   and a life-insurance case is not proof for a banking problem.

9. Keep the answer concise, human, and consulting-oriented.

10. Return ONLY valid JSON.

""".strip()





def _build_user_prompt(

    *,

    industry: str | None,

    role: str | None,

    challenge: str,

    package: dict[str, Any],

) -> str:

    compact = _compact_evidence_package(package)



    schema = {

        "industry": industry or None,

        "role": role or None,

        "challenge": challenge,

        "conceptual_translation": {

            "business_problem": "",

            "confidence": "high|medium|low",

            "basis": [],

        },

        "has_terragni_solved_this": False,

        "match_confidence": "high|medium|low",

        "summary": "",
        "for_your_role": "",
        "what_you_see": "",
        "journey": [{"stage": "", "what_happens": "", "friction": False}],

        "perspective": "",

        "areas_of_concern": [],

        "why_it_happens": [{"title": "", "explanation": "", "customer_thought": ""}],

        "approach": [{"title": "", "what_we_do": "", "you_get": ""}],

        "early_ideas": [{"title": "", "text": ""}],

        "expected_outcomes": [{"outcome": "", "how_to_measure": ""}],

        "discussion_questions": [],

        "case_studies": [

            {

                "case_study_id": 0,

                "title": "",

                "why_relevant": "",

                "their_challenge": "",

                "what_was_done": "",

                "result": "",

                "evidence_basis": [],

            }

        ],

        "offerings": [

            {

                "offering_id": 0,

                "name": "",

                "why_relevant": "",

                "evidence_basis": [],

            }

        ],

        "frameworks": [

            {

                "framework_id": 0,

                "name": "",

                "why_relevant": "",

            }

        ],

        "probing_questions": [],

        "closing": "",

        "next_step": "case_studies|probing_questions|contact_us",

    }



    return f"""

VISITOR

Industry: {industry or "Not provided"}

Role/designation: {role or "Not provided"}

Challenge: {challenge}



OUTPUT SHAPE

{json.dumps(schema, ensure_ascii=False)}



TERRAGNI EVIDENCE

{json.dumps(compact, ensure_ascii=False)}



DECISION RULES

- Return only the JSON object.

- Be clear and specific; no filler and no essays.

- Select at most 2 case studies, 2 offerings and 2 frameworks.

- Every selected entity must exist in the supplied evidence package.

- evidence_basis must refer only to supplied chunk IDs or explicit relationships.

- If the evidence does not credibly support a solved match, set

  has_terragni_solved_this=false and ask up to 3 useful probing questions.

- If there is a credible match, probing_questions must be empty.

- If there is no match and no useful probing question remains, use

  next_step="contact_us".

- Keep labels short; explanations may be 1-2 full sentences.

WRITING THE ANSWER (a detailed page the visitor reads top to bottom)
- summary: 2-3 sentences that directly answer the visitor: what is really
  going on and what Terragni would do. Plain business language.
- for_your_role: 1-2 sentences on why this matters to someone in the
  visitor's role (their goals, targets or pressures).
- what_you_see: 1 sentence describing the symptom as the bank sees it in
  its numbers or day-to-day (the visible problem, not the cause).
- journey: 4-5 customer journey stages relevant to this challenge, in order.
  stage = 1-3 words; what_happens = 1 sentence on what the customer does or
  feels there; friction = true for the 1-2 stages where the problem bites.
- why_it_happens: 3 behavioural or experience reasons behind the problem.
  title = 2-5 words; explanation = 1-2 sentences on why it causes the
  problem; customer_thought = what a customer might think at that moment,
  in first person, under 15 words, no quotation marks.
- approach: 3-4 steps Terragni would take, in order (understand, design,
  test, scale/measure style). title = 2-4 words; what_we_do = 2 sentences
  specific to this challenge; you_get = the concrete thing the bank receives
  from that step (e.g. "a map of the 5 moments where customers give up").
- early_ideas: 2-3 small, low-risk ideas the bank could test early, grounded
  in the behavioural principles in the evidence. title = 2-5 words;
  text = 1 sentence.
- offerings/frameworks why_relevant: 1 sentence on how it helps THIS
  challenge.
- case_studies: their_challenge = 1 sentence on the problem that bank had;
  what_was_done = 1-2 sentences on what Terragni did there; result = the
  business outcome stated in the evidence (empty if none).
- expected_outcomes: 3 items supported by the evidence. outcome = max 6
  words; how_to_measure = the metric the bank would track (e.g. "completion
  rate of the account-opening flow").
- discussion_questions: 3 questions a Terragni consultant would explore in
  a first conversation with this visitor.
- areas_of_concern: 2-4 short labels (1-3 words).
- perspective: 1 sentence, the key insight from a fresh angle.
- closing: 1 short, warm invitation to talk.
- Never invent statistics, percentages, client names or results. Results
  must come from the evidence.
- PLAIN LANGUAGE: the visitor does not know Terragni's product, tool or
  framework names. In every field the visitor reads (everything except the
  offerings/frameworks arrays), NEVER use offering or
  framework names, acronyms or brand names (e.g. write "a quick review of
  the digital journey to find where customers drop off", not "JUMP Probe"
  or "EAS"). Only the offerings/frameworks arrays may hold those names.
- NEVER repeat the same sentence, phrase or idea in two fields. Each field
  must add something new; if there is nothing new, leave it empty.

""".strip()





def _call_groq(
    *,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Call Groq using GPT-OSS with a controlled reasoning budget."""

    client = _get_groq_client()

    def make_request(max_tokens: int):
        return client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.1,
            max_completion_tokens=max_tokens,
            reasoning_effort=GROQ_REASONING_EFFORT,
            include_reasoning=False,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

    try:
        response = make_request(GROQ_MAX_COMPLETION_TOKENS)
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        error_text = str(exc).lower()

        if status_code == 429:
            raise JourneyServiceError(
                "The Terragni AI reasoning service is temporarily rate-limited. "
                "Please wait a few minutes and try the challenge again."
            ) from exc

        if status_code == 400 and (
            "max completion tokens" in error_text
            or "json_validate_failed" in error_text
            or "failed to generate json" in error_text
        ):
            try:
                response = make_request(max(GROQ_MAX_COMPLETION_TOKENS, 5000))
            except Exception as retry_exc:
                retry_status = getattr(retry_exc, "status_code", None)
                if retry_status == 429:
                    raise JourneyServiceError(
                        "The Terragni AI reasoning service is temporarily rate-limited. "
                        "Please wait a few minutes and try again."
                    ) from retry_exc
                raise JourneyServiceError(
                    f"Groq reasoning failed after retry: {retry_exc}"
                ) from retry_exc
        else:
            raise JourneyServiceError(
                f"Groq reasoning failed: {exc}"
            ) from exc

    content = response.choices[0].message.content or ""
    if not content.strip():
        raise JourneyServiceError("Groq returned an empty reasoning response.")

    return _json_from_text(content)


def _normalise_result(



    result: dict[str, Any],



    *,



    challenge: str,



    package: dict[str, Any],



) -> dict[str, Any]:



    """



    Defensive normalization so the Flask API gets a stable shape even when



    Groq omits optional fields.



    """



    result.setdefault("industry", None)



    result.setdefault("role", None)



    result["challenge"] = challenge







    translation = result.get("conceptual_translation")



    if not isinstance(translation, dict):



        translation = {}







    translation.setdefault("business_problem", "")



    translation.setdefault("confidence", "low")



    translation.setdefault("basis", [])







    result["conceptual_translation"] = translation







    result["has_terragni_solved_this"] = bool(



        result.get("has_terragni_solved_this", False)



    )







    if result.get("match_confidence") not in {



        "high",



        "medium",



        "low",



    }:



        result["match_confidence"] = "low"







    for key in (



        "summary",

        "perspective",



        "closing",



    ):



        result[key] = _clean(result.get(key))

    def _records(items: Any, keys: tuple[str, ...], limit: int) -> list[dict[str, str]]:
        cleaned = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, str):
                item = {keys[0]: item}
            if not isinstance(item, dict):
                continue
            record = {key: _clean(item.get(key)) for key in keys}
            if any(record.values()):
                cleaned.append(record)
        return cleaned[:limit]

    for key in ("for_your_role", "what_you_see"):
        result[key] = _clean(result.get(key))

    result["why_it_happens"] = _records(
        result.get("why_it_happens"), ("title", "explanation", "customer_thought"), 3)
    result["approach"] = _records(
        result.get("approach"), ("title", "what_we_do", "you_get"), 4)
    result["early_ideas"] = _records(result.get("early_ideas"), ("title", "text"), 3)
    result["expected_outcomes"] = _records(
        result.get("expected_outcomes"), ("outcome", "how_to_measure"), 3)

    journey = []
    for item in result.get("journey") if isinstance(result.get("journey"), list) else []:
        if isinstance(item, dict) and _clean(item.get("stage")):
            journey.append({
                "stage": _clean(item.get("stage")),
                "what_happens": _clean(item.get("what_happens")),
                "friction": bool(item.get("friction")),
            })
    result["journey"] = journey[:5]

    result["discussion_questions"] = [
        _clean(item)
        for item in (result.get("discussion_questions") or [])[:3]
        if isinstance(item, str) and _clean(item)
    ]







    for key in (



        "areas_of_concern",



        "case_studies",



        "offerings",



        "frameworks",



        "probing_questions",



    ):



        if not isinstance(result.get(key), list):



            result[key] = []







    if result["has_terragni_solved_this"]:



        result["probing_questions"] = []



        result["next_step"] = "case_studies"







    elif result["probing_questions"]:



        result["probing_questions"] = result[



            "probing_questions"



        ][:3]



        result["next_step"] = "probing_questions"







    else:



        result["case_studies"] = []



        result["next_step"] = "contact_us"









    # ------------------------------------------------------------

    # SOURCE-GROUNDED ENTITY FILTERING

    # ------------------------------------------------------------



    allowed_case_ids = {

        str(item.get("case_study_id"))

        for item in package.get("case_studies", [])

        if item.get("case_study_id") is not None

    }



    allowed_offering_ids = {

        str(item.get("offering_id"))

        for item in package.get("offerings", [])

        if item.get("offering_id") is not None

    }



    allowed_framework_ids = {

        str(item.get("framework_id"))

        for item in package.get("frameworks", [])

        if item.get("framework_id") is not None

    }



    case_titles = {
        str(case.get("case_study_id")): case.get("public_title") or case.get("title")
        for case in package.get("case_studies", [])
        if case.get("case_study_id") is not None
    }

    valid_cases = []

    for item in result["case_studies"][:2]:

        if not isinstance(item, dict):

            continue

        if str(item.get("case_study_id")) not in allowed_case_ids:

            continue

        # Use the stored case-study title, not the model's paraphrase.
        known_title = case_titles.get(str(item.get("case_study_id")))
        item["title"] = _clean(known_title or item.get("title"))

        item["why_relevant"] = _clean(item.get("why_relevant"))

        item["their_challenge"] = _clean(item.get("their_challenge"))

        item["what_was_done"] = _clean(item.get("what_was_done"))

        item["result"] = _clean(item.get("result"))

        if not isinstance(item.get("evidence_basis"), list):

            item["evidence_basis"] = []

        valid_cases.append(item)



    valid_offerings = []

    for item in result["offerings"][:2]:

        if not isinstance(item, dict):

            continue

        if str(item.get("offering_id")) not in allowed_offering_ids:

            continue

        item["name"] = _clean(item.get("name"))

        item["why_relevant"] = _clean(item.get("why_relevant"))

        if not isinstance(item.get("evidence_basis"), list):

            item["evidence_basis"] = []

        valid_offerings.append(item)



    valid_frameworks = []

    for item in result["frameworks"][:2]:

        if not isinstance(item, dict):

            continue

        if str(item.get("framework_id")) not in allowed_framework_ids:

            continue

        item["name"] = _clean(item.get("name"))

        item["why_relevant"] = _clean(item.get("why_relevant"))

        valid_frameworks.append(item)



    result["case_studies"] = valid_cases

    result["offerings"] = valid_offerings

    result["frameworks"] = valid_frameworks



    # A "solved" answer without at least one grounded case is not accepted.

    if result["has_terragni_solved_this"] and not result["case_studies"]:

        result["has_terragni_solved_this"] = False



    result["areas_of_concern"] = [

        _clean(item)

        for item in result["areas_of_concern"][:4]

        if _clean(item)

    ]



    result["probing_questions"] = [

        _clean(item)

        for item in result["probing_questions"][:3]

        if _clean(item)

    ]



    result["retrieval"] = {



        "evidence_count": package.get("retrieval", {}).get(



            "evidence_count",



            0,



        ),



        "case_study_count": package.get("retrieval", {}).get(



            "case_study_count",



            0,



        ),



    }







    return result











def run_journey(



    *,



    challenge: str,



    industry: str | None = None,



    role: str | None = None,



    top_k: int = 12,



    minimum_similarity: float = 0.50,



) -> dict[str, Any]:



    """



    Run one complete first-pass Terragni journey.







    This is the function the Flask route should call.



    """



    challenge = _clean(challenge)



    industry = _clean(industry) or None



    role = _clean(role) or None







    if not challenge:



        raise ValueError("challenge is required")







    package = retrieve_journey_evidence(



        challenge,



        top_k=top_k,



        minimum_similarity=minimum_similarity,



    )







    result = _call_groq(



        system_prompt=_build_system_prompt(),



        user_prompt=_build_user_prompt(



            industry=industry,



            role=role,



            challenge=challenge,



            package=package,



        ),



    )







    return _normalise_result(



        result,



        challenge=challenge,



        package=package,



    )











def continue_journey(



    *,



    original_challenge: str,



    probing_answers: list[str],



    industry: str | None = None,



    role: str | None = None,



    top_k: int = 12,



    minimum_similarity: float = 0.50,



) -> dict[str, Any]:



    """



    Re-run conceptual retrieval after the visitor answers probing questions.



    """



    original_challenge = _clean(original_challenge)



    answers = [



        _clean(answer)



        for answer in probing_answers



        if _clean(answer)



    ]







    if not original_challenge:



        raise ValueError("original_challenge is required")







    if not answers:



        raise ValueError("At least one probing answer is required")







    combined_challenge = (



        f"Original business challenge:\n{original_challenge}\n\n"



        "Additional context from the visitor:\n"



        + "\n".join(



            f"{index}. {answer}"



            for index, answer in enumerate(answers, start=1)



        )



    )







    return run_journey(



        challenge=combined_challenge,



        industry=industry,



        role=role,



        top_k=top_k,



        minimum_similarity=minimum_similarity,



    )











if __name__ == "__main__":



    test_challenge = (



        "Our affluent banking customers are happy but not engaged. "



        "What is really driving that gap?"



    )







    print("=" * 90)



    print("TERRAGNI JOURNEY SERVICE TEST")



    print("=" * 90)







    result = run_journey(



        challenge=test_challenge,



        industry="Banking",



        role="Senior Customer Experience Leader",



    )







    print(json.dumps(result, indent=2, ensure_ascii=False))
