from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Sequence
from rag import config as cfg
from rag.generators import GenerationResult, Generator
from rag.retriever import SearchResult, VectorRetriever, BM25Retriever

"""
Hybrid RAG Architecture.
Combines Dense Semantic Vector Search (VectorRetriever) and  
(BM25Retriever) via Reciprocal Rank Fusion (RRF)
Calculates detailed execution metrics (Retrieval Latency, Generation Latency, Token Usage).
"""

@dataclass
class HybridRAGAnswer:
    """Dataclass holding the final generated answer, retrieved context, and metrics."""

    query: str
    answer: str
    retrieved: list[SearchResult]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    retrieval_latency_s: float
    generation_latency_s: float
    total_latency_s: float
    architecture: str = "hybrid"
    extra: dict[str, Any] = field(default_factory=dict)


class HybridRetriever:
    """
    Combines Vector Search and BM25 Keyword Search using Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        bm25_retriever: BM25Retriever,
        rrf_k: int = cfg.RRF_K,
    ):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        top_k: int = getattr(cfg, "TOP_K", 3),
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Retrieves candidate lists from Vector and BM25 retrievers, 
        then merges them using RRF scoring.
        """
        # Fetch candidate multiplier to allow effective fusion
        candidate_k = max(
        top_k * cfg.HYBRID_CANDIDATE_MULTIPLIER,
        10,
        )

        vec_results = self.vector_retriever.retrieve(
            query=query, top_k=candidate_k, metadata_filter=metadata_filter
        )
        bm25_results = self.bm25_retriever.retrieve(
            query=query, top_k=candidate_k, metadata_filter=metadata_filter
        )

        # Apply Reciprocal Rank Fusion (RRF)
        # RRF_Score(doc) = sum( 1.0 / (rrf_k + rank) )
        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, SearchResult] = {}

        def _process_rankings(results_list: Sequence[SearchResult]):
            for rank, item in enumerate(results_list, start=1):
                key = item.doc_id
                doc_map[key] = item
                rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (self.rrf_k + rank))

        _process_rankings(vec_results)
        _process_rankings(bm25_results)

        # Sort results descending by fused RRF score
        sorted_keys = sorted(
            rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True
        )

        fused_results: list[SearchResult] = []
        for key in sorted_keys[:top_k]:
            base_item = doc_map[key]
            
            base_item.score = round(rrf_scores[key], 6)

            fused_results.append(base_item)
                
            
        return fused_results


class HybridRAG:
    """
    Pipeline orchestrator for Hybrid Search RAG.
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        generator: Generator | None = None,
        top_k: int = getattr(cfg, "TOP_K", 3),
        rrf_k: int = cfg.RRF_K,
    ):
        self.vector_retriever = vector_retriever or VectorRetriever()

        self.bm25_retriever = bm25_retriever or BM25Retriever()

        self.hybrid_retriever = HybridRetriever(
            vector_retriever=self.vector_retriever,
            bm25_retriever=self.bm25_retriever,
            rrf_k=rrf_k,
        )
        self.generator = generator or Generator()
        self.top_k = top_k

    def answer(
        self, query: str, metadata_filter: dict[str, Any] | None = None
    ) -> HybridRAGAnswer:
        """
        Executes end-to-end Hybrid RAG and captures latency/token consumption.
        """
        t0 = time.perf_counter()

        # Step 1: Hybrid Retrieval (Vector + BM25 via RRF)
        retrieved_chunks = self.hybrid_retriever.retrieve(
            query=query, top_k=self.top_k, metadata_filter=metadata_filter
        )
        if not retrieved_chunks:
            latency = round(time.perf_counter() - t0, 4)

            return HybridRAGAnswer(
                query=query,
                answer="No relevant documents were retrieved.",
                retrieved=[],
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                retrieval_latency_s=latency,
                generation_latency_s=0.0,
                total_latency_s=latency,
                architecture="hybrid",
        )

        t1 = time.perf_counter()

        # Step 2: Generation via LLM
        gen_result: GenerationResult = self.generator.generate(
            query=query, retrieved=retrieved_chunks
        )
        t2 = time.perf_counter()

        retrieval_latency = round(t1 - t0, 4)
        generation_latency = round(t2 - t1, 4)
        total_latency = round(t2 - t0, 4)

        return HybridRAGAnswer(
            query=query,
            answer=gen_result.answer,
            retrieved=retrieved_chunks,
            prompt_tokens=gen_result.prompt_tokens,
            completion_tokens=gen_result.completion_tokens,
            total_tokens=gen_result.total_tokens,
            retrieval_latency_s=retrieval_latency,
            generation_latency_s=generation_latency,
            total_latency_s=total_latency,
            architecture="hybrid",
        )