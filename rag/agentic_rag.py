from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any
from rag import config as cfg
from rag.retriever import VectorRetriever, BM25Retriever, SearchResult
from rag.generators import Generator
import time
 
@dataclass
class ReasoningStep:
    
    thought: str
    action: str  # "retrieve" | "answer"
    query: str | None = None
    observation: str | None = None
 
 
@dataclass
class AgenticRAGResult:
    answer: str
    steps: list[ReasoningStep] = field(default_factory=list)
    retrieved: list[SearchResult] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    retrieval_latency_s: float = 0.0
    generation_latency_s: float = 0.0
    total_latency_s: float = 0.0
    planning_latency_s: float = 0.0
    architecture: str = "agentic"
 
class AgenticRAG:
    """
    Reasoning loop on top of retrieval + generation:
 
        decide -> retrieve -> observe -> decide again ... -> answer
    """
 
    def __init__(
        self,
        retriever: VectorRetriever | BM25Retriever | None = None,
        generator: Generator | None = None,
        model_name: str = cfg.GENERATOR_MODEL_NAME,
        api_key: str | None = None,
        max_iterations: int = 4,
        top_k: int = cfg.TOP_K,
    ):
        self.retriever = retriever or VectorRetriever()
        self.generator = generator or Generator(model_name=model_name, api_key=api_key)
        # reuse the same genai client/model the Generator already created
        self.client = self.generator.client
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.top_k = top_k
 
    # Decision step: ask the controller LLM what to do next
    def _decide(
        self,
        query: str,
        history: list[ReasoningStep],
        accumulated: list[SearchResult],
    ) -> dict[str, Any]:
 
        history_text = "\n\n".join(
            f"Step {i + 1}:\n"
            f"Thought: {s.thought}\n"
            f"Action: {s.action} (query={s.query})\n"
            f"Observation: {s.observation}"
            for i, s in enumerate(history)
        ) or "No steps yet."
 
        context_summary = "\n".join(
            f"- [{r.doc_id}] {r.text[:200]}..." for r in accumulated
        ) or "No documents retrieved yet."
 
        prompt = f"""
You are the reasoning controller of a Retrieval-Augmented Generation agent
for an automotive tuning knowledge base.
 
Original question: {query}
 
History of steps taken so far:
{history_text}
 
Documents retrieved so far:
{context_summary}
 
Decide the next action. Respond ONLY with valid JSON, no extra text,
no markdown fences:
 
{{
  "thought": "brief reasoning about what is still missing",
  "action": "retrieve" or "answer",
  "search_query": "exact query to search for if action is retrieve, else null"
}}
 
Rules:
- Choose "retrieve" if the documents so far are not enough to fully answer.
- Choose "answer" only when the retrieved documents are sufficient, or
  when you judge that further retrieval will not help.
- Never repeat a search_query already used in a previous step.
- Keep search_query short and focused (keywords), not a full sentence.
"""
 
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={"temperature": 0},
        )
 
        raw = (response.text or "").strip()
        raw = (
            raw.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
 
        try:
            decision = json.loads(raw)
        except json.JSONDecodeError:
            # Safe fallback so the loop always terminates
            decision = {
                "thought": "Could not parse controller output, defaulting to answer.",
                "action": "answer",
                "search_query": None,
            }
 
        return decision
 
    # Main reasoning loop
    def answer(self, query: str) -> AgenticRAGResult:

        overall_start = time.perf_counter()
        retrieval_latency = 0.0
        steps: list[ReasoningStep] = []
        accumulated: list[SearchResult] = []
        seen_ids: set[str] = set()
        seen_queries: set[str] = set()
 
        current_query = query
 
        for _ in range(self.max_iterations):
 
            decision = self._decide(query, steps, accumulated)
 
            thought = decision.get("thought", "")
            action = decision.get("action", "answer")
            search_query = decision.get("search_query") or current_query
 
            # Guard against infinite loops on a repeated query
            if action == "retrieve" and search_query in seen_queries:
                action = "answer"
 
            if action != "retrieve":
                steps.append(ReasoningStep(thought=thought, action="answer"))
                break
 
            seen_queries.add(search_query)
            retrieval_start = time.perf_counter()
            results = self.retriever.retrieve(search_query, top_k=self.top_k)
            retrieval_latency += time.perf_counter() - retrieval_start
            new_results = [r for r in results if r.doc_id not in seen_ids]
 
            for r in new_results:
                seen_ids.add(r.doc_id)
                accumulated.append(r)
 
            observation = (
                f"Retrieved {len(new_results)} new chunk(s) for query '{search_query}'."
                if new_results
                else f"No new chunks found for query '{search_query}'."
            )
 
            steps.append(
                ReasoningStep(
                    thought=thought,
                    action="retrieve",
                    query=search_query,
                    observation=observation,
                )
            )
 
        else:
            # max_iterations reached without the controller choosing "answer"
            steps.append(ReasoningStep(thought="Reached max iterations.", action="answer"))

 
        generation_start = time.perf_counter()
        generation = self.generator.generate(query=query, retrieved=accumulated)
        generation_latency = (
        time.perf_counter() - generation_start
        )

        total_latency = (
        time.perf_counter() - overall_start
        )
        prompt_tokens=generation.prompt_tokens
        completion_tokens=generation.completion_tokens
        total_tokens=generation.total_tokens
 
        return AgenticRAGResult(
            answer=generation.answer,
            steps=steps,
            retrieved=accumulated,
            prompt_tokens=generation.prompt_tokens,
            completion_tokens=generation.completion_tokens,
            total_tokens=generation.total_tokens,

            retrieval_latency_s=round(retrieval_latency, 4),
            generation_latency_s=round(generation_latency, 4),
            total_latency_s=round(total_latency, 4),

            architecture="agentic",
        )