"""Strictly grounded AI synthesis for the Terragni website."""

from __future__ import annotations

import json
import re
from typing import Any

from .config import GROQ_API_KEY, GROQ_MODEL


# ============================================================
# GROQ LLM CALL
# ============================================================

def _groq_json_call(
    messages: list[dict],
    max_tokens: int,
) -> str:

    from groq import Groq

    client = Groq(
        api_key=GROQ_API_KEY
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.05,
        max_tokens=max_tokens,
        response_format={
            "type": "json_object"
        },
    )

    return (
        response.choices[0].message.content
        or "{}"
    )


# ============================================================
# SEMANTIC CHALLENGE GATE
# ============================================================

CHALLENGE_GATE_PROMPT = """
You are the semantic applicability gate for a Terragni business
challenge mapper.

Your ONLY job is to determine whether the visitor has described
a sufficiently concrete business challenge that can be evaluated
against the supplied Terragni material.

Do not generate a Terragni solution.
Do not recommend an offering.
Do not choose a framework.
Do not use keyword matching.
Do not assume that a topic mentioned by the visitor is a problem.
Do not work backwards from retrieved evidence to manufacture a
challenge.

A concrete challenge normally contains enough information to
identify some combination of:
- a business situation or context,
- an affected audience or stakeholder,
- an observed behaviour, friction, decision, adoption issue,
  experience issue, or business outcome problem, and
- a meaningful change the visitor is trying to achieve.

The challenge does NOT need to contain every element above.
Judge semantic specificity from the whole request.

Use these decisions:

MATCHED
Use only when BOTH conditions are satisfied:
1. The visitor describes a concrete business situation/problem,
   rather than merely asking for general advice, education, trends,
   ideas, strategy creation, or hypothetical possibilities.
2. The supplied Terragni evidence contains a meaningful, defensible
   connection to that actual situation.

NEEDS_CLARIFICATION
Use when the visitor clearly has a real business problem, but the
description is too vague to understand what is happening well enough
to evaluate the Terragni connection. Ask exactly one concise question
that requests the missing context most useful for understanding the
challenge, such as the affected audience, observed behaviour, desired
behaviour, business outcome, or journey/context.

NOT_SUPPORTED
Use when the request is generic, educational, trend-oriented,
hypothetical, unrelated to a business challenge, asks to invent a
Terragni capability, or when there is no defensible Terragni evidence
for the concrete challenge.

IMPORTANT DECISION ORDER
1. Understand the visitor's meaning.
2. Decide whether an actual business challenge is present.
3. If vague but genuinely problematic, request clarification.
4. If sufficiently concrete, assess the supplied evidence.
5. Only then decide matched/not_supported.

Never classify a request as matched merely because retrieved evidence
shares words, an industry, a topic, or a broad business objective
with the request.

Return ONLY JSON in this shape:
{
  "match_status": "matched | needs_clarification | not_supported",
  "challenge_summary": "brief anonymous description of the actual
                         business situation, or empty string",
  "missing_context": "what is missing if clarification is needed,
                       otherwise empty string",
  "clarification_question": "exactly one concise question if needed,
                              otherwise empty string",
  "evidence_assessment": "brief explanation of why the supplied
                          evidence does or does not support the
                          concrete challenge"
}
"""


