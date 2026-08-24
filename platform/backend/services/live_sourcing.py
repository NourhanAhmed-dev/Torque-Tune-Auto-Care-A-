"""Live wiring for Graph 1: simulated supplier API + LangChain-compatible
Gemini chat model for dynamic_decomposition."""
from __future__ import annotations
import json, sqlite3
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class LiveSupplierClient:
    """Simulated supplier HTTP API: quote = sum of seeded part prices."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def place_order(self, supplier: str, part_ids: list[int]) -> dict[str, Any]:
        # Demo supplier C (race-spec) times out until ops resolves its ticket.
        if supplier == "SupplierC":
            conn = sqlite3.connect(self.db_path)
            try:
                fixed = conn.execute(
                    "SELECT 1 FROM failure_tickets WHERE status='resolved' "
                    "AND error_message LIKE '%SupplierC%' LIMIT 1").fetchone()
            finally:
                conn.close()
            if not fixed:
                raise TimeoutError(f"{supplier} timed out (race-spec unavailable)")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            ph = ",".join("?" for _ in part_ids)
            rows = conn.execute(
                f"SELECT part_id, MIN(price) AS price, MIN(quantity) AS quantity "
                f"FROM build_part_requirements WHERE part_id IN ({ph}) "
                f"GROUP BY part_id",
                part_ids).fetchall()
            if not rows:
                raise ValueError(f"unknown parts: {part_ids}")
            quoted = sum(r["price"] * r["quantity"] for r in rows)
            order_id = conn.execute(
                "SELECT COALESCE(MAX(order_id), 1000) + 1 AS n "
                "FROM supplier_orders").fetchone()["n"]
        finally:
            conn.close()
        return {"order_id": order_id, "quoted_price": quoted,
                "expected_delivery": "+3 days"}


class LiveChatModel(BaseChatModel):
    """LangChain-compatible facade over LiveLLM (Gemini)."""
    llm: Any = None

    @property
    def _llm_type(self) -> str:
        return "gemini-live"

    @staticmethod
    def _prompt(messages) -> str:
        parts = []
        for m in messages:
            if isinstance(m, tuple):
                role, content = m[0], m[1]
            else:
                role = getattr(m, "type", "human")
                content = m.content
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = self.llm.complete(self._prompt(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def with_structured_output(self, schema, *, method=None, **kwargs):
        outer = self

        class _Structured:
            def invoke(self, messages, **kw):
                prompt = (outer._prompt(messages) +
                          "\nRespond ONLY with valid JSON (no fences) matching: " +
                          json.dumps(schema.model_json_schema()))
                raw = outer.llm.complete(prompt).strip()
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
                data = {k: v for k, v in data.items() if k in schema.model_fields}
                return schema(**data)
        return _Structured()

class ResilientAgenticRAG:
    """Retry + memoization wrapper around AgenticRAG.

    - Retries transient Gemini 503/429 with growing backoff.
    - Caches answers per query: TaskDecompositionNode re-fetches specs
      for every part on EVERY supplier event, multiplying Gemini calls;
      identical queries now return the cached result instantly.
    Same answers, same contract — just patient and cheap.
    """

    def __init__(self, inner, attempts: int = 5, base_delay: float = 3.0):
        self._inner = inner
        self._attempts = attempts
        self._base_delay = base_delay
        self._cache: dict = {}

    def answer(self, query: str):
        if query in self._cache:
            return self._cache[query]
        import time
        last = None
        for i in range(self._attempts):
            try:
                result = self._inner.answer(query)
            except Exception as e:
                msg = str(e).lower()
                if "quota" in msg or "billing" in msg:
                    raise                      # quota won't heal by retrying
                last = e
                if i < self._attempts - 1:
                    time.sleep(self._base_delay * (2 ** i))
                continue
            self._cache[query] = result
            return result
        raise last

    