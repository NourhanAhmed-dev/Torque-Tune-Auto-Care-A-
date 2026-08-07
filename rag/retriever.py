from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from rag import config as cfg
from rag.embeddings import Embedder, get_embedder
from rag.vector_store import VectorStore
from rank_bm25 import BM25Okapi
from rag.chunking import Chunk,build_all_chunks
import re


@dataclass
class SearchResult:
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    distance: float = 0.0
    score: float =0.0


class VectorRetriever:
    """
    Retrieves the most relevant document chunks from ChromaDB
    using vector similarity search.

    Supports optional metadata filtering.
    """

    def __init__(
        self,
        store: VectorStore | None = None,
        embedder: Embedder | None = None,
    ):
        # Dependency Injection with lazy defaults
        self.store = store or VectorStore()
        self.embedder = embedder or get_embedder()

    def retrieve(
        self,
        query: str,
        top_k: int = cfg.TOP_K,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
      
        query_embedding = self.embedder.embed_one(query)

        if metadata_filter:
            results = self.store.search_with_filter(
                query_embedding=query_embedding,
                metadata_filter=metadata_filter,
                top_k=top_k,
            )
        else:
            results = self.store.search(
                query_embedding=query_embedding,
                top_k=top_k,
            )

        return self._convert(results)

    def _convert(self, results: dict[str, Any]) -> list[SearchResult]:
        """
        Convert raw ChromaDB output into SearchResult objects.
        """

        if not results.get("ids") or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results.get("distances", [[0.0] * len(ids)])[0]

        output: list[SearchResult] = []

        for doc_id, text, meta, dist in zip(
            ids,
            docs,
            metas,
            distances,
        ):
            output.append(
                SearchResult(
                    doc_id=doc_id,
                    text=text,
                    metadata=meta,
                    distance=float(dist),
                )
            )

        return output


class BM25Retriever:
    """
    Retrieves document chunks using BM25 keyword search.
    """

    def __init__(self):
        self.chunks = build_all_chunks()

        # Tokenize corpus once during initialization
        self.tokenized_corpus = [
            re.findall(r"\w+", chunk.text.lower())
            for chunk in self.chunks
        ]

        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def retrieve(
        self,
        query: str,
        top_k: int = cfg.TOP_K,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Retrieve relevant chunks using BM25 with optional metadata filtering.
        """

        query_tokens = re.findall(r"\w+", query.lower())

        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        ranked_results: list[tuple[float, Chunk]] = []

        for score, chunk in zip(scores, self.chunks):

            if score <= 0:
                continue

            if metadata_filter:
                if not all(
                    chunk.metadata.get(key) == value
                    for key, value in metadata_filter.items()
                ):
                    continue

            ranked_results.append((float(score), chunk))

        ranked_results.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        results: list[SearchResult] = []

        for score, chunk in ranked_results[:top_k]:
            results.append(
                SearchResult(
                    doc_id=chunk.doc_id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    score=score,
                )
            )

        return results
    