def _run_challenge_gate(
    messages: list[dict],
) -> dict:

    gate_user = messages[-1]["content"]

    raw = _groq_json_call(
        [
            {
                "role": "system",
                "content": CHALLENGE_GATE_PROMPT,
            },
            {
                "role": "user",
                "content": gate_user,
            },
        ],
        max_tokens=900,
    )

    try:
        result = json.loads(
            _strip_json_fences(raw)
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        result = {}

    status = str(
        result.get("match_status")
        or "not_supported"
    ).strip().lower()

    if status not in {
        "matched",
        "needs_clarification",
        "not_supported",
    }:
        status = "not_supported"

    question = str(
        result.get("clarification_question")
        or ""
    ).strip()

    if status == "needs_clarification" and not question:
        question = (
            "What specific behaviour, outcome, or business problem "
            "would you most like to change?"
        )

    return {
        "match_status": status,
        "challenge_summary": str(
            result.get("challenge_summary")
            or ""
        ).strip(),
        "missing_context": str(
            result.get("missing_context")
            or ""
        ).strip(),
        "clarification_question": question[:500],
        "evidence_assessment": str(
            result.get("evidence_assessment")
            or ""
        ).strip(),
    }


def _gate_result_as_json(gate: dict) -> str:

    status = gate["match_status"]

    if status == "needs_clarification":
        return json.dumps({
            "match_status": status,
            "clarification_question": gate["clarification_question"],
            "page_title": "A little more context would help",
            "problem_summary": gate["challenge_summary"],
            "diagnosis": "",
            "primary_offering": "",
            "matched_offerings": [],
            "solution_title": "",
            "solution": "",
            "how_it_works": [],
            "frameworks": [],
            "expected_outcomes": [],
            "case_study_ids": [],
            "why_this_fits": "",
            "recommended_next_step": "",
            "evidence_status": "limited",
            "documented_evidence": [],
        })

    if status == "not_supported":
        return json.dumps({
            "match_status": status,
            "clarification_question": "",
            "page_title": "Let's start with a specific business challenge",
            "problem_summary": gate["challenge_summary"],
            "diagnosis": "The request does not yet provide a sufficiently concrete Terragni challenge supported by the supplied material.",
            "primary_offering": "",
            "matched_offerings": [],
            "solution_title": "",
            "solution": "",
            "how_it_works": [],
            "frameworks": [],
            "expected_outcomes": [],
            "case_study_ids": [],
            "why_this_fits": "",
            "recommended_next_step": "Describe the specific business situation, what is happening today, and what you want to change.",
            "evidence_status": "limited",
            "documented_evidence": [],
        })

    return ""


def call_llm(messages: list[dict]) -> str:

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. "
            "Add your key to backend/.env"
        )

    # First understand the visitor's challenge independently from
    # solution generation. This prevents relevant Terragni material
    # from pulling generic questions into a fabricated solution.
    gate = _run_challenge_gate(messages)

    if gate["match_status"] != "matched":
        return _gate_result_as_json(gate)

    synthesis_messages = list(messages)
    synthesis_messages.append({
        "role": "user",
        "content": (
            "SEMANTIC CHALLENGE GATE RESULT\n"
            "The gate has independently determined that the visitor "
            "described a concrete business challenge with sufficient "
            "Terragni evidence for synthesis.\n\n"
            + json.dumps(gate, ensure_ascii=False)
            + "\n\n"
            "Now generate the final Terragni-grounded JSON. Do not "
            "change the challenge into a generic business question. "
            "Every proposed solution element must remain grounded in "
            "the supplied evidence and controlled vocabulary."
        ),
    })

    return _groq_json_call(
        synthesis_messages,
        max_tokens=2200,
    )


# ============================================================
# TERRAGNI TAXONOMY
# ============================================================

def _taxonomy(kb: dict) -> str:

    offerings = "\n".join(
        f"{o['id']} | {o['name']} | {o['description']}"
        for o in kb.get(
            "offerings",
            []
        )
    )

    signals = "\n".join(
        f"{s['signal']} => {', '.join(s['offerings'])}"
        for s in kb.get(
            "business_challenge_signals",
            []
        )
    )

    cases = "\n".join(
        f"{c['id']} | "
        f"offering={c['offering']} | "
        f"industry={c['industry']} | "
        f"finding={c['finding']} | "
        f"outcome={c.get('outcome') or 'not stated'}"
        for c in kb.get(
            "case_studies",
            []
        )
    )

    frameworks = "\n".join(
        f"{offering_id}: {', '.join(items)}"
        for offering_id, items in kb.get(
            "frameworks_by_offering",
            {}
        ).items()
    )

    outcomes = "\n".join(
        f"{x['outcome']} => {', '.join(x['offerings'])}"
        for x in kb.get(
            "outcome_language",
            []
        )
    )

    return (
        f"OFFERINGS\n{offerings}\n\n"
        f"CHALLENGE SIGNALS\n{signals}\n\n"
        f"CASE STUDIES\n{cases}\n\n"
        f"FRAMEWORKS\n{frameworks}\n\n"
        f"OUTCOME LANGUAGE\n{outcomes}"
    )


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are the Terragni consultant powering a public-facing
Terragni business-challenge explorer.

