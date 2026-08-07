from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Sequence
import google.generativeai as genai
from rag import config as cfg
from rag.retriever import SearchResult


# Generation Result
@dataclass
class GenerationResult:
    answer: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency: float

# Generator
class Generator:

    def __init__(
        self,
        model_name: str = getattr(
            cfg,
            "GENERATOR_MODEL_NAME",
            "gemini-1.5-flash",
        ),
        api_key: str | None = None,
        temperature: float = 0,
    ):

        key = (
            api_key
            or getattr(cfg, "GEMINI_API_KEY", None)
            or os.getenv("GEMINI_API_KEY")
        )

        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        genai.configure(api_key=key)

        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
            ),
        )

    # Format Retrieved Context
    def _format_context(
        self,
        retrieved: Sequence[SearchResult],
    ) -> str:

        formatted = []

        for i, chunk in enumerate(retrieved, start=1):

            formatted.append(
                f"""
Document {i}
Document ID: {chunk.doc_id}

{chunk.text}
"""
            )

        return "\n\n-----------------------------\n\n".join(formatted)

    # Prompt
    def _build_prompt(
        self,
        query: str,
        context: str,
    ) -> str:

        return f"""
You are an automotive tuning assistant.

Answer the user's question ONLY using the retrieved context.

Rules:

- Do NOT use outside knowledge.
- If the answer is not present in the context, reply exactly:

"I cannot answer this question based on the provided context."

- Mention the document IDs when possible.

========================
Context
========================

{context}

========================
Question
========================

{query}

========================
Answer
========================
"""
    # Generate
    def generate(
        self,
        query: str,
        retrieved: Sequence[SearchResult],
    ) -> GenerationResult:

        # No retrieved documents
        if not retrieved:

            return GenerationResult(
                answer="No relevant documents were retrieved.",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency=0.0,
            )

        context = self._format_context(retrieved)

        prompt = self._build_prompt(
            query=query,
            context=context,
        )

        start = time.perf_counter()

        response = self.model.generate_content(prompt)

        latency = time.perf_counter() - start

        usage = getattr(response, "usage_metadata", None)

        prompt_tokens = (
            getattr(usage, "prompt_token_count", 0)
            if usage
            else 0
        )

        completion_tokens = (
            getattr(usage, "candidates_token_count", 0)
            if usage
            else 0
        )

        total_tokens = (
            getattr(usage, "total_token_count", 0)
            if usage
            else 0
        )

        answer = response.text.strip() if response.text else ""

        return GenerationResult(
            answer=answer,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency=latency,
        )