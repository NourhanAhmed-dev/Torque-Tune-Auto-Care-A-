from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any
from rag import config as cfg
from rag.generators import Generator, GenerationResult
from rag.retriever import SearchResult, VectorRetriever



# Final RAG Response
@dataclass
class RAGAnswer:
    """
    Final response returned by the Naive RAG pipeline.
    """

    query: str
    answer: str
    architecture: str = "naive"
    retrieved: list[SearchResult] = field(default_factory=list)
    retrieved_count: int = 0
    retrieved_doc_ids: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    retrieval_latency_s: float = 0.0
    generation_latency_s: float = 0.0
    total_latency_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


# Naive RAG
class NaiveRAG:
    """
    Standard Naive RAG pipeline.

    User Query
        ↓
    Vector Retrieval
        ↓
    LLM Generation
        ↓
    Final Answer
    """

    def __init__(
        self,
        retriever: VectorRetriever | None = None,
        generator: Generator | None = None,
        top_k: int = cfg.TOP_K,
    ):

        self.retriever = retriever or VectorRetriever()

        self.generator = generator or Generator()

        self.top_k = top_k


    def answer(
        self,
        query: str,
        metadata_filter: dict[str, Any] | None = None,
    ) -> RAGAnswer:

        overall_start = time.perf_counter()


        # Retrieval
        retrieval_start = time.perf_counter()

        retrieved = self.retriever.retrieve(
            query=query,
            top_k=self.top_k,
            metadata_filter=metadata_filter,
        )

        retrieval_latency = (
            time.perf_counter() - retrieval_start
        )

       
        # No Retrieved Documents
        if not retrieved:

            total_latency = (
                time.perf_counter() - overall_start
            )

            return RAGAnswer(
                query=query,
                answer="No relevant documents were retrieved.",
                architecture="naive",
                retrieved=[],
                retrieved_count=0,
                retrieved_doc_ids=[],
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                retrieval_latency_s=round(retrieval_latency, 4),
                generation_latency_s=0.0,
                total_latency_s=round(total_latency, 4),
                extra={
                    "top_k": self.top_k,
                },
            )

        # Generation
        generation_start = time.perf_counter()

        generation: GenerationResult = self.generator.generate(
            query=query,
            retrieved=retrieved,
        )

        generation_latency = (
            time.perf_counter() - generation_start
        )

        total_latency = (
            time.perf_counter() - overall_start
        )

        # Return Final Answer
        return RAGAnswer(

            query=query,

            answer=generation.answer,

            architecture="naive",

            retrieved=retrieved,

            retrieved_count=len(retrieved),

            retrieved_doc_ids=[
                r.doc_id
                for r in retrieved
            ],

            prompt_tokens=generation.prompt_tokens,

            completion_tokens=generation.completion_tokens,

            total_tokens=generation.total_tokens,

            retrieval_latency_s=round(
                retrieval_latency,
                4,
            ),

            generation_latency_s=round(
                generation_latency,
                4,
            ),

            total_latency_s=round(
                total_latency,
                4,
            ),

            extra={
                "top_k": self.top_k,
            },
        )