Your job is to interpret a visitor's business challenge through
the Terragni lens using ONLY the Terragni material supplied
in this request.

You are NOT a generic business consultant.

============================================================
TERRAGNI-ONLY RULES
============================================================

1. Use ONLY the controlled Terragni vocabulary and the retrieved
   Terragni evidence supplied in this request.

2. Do NOT use general business knowledge, external research,
   outside statistics, invented examples, or generic consulting
   frameworks.

3. Do NOT invent:
   - Terragni offerings
   - methodologies
   - frameworks
   - case studies
   - clients
   - results
   - metrics
   - capabilities

4. Do not select an offering merely because of a keyword or
   industry.

   Reason from the actual visitor challenge and retrieved
   evidence.

5. Multiple offerings may be relevant.

6. Select case studies only when retrieved evidence provides
   a defensible connection.

7. Proposed applications must be clearly presented as things
   Terragni could explore.

8. documented_evidence must refer ONLY to evidence supplied
   in this request.

9. expected_outcomes must use ONLY documented Terragni
   outcome language.

10. If evidence is weak, say so.

============================================================
SEMANTIC CHALLENGE GATE
============================================================

Before generating any solution, independently determine whether the
visitor has described a concrete business challenge. A challenge is
concrete when the request describes an actual business situation,
problem, friction, behaviour, decision, adoption issue, experience
issue, or business outcome that someone wants to change.

Do NOT infer a problem merely because the visitor mentions a business
topic, industry, capability, trend, audience, or desired activity.
A request for general advice, strategy creation, trends, education,
ideas, or a hypothetical plan is not by itself a concrete challenge.

If the visitor has a genuine business problem but the description is
too vague to understand what is happening, use needs_clarification.
Ask exactly one concise question targeting the missing context.

Use matched only when there is both:
- a sufficiently concrete visitor challenge, and
- a meaningful, defensible connection between that challenge and the
  retrieved Terragni evidence.

Never work backwards from retrieved evidence to make a generic query
look like a Terragni challenge. Keyword, industry, or topic similarity
is not enough.

Generation order:
1. Understand the visitor's meaning.
2. Establish whether a concrete business challenge exists.
3. Assess whether the supplied Terragni evidence supports that challenge.
4. Choose match_status.
5. Generate the full solution only when match_status is matched.

============================================================
OUTPUT BEHAVIOUR BY MATCH STATUS
============================================================

matched:
Generate the full grounded response fields.

needs_clarification:
Return only the anonymous problem summary and exactly one concise
clarification question. Keep solution, offerings, frameworks, outcomes,
case studies and documented evidence empty.

not_supported:
Return a concise scope explanation. Keep clarification_question empty
and keep solution, offerings, frameworks, outcomes, case studies and
documented evidence empty.

============================================================
EVIDENCE CITATION RULE
============================================================

Each retrieved source is numbered:

EVIDENCE 1
EVIDENCE 2
EVIDENCE 3
...

When citing evidence, ALWAYS use the numeric evidence index.

For example:

"evidence_index": 3

Do NOT invent an evidence index.

Do NOT use an index that was not supplied.

The evidence index is the safest way to connect your answer
to the actual retrieved Terragni source.

============================================================
CONFIDENTIALITY RULES
============================================================

11. NEVER reproduce:
    - client names
    - company names
    - brand names
    - person's names
    - account names
    - project names
    - email addresses
    - phone numbers
    - URLs
    - account numbers
    - ticket/reference numbers
    - other identifying information

12. Do not repeat the visitor's question verbatim.

13. Rewrite the challenge generically and anonymously.

14. Never include identifying information in:
    - page_title
    - problem_summary
    - diagnosis
    - solution_title
    - solution
    - how_it_works
    - why_this_fits
    - recommended_next_step
    - documented_evidence.claim

