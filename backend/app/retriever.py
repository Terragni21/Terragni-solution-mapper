"""Small, local, deterministic retrieval layer for Terragni documents.

Retrieval does not decide the answer. It only finds source passages. The LLM
is allowed to reason over those passages, and the API refuses to manufacture a
fallback answer when the LLM is unavailable.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .document_parser import load_index

TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9&'/-]*")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


class Retriever:
    def __init__(self):
        self.index = load_index()
        self.docs = self.index.get("documents", [])
        self.doc_tokens = [tokenize(d["text"]) for d in self.docs]
        self.df = Counter()
        for toks in self.doc_tokens:
            self.df.update(set(toks))
        self.avgdl = (sum(map(len, self.doc_tokens)) / len(self.doc_tokens)) if self.doc_tokens else 1

    def score(self, query: str, i: int) -> float:
        q = tokenize(query)
        if not q:
            return 0.0
        toks = self.doc_tokens[i]
        tf = Counter(toks)
        n = len(self.docs)
        dl = len(toks) or 1
        k1, b = 1.5, 0.75
        score = 0.0
        for term in set(q):
            if term not in tf:
                continue
            df = self.df.get(term, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * dl / self.avgdl)
            score += idf * (freq * (k1 + 1)) / denom

        # Generic phrase boosts only. No phrase maps to a particular offering.
        q_lower = query.lower()
        text_lower = self.docs[i]["text"].lower()
        for phrase in (
            "digital adoption", "cost to serve", "wallet share", "one-size-fits-all",
            "relationship manager", "customer effort", "premium banking",
            "fund transfer", "loyalty programme", "market share", "persistency",
            "behavioural design", "behaviour science", "registration", "onboarding",
            "sign up", "signup", "abandon", "abandonment",
        ):
            if phrase in q_lower and phrase in text_lower:
                score += 1.5
        return score

    def search(self, query: str, top_k: int = 15) -> list[dict]:
        ranked = sorted(
            ((self.score(query, i), self.docs[i]) for i in range(len(self.docs))),
            key=lambda x: x[0],
            reverse=True,
        )
        results = []
        for score, doc in ranked:
            if score <= 0:
                continue
            results.append({**doc, "score": round(score, 4)})
            if len(results) >= top_k:
                break
        return results


