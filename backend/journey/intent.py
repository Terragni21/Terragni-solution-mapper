"""
Visitor intent detection for the Terragni Solution Mapper.

Every visitor input is routed to one of two paths:

    challenge  - the visitor describes a business problem
    knowledge  - the visitor wants to learn about Terragni
    mixed      - both at once ("Has Terragni helped banks reduce branch visits?")

Clear cases are decided by fast keyword rules. Only unclear inputs are sent
to the LLM, so most visitors do not pay for an extra model call.
"""

from __future__ import annotations

import re
from typing import Any

INTENTS = ("challenge", "knowledge", "mixed")

# Words that point at Terragni itself, its services or its methods.
_TERRAGNI_RE = re.compile(
    r"\b(terragni|your (?:company|firm|team|services?|offerings?|work|methods?|approach|clients?"
    r"|brand|logo|colou?rs?|font|name|office|address|location|founders?|ceo|leadership|website"
    r"|newsletter|contact|email|phone|values|vision|mission|history|experience|industries|sectors)"
    r"|brand colou?rs?|the shift newsletter|who are you|what do you do"
    r"|you guys|de-?sludge|jump probe|\bjump\b|\beas\b|effort assessment|experiential segmentation"
    r"|marketing effectiveness|trunorth|lens|sensemaking|fmc model|east framework|scarf"
    r"|behavio(?:u)?ral science|behavio(?:u)?r(?:al)? design)\b",
    re.IGNORECASE,
)

# Question openings typical of someone who wants to learn.
_QUESTION_RE = re.compile(
    r"^\s*(what|who|how|which|where|when|why|can|could|do|does|did|is|are|have|has|tell me|explain|describe)\b",
    re.IGNORECASE,
)

# First-person business language typical of someone describing a problem.
_PROBLEM_RE = re.compile(
    r"\b(our|we|we're|we are|my team|my bank|us)\b.*\b("
    r"customers?|clients?|users?|employees?|branch(?:es)?|app|sales|costs?|churn|retention|referr\w*|"
    r"complain\w*|adoption|engage\w*|switch\w*|leav\w*|drop\w*|declin\w*|low|poor|high|struggl\w*|"
    r"not\s+\w+|never|rarely|problem|issue|challenge"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)


def _rule_based_intent(text: str) -> dict[str, Any] | None:
    """Return a confident decision, or None when the input is unclear."""
    value = str(text or "").strip()

    if not value:
        return None

    mentions_terragni = bool(_TERRAGNI_RE.search(value))
    asks_question = bool(_QUESTION_RE.search(value)) or value.endswith("?")
    describes_problem = bool(_PROBLEM_RE.search(value))

    if mentions_terragni and asks_question and describes_problem:
        return {"intent": "mixed", "confidence": "high", "method": "rules"}

    if mentions_terragni and asks_question:
        return {"intent": "knowledge", "confidence": "high", "method": "rules"}

    if describes_problem and not mentions_terragni:
        return {"intent": "challenge", "confidence": "high", "method": "rules"}

    return None


_SYSTEM_PROMPT = """
You classify why a visitor typed something into the Terragni Consulting website.
Terragni is a behavioural-science consulting firm.

Return ONLY a JSON object: {"intent": "challenge|knowledge|mixed", "confidence": "high|medium|low"}

- challenge: the visitor describes a business problem or situation in their own organisation.
- knowledge: the visitor wants to learn about Terragni, its services, methods, frameworks or past work.
- mixed: the visitor asks about Terragni's past work AND describes their own problem.
""".strip()


def detect_intent(
    text: str,
    *,
    chosen_path: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Decide which path an input belongs to.

    chosen_path is the button the visitor clicked ("challenge" or "knowledge").
    It is used as the answer when the input itself is unclear.
    """
    chosen = chosen_path if chosen_path in ("challenge", "knowledge") else None

    decision = _rule_based_intent(text)
    if decision:
        return decision

    if use_llm:
        try:
            from backend.journey_service import _call_groq

            result = _call_groq(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=f"Visitor input:\n{str(text or '')[:1500]}",
            )
            intent = str(result.get("intent", "")).strip().lower()
            confidence = str(result.get("confidence", "low")).strip().lower()

            if intent in INTENTS:
                # A low-confidence guess should not override the visitor's own choice.
                if confidence == "low" and chosen:
                    return {"intent": chosen, "confidence": "low", "method": "visitor_choice"}

                return {"intent": intent, "confidence": confidence, "method": "llm"}
        except Exception:
            pass

    return {
        "intent": chosen or "challenge",
        "confidence": "low",
        "method": "visitor_choice" if chosen else "default",
    }


# ============================================================
# INDUSTRY SCOPE
# ============================================================
# The prototype covers banking only. Anything that is clearly a banking or
# financial-services context is accepted; everything else is out of scope.

_BANKING_RE = re.compile(
    r"\b(bank\w*|bfsi|financial services?|finance|fintech|nbfc|lend\w*|loans?|credit|"
    r"wealth|payments?|microfinance|mortgage|cards?|retail banking|private banking|"
    r"priority banking|treasury)\b",
    re.IGNORECASE,
)


def is_supported_industry(industry: str | None) -> bool:
    """True for banking and closely related financial-services industries."""
    value = str(industry or "").strip()

    # An empty industry is treated as in scope so the visitor is not blocked.
    if not value:
        return True

    return bool(_BANKING_RE.search(value))