15. Never expose raw confidential source filenames
    as customer-facing text.

16. Internal case-study IDs such as DS-CS1 and DS-CS2
    are backend identifiers only.

17. Do not put visitor information in URLs, query strings,
    email links or CTAs.

============================================================
PUBLIC-FACING TONE
============================================================

18. Keep the response concise, clear, premium and human.

19. Use Terragni terminology only when supported by the supplied
    material.

20. The answer should explain what Terragni could explore.
    Do not present it as a confirmed consulting diagnosis.

21. Return ONLY valid JSON.

============================================================
OUTPUT JSON
============================================================

{
  "match_status": "matched | needs_clarification | not_supported",

  "clarification_question": "one short question only when needs_clarification; otherwise empty string",

  "page_title": "anonymous customer-facing title",

  "problem_summary": "one anonymous sentence",

  "diagnosis": "2-4 grounded sentences",

  "primary_offering": "valid offering ID or empty string",

  "matched_offerings": [
    "supported offering IDs"
  ],

  "solution_title": "specific proposed Terragni intervention",

  "solution": "3-5 grounded sentences",

  "how_it_works": [
    "3-6 practical proposed steps"
  ],

  "frameworks": [
    "supported framework names"
  ],

  "expected_outcomes": [
    "supported outcome language"
  ],

  "case_study_ids": [
    "0-3 strongest documented case IDs"
  ],

  "why_this_fits":
    "2-3 sentences explaining the evidence connection",

  "recommended_next_step":
    "one simple Terragni-oriented next step",

  "evidence_status":
    "strong | moderate | limited",

  "documented_evidence": [
    {
      "evidence_index": 1,
      "case_study_id": "valid ID or empty",
      "claim": "short anonymous factual summary"
    }
  ]
}
"""


# ============================================================
# BUILD MESSAGES
# ============================================================

def build_messages(
    kb: dict,
    user_query: str,
    evidence: list[dict],
) -> list[dict]:

    evidence_parts = []

    for index, item in enumerate(
        evidence,
        start=1,
    ):

        evidence_parts.append(
            f"""
EVIDENCE {index}

Source:
{item.get("source", "")}

Location:
{item.get("locator", "")}

