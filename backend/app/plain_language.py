"""
Plain-language safety net for visitor-facing text.

The AI is told not to use Terragni's product, tool or framework names
(JUMP, EAS, De-Sludge, EAST, MRI ...), because a visitor does not know what
they mean. If a name still slips through, it is replaced here with a short
description of what it is.

Only text the visitor reads goes through this filter. The offering and
framework names themselves are kept in the response for Terragni's team
(for example in the contact-form context).
"""

from __future__ import annotations

import re

# Longest / most specific names first.
_REPLACEMENTS: list[tuple[str, str]] = [
    (r"(?:the\s+)?JUMP\s+Probe", "a review of the digital journey"),
    (r"(?:the\s+)?JUMP(?:\s+(?:solution|framework|approach|programme|program))?", "a behavioural redesign of the journey"),
    (r"(?:an?\s+|the\s+)?Effort\s+Assessment\s+Score(?:\s*\(EAS\))?", "an assessment of customer effort"),
    (r"(?:an?\s+|the\s+)?EAS[\s‑-]*Pilot", "a customer-effort pilot"),
    (r"(?:an?\s+|the\s+)?\bEAS\b", "an assessment of customer effort"),
    (r"(?:an?\s+|the\s+)?De[\s‑-]?Sludge(?:\s+(?:programme|program|service|approach))?", "a programme to remove unnecessary complexity"),
    (r"(?:an?\s+|the\s+)?Sludge\s+(?:Audit|Assessment)", "a review of unnecessary complexity"),
    (r"(?:an?\s+|the\s+)?TruNorth(?:\s+(?:probe|out-of-the-box\s+solution|solution))?", "a customer insight study"),
    (r"(?:an?\s+|the\s+)?Lens\s*[–—-]?\s*Insights\s+As\s+A\s+Service", "an ongoing customer-insight service"),
    (r"(?:an?\s+|the\s+)?Insights\s+As\s+A\s+Service", "an ongoing customer-insight service"),
    (r"(?:the\s+)?Behaviour\s+Science\s+Led\s+Communication\s+Me\s+platform", "a behaviour-science communication platform"),
    (r"(?:the\s+)?\bMe\s+platform", "a behaviour-science communication platform"),
    (r"(?:the\s+)?Market\s+Responsiveness\s+Index(?:\s*\(MRI\))?", "a measure of how responsive teams are to customers"),
    (r"(?:the\s+)?\bMRI\b", "a measure of how responsive teams are to customers"),
    (r"\bEAST\*?(?:\s+framework)?", "proven nudge"),
    (r"\bSTEPPS\*?(?:\s+framework)?", "word-of-mouth"),
    (r"\bSCARF\b(?:\s+(?:model|framework))?", "social threat-and-reward"),
    (r"(?:the\s+)?Terragni\s+Experience\s+Grids?", "experience mapping"),
]

_COMPILED = [(re.compile(pattern), plain) for pattern, plain in _REPLACEMENTS]


def plain_language(text: str) -> str:
    """Replace Terragni jargon with plain words; leave everything else."""
    value = str(text or "")
    if not value:
        return ""
    for pattern, plain in _COMPILED:
        value = pattern.sub(plain, value)
    # Tidy repeated articles such as "a an assessment" or "the a review".
    value = re.sub(r"\b(?:a|an|the)\s+(a|an)\b", r"\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s{2,}", " ", value).strip()
    if value[:1].islower() and str(text)[:1].isupper():
        value = value[:1].upper() + value[1:]
    return value
