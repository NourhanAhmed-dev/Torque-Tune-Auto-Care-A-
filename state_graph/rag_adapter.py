"""Adapts the `rag_retriever.search(query, filter=...)` calls made inside
FleetRescueNodes.intake_and_plan() (nodes.py) onto the team's real
rag/retriever.py — VectorRetriever, backed by ChromaDB (rag/vector_store.py).

nodes.py itself is untouched: it just needs anything with a
`.search(query, filter=...) -> list[dict-like]` shape injected as its
`rag_retriever` constructor arg. This class is what you inject in
production; the earlier sqlite-based RagRetriever draft is dropped —
the real RAG store is Chroma, not sqlite.

Two translations happen here, both because of how rag/chunking.py
ACTUALLY stores frontmatter (verified against the real file, not
assumed):

  1. Frontmatter key is `doc_type`, not `type` — see chunking.py's
     `__main__` block (`c.metadata.get("doc_type")`). filter={"type": "contract"}
     as used inside nodes.py gets remapped to {"doc_type": "contract"} here.

  2. `_parse_frontmatter()` never casts values — every frontmatter field
     lands in Chroma metadata as a raw string. So client_id=1 (int, as
     nodes.py passes it) must be filtered as client_id="1" (str) or
     Chroma's exact-match `where` clause won't match anything.

Also builds Chroma's `$and`/`$eq` where-clause syntax explicitly rather
than a flat multi-key dict, since flat multi-key dicts are rejected by
current chromadb versions.
"""
from __future__ import annotations

from typing import Any

from rag.retriever import SearchResult, VectorRetriever

_KEY_MAP = {"type": "doc_type"}


class FleetRagAdapter:
    def __init__(self, retriever: VectorRetriever | None = None):
        # Dependency injection with lazy default, same pattern VectorRetriever
        # itself uses — lets tests pass a fake retriever instead of hitting
        # the real Chroma/Gemini stack.
        self.retriever = retriever or VectorRetriever()

    def search(
        self, query: str, filter: dict[str, Any] | None = None, top_k: int = 3
    ) -> list[dict[str, Any]]:
        results: list[SearchResult] = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            metadata_filter=self._build_where(filter),
        )
        return [
            {
                "doc_id": r.doc_id,
                "content": r.text,
                "metadata": r.metadata,
                "distance": r.distance,
            }
            for r in results
        ]

    def _build_where(self, filter: dict[str, Any] | None) -> dict | None:
        if not filter:
            return None
        clauses = [
            {_KEY_MAP.get(k, k): {"$eq": str(v)}}
            for k, v in filter.items()
        ]
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}