Content:
{item.get("text", "")}
""".strip()
        )

    evidence_block = "\n\n".join(
        evidence_parts
    )

    return [
        {
            "role": "system",
            "content": (
                SYSTEM_PROMPT
                + "\n\n"
                + "CONTROLLED TERRAGNI VOCABULARY\n"
                + _taxonomy(kb)
            ),
        },

        {
            "role": "user",
            "content": (
                "VISITOR QUESTION\n"
                + user_query
                + "\n\n"
                + "RETRIEVED TERRAGNI MATERIAL\n"
                + (
                    evidence_block
                    if evidence_block
                    else (
                        "[No sufficiently relevant "
                        "Terragni evidence was retrieved.]"
                    )
                )
            ),
        },
    ]


# ============================================================
# JSON CLEANUP
# ============================================================

def _strip_json_fences(
    text: str,
) -> str:

    text = (
        text or ""
    ).strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    ).strip()

    return text


# ============================================================
# BASIC SENSITIVE-DATA DETECTION
# ============================================================

def _contains_sensitive_identity(
    text: str,
) -> bool:

    value = (
        text or ""
    ).lower()

    patterns = [

        # Email
        r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",

        # Phone
        r"\b(?:\+?\d[\d\s().-]{7,}\d)\b",

        # URL
        r"\bhttps?://\S+\b",

        # www URL
        r"\bwww\.\S+\b",
    ]

    return any(
        re.search(
            pattern,
            value,
            flags=re.I,
        )
        for pattern in patterns
    )


# ============================================================
# RESPONSE PARSER
# ============================================================

def parse_llm_response(
    raw: str,
    kb: dict,
    allowed_evidence: list[dict],
) -> dict:

    data = json.loads(
        _strip_json_fences(raw)
    )

    # ---------------------------------------------------------
    # VALID TERRAGNI IDs
    # ---------------------------------------------------------

    valid_offerings = {
        item["id"]
        for item in kb.get(
            "offerings",
            []
        )
        if isinstance(item, dict)
        and item.get("id")
    }

    valid_case_studies = {
        item["id"]
        for item in kb.get(
            "case_studies",
            []
        )
        if isinstance(item, dict)
        and item.get("id")
    }

    valid_frameworks = {
        framework
        for frameworks in kb.get(
            "frameworks_by_offering",
            {}
        ).values()
        for framework in frameworks
    }

    valid_outcomes = {
        item["outcome"]
        for item in kb.get(
            "outcome_language",
            []
        )
        if isinstance(item, dict)
        and item.get("outcome")
    }

    # ---------------------------------------------------------
    # LIST VALIDATION
    # ---------------------------------------------------------

    def clean_list(
        value: Any,
        allowed: set[str],
        limit: int,
    ) -> list[str]:

        if not isinstance(
            value,
            list,
        ):
            return []

        result = []

        for item in value:

            value_string = str(
                item
            ).strip()

            if value_string in allowed:
                result.append(
                    value_string
                )

        return result[:limit]

    # ---------------------------------------------------------
    # OFFERINGS
    # ---------------------------------------------------------

    data["matched_offerings"] = clean_list(
        data.get(
            "matched_offerings"
        ),
        valid_offerings,
        3,
    )

    # ---------------------------------------------------------
    # CASE STUDIES
    # ---------------------------------------------------------

    data["case_study_ids"] = clean_list(
        data.get(
            "case_study_ids"
        ),
        valid_case_studies,
        3,
    )

    # ---------------------------------------------------------
    # FRAMEWORKS
    # ---------------------------------------------------------

    data["frameworks"] = clean_list(
        data.get(
            "frameworks"
        ),
        valid_frameworks,
        6,
    )

    # ---------------------------------------------------------
    # OUTCOMES
    # ---------------------------------------------------------

    data["expected_outcomes"] = clean_list(
        data.get(
            "expected_outcomes"
        ),
        valid_outcomes,
        5,
    )

    # ---------------------------------------------------------
    # PRIMARY OFFERING
    # ---------------------------------------------------------

    primary = data.get(
        "primary_offering"
    )

    data["primary_offering"] = (
        primary
        if primary in valid_offerings
        else ""
    )

    if (
        data["primary_offering"]
        and data["primary_offering"]
        not in data["matched_offerings"]
    ):

        data["matched_offerings"].insert(
            0,
            data["primary_offering"],
        )

    data["matched_offerings"] = (
        data["matched_offerings"][:3]
    )

    # ---------------------------------------------------------
    # MATCH STATUS
    # ---------------------------------------------------------

    match_status = str(
        data.get("match_status")
        or "not_supported"
    ).strip().lower()

    if match_status not in {
        "matched",
        "needs_clarification",
        "not_supported",
    }:
        match_status = "not_supported"

    data["match_status"] = match_status

    data["clarification_question"] = str(
        data.get("clarification_question")
        or ""
    ).strip()

    if match_status == "needs_clarification":
        if not data["clarification_question"]:
            data["clarification_question"] = (
                "What outcome or behaviour would you most like to change?"
            )
        data["clarification_question"] = (
            data["clarification_question"][:500]
        )
    else:
        data["clarification_question"] = ""

    # ---------------------------------------------------------
    # TEXT FIELDS
    # ---------------------------------------------------------

    text_fields = (
        "page_title",
        "problem_summary",
        "diagnosis",
        "solution_title",
        "solution",
        "why_this_fits",
        "recommended_next_step",
    )

    for field in text_fields:

        data[field] = str(
            data.get(field)
            or ""
        ).strip()

    # ---------------------------------------------------------
    # STEPS
    # ---------------------------------------------------------

    if not isinstance(
        data.get("how_it_works"),
        list,
    ):
        data["how_it_works"] = []

    data["how_it_works"] = [
        str(item).strip()
        for item in data["how_it_works"]
        if str(item).strip()
    ][:6]

    # ---------------------------------------------------------
    # EVIDENCE STATUS
    # ---------------------------------------------------------

    if data.get(
        "evidence_status"
    ) not in {
        "strong",
        "moderate",
        "limited",
    }:

        data["evidence_status"] = "limited"

    # =========================================================
    # RESOLVE EVIDENCE BY INDEX
    # =========================================================

    grounded_evidence = []

    raw_evidence = data.get(
        "documented_evidence"
    )

    if not isinstance(
        raw_evidence,
        list,
    ):
        raw_evidence = []

    for item in raw_evidence:

        if not isinstance(
            item,
            dict,
        ):
            continue

        # -----------------------------------------------------
        # Evidence index supplied by the LLM
        # -----------------------------------------------------

        evidence_index = item.get(
            "evidence_index"
        )

        try:

            evidence_index = int(
                evidence_index
            )

        except (
            TypeError,
            ValueError,
        ):

            continue

        # -----------------------------------------------------
        # Validate index
        # -----------------------------------------------------

        if (
            evidence_index < 1
            or evidence_index > len(
                allowed_evidence
            )
        ):
            continue

        # -----------------------------------------------------
        # Resolve the actual retrieved chunk
        # -----------------------------------------------------

        source_evidence = (
            allowed_evidence[
                evidence_index - 1
            ]
        )

        claim = str(
            item.get(
                "claim"
            )
            or source_evidence.get(
                "text",
                "",
            )
        ).strip()

        # -----------------------------------------------------
        # Prevent obvious sensitive information in claim
        # -----------------------------------------------------

        if _contains_sensitive_identity(
            claim
        ):
            continue

        grounded_evidence.append(
            {
                # Internal ID is retained internally.
                "case_study_id": (
                    item.get(
                        "case_study_id"
                    )
                    if item.get(
                        "case_study_id"
                    ) in valid_case_studies
                    else ""
                ),

                # These are used internally by the backend.
                "source": source_evidence.get(
                    "source",
                    "",
                ),

                "locator": source_evidence.get(
                    "locator",
                    "",
                ),

                "claim": claim[:700],
            }
        )

    data["documented_evidence"] = (
        grounded_evidence[:6]
    )

    # =========================================================
    # MATCH-GATE SAFETY
    # =========================================================

    # A clarification or unsupported result must never accidentally
    # expose a full Terragni solution assembled from weak evidence.
    if data["match_status"] != "matched":
        data["primary_offering"] = ""
        data["matched_offerings"] = []
        data["case_study_ids"] = []
        data["frameworks"] = []
        data["expected_outcomes"] = []
        data["documented_evidence"] = []

        if data["match_status"] == "not_supported":
            data["clarification_question"] = ""

    # =========================================================
    # FINAL PUBLIC TEXT SAFETY CHECK
    # =========================================================

    public_text = " ".join(
        [
            data.get(
                "page_title",
                "",
            ),

            data.get(
                "problem_summary",
                "",
            ),

            data.get(
                "diagnosis",
                "",
            ),

            data.get(
                "solution_title",
                "",
            ),

            data.get(
                "solution",
                "",
            ),

            data.get(
                "why_this_fits",
                "",
            ),

            data.get(
                "recommended_next_step",
                "",
            ),

            data.get(
                "clarification_question",
                "",
            ),

            " ".join(
                data.get(
                    "how_it_works",
                    [],
                )
            ),
        ]
    )

    if _contains_sensitive_identity(
        public_text
    ):

        raise ValueError(
            "The generated response contained "
            "an identifying value and was blocked "
            "for confidentiality."
        )

    # =========================================================
    # IMPORTANT:
    #
    # We now only clear unsupported Terragni selections
    # when there is genuinely NO grounded evidence.
    # =========================================================

    if not data["documented_evidence"]:

        data["evidence_status"] = "limited"

        data["primary_offering"] = ""

        data["matched_offerings"] = []

        data["case_study_ids"] = []

        data["frameworks"] = []

        data["expected_outcomes"] = []

    return data
