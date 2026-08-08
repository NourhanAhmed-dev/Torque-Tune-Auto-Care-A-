# rag/verifier.py
"""=== SELF-RAG CHECK (grader: the relevance + support gate) ===

Applied to BOTH RAG answers and episodic/semantic recall (agent/client.py:
HOOK 5 on the final answer + _recall_with_verification on recalled memories).
Visible consequence on failure: the agent prefixes the reply with
"[Low confidence — ...]" instead of presenting an ungrounded claim as fact.

Two reflection dimensions, mirroring Self-RAG (arXiv:2310.11511):
  1. RELEVANT   — is the retrieved content on-topic for the query?
  2. SUPPORTED  — is the claim actually contained in the retrieved content?

Judged by Gemini when a key is available; falls back to a deterministic
lexical check on missing key or ANY API error (e.g. 429), so the pipeline
never crashes mid-demo.
"""
from __future__ import annotations

import os
import re

__all__ = ["SelfRAGVerifier"]

_JUDGE_PROMPT = """You are a strict grounding grader for an auto-care assistant.
Answer with exactly three lines:
Line 1: RELEVANT or NOT_RELEVANT (is the evidence on-topic for the query?)
Line 2: SUPPORTED or NOT_SUPPORTED (does the evidence actually contain the claim?)
Line 3: one short reason.
Query: {query}
Evidence:
{evidence}
Claim: {claim}"""

_STOP = {"the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "is", "are",
         "was", "were", "what", "our", "your", "per", "with", "about", "it", "at",
         "be", "has", "have", "not", "no", "we", "you", "they", "should", "would"}
_IDENT = re.compile(r"\b(?:SB|PT|POL)[- ]?\d+[0-9a-z.-]*", re.I)


def _text_of(src) -> str:
    if isinstance(src, str):
        return src
    if isinstance(src, dict):
        return str(src.get("content", src.get("text", src)))
    return getattr(src, "content", None) or getattr(src, "text", None) or str(src)


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower())
            if t not in _STOP and len(t) > 2}


class SelfRAGVerifier:
    """Post-retrieval / post-generation verification gate."""

    def __init__(self, client=None, model: str = "gemini-3.5-flash-lite"):
        self._client = client
        self.model = model

    def check(self, query, sources, answer) -> tuple:
        """(supported: bool, critique: str) — empty critique means the check passed."""
        evidence = [t for t in (_text_of(s) for s in (sources or [])) if t and t.strip()]
        if not evidence:
            return False, "no retrieved content behind the claim"
        ev_text = "\n---\n".join(evidence)[:12000]

        llm = self._llm()
        if llm is not None:
            try:
                text = (llm.models.generate_content(
                    model=self.model,
                    contents=_JUDGE_PROMPT.format(query=query, evidence=ev_text, claim=answer),
                ).text or "")
            except Exception:
                text = ""
            lines = [l.strip().upper().replace(" ", "_") for l in text.splitlines()]
            if lines and ("RELEVANT" in lines[0] or (len(lines) > 1 and "SUPPORTED" in lines[1])):
                rel = lines[0].startswith("RELEVANT")
                sup = lines[1].startswith("SUPPORTED") if len(lines) > 1 else False
                reason = lines[2] if len(lines) > 2 else ""
                if not rel:
                    return False, f"retrieval not relevant: {reason}"
                if not sup:
                    return False, f"answer not supported: {reason}"
                return True, ""
        # deterministic fallback (no key / API error / unparseable judge)
        return self._lexical(query, ev_text, answer)

    @staticmethod
    def _lexical(query: str, evidence: str, answer: str) -> tuple:
        q_tok, e_tok, a_tok = _tokens(query), _tokens(evidence), _tokens(answer)
        q_id, e_id, a_id = (set(_IDENT.findall(x)) for x in (query, evidence, answer))
        if not (q_tok & e_tok) and not (q_id & e_id):
            return False, "no topical overlap between query and retrieval"
        if a_id and not a_id <= e_id:
            return False, "answer cites identifiers absent from retrieval"
        overlap = len(a_tok & e_tok) / max(1, len(a_tok))
        if overlap < 0.2:
            return False, f"lexical support too low ({overlap:.0%})"
        return True, ""

    def _llm(self):
        if self._client is not None:
            return self._client
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return None
        try:
            from google import genai
            self._client = genai.Client(api_key=key)
        except Exception:
            self._client = None
        return self._client