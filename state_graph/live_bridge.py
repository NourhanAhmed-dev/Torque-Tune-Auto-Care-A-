"""Live wiring for Graph 3 — reuses the EXISTING client & server.
MCP : TorqueTuneAgent (agent/client.py) runs on a background event loop;
nodes call LiveMcp.call_tool(...), which forwards to
agent.session.call_tool(...) over the same transport (stdio/http).
Parsing uses agent.helpers.tool_result_to_text — the exact helper the
chat agent uses; no parallel parsing logic.
LLM : genai.Client from agent.config.load_config() (same GEMINI_API_KEY /
GEMINI_MODEL). grounded_reflect.py is not used (lab task only).
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from google import genai

from agent.client import TorqueTuneAgent
from agent.config import load_config
from agent.helpers import tool_result_to_text


class LiveLLM:
    """Strict Gemini adapter with transient-error retry (503/429)."""

    def __init__(self, config=None):
        self.config = config or load_config()
        if not self.config.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY missing from .env")
        self.client = genai.Client(api_key=self.config.gemini_api_key)
        self.model = self.config.gemini_model

    def complete(self, prompt: str) -> str:
        import time
        last: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=prompt,
                    config={"temperature": 0},
                )
                text = (response.text or "").strip()
                if not text:
                    raise RuntimeError("LLM returned empty response")
                return text
            except Exception as exc:
                last = exc
                msg = str(exc).lower()
                transient = any(t in msg for t in
                                ("503", "429", "unavailable", "resource_exhausted", "deadline"))
                if transient and attempt < 2:
                    print(f"[LLM] transient error ({type(exc).__name__}), retrying in {2 ** attempt}s...")
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise last


class LiveMcp:
    """Sync facade over the EXISTING TorqueTuneAgent session.

    anyio cancel scopes are TASK-LOCAL: the stdio transport's TaskGroup is
    entered by __aenter__ and must be exited by __aexit__ in the SAME task,
    otherwise close() dies with 'Attempted to exit cancel scope in a
    different task than it was entered in'. So the whole lifecycle lives in
    ONE owner task on the background loop; tool calls may run in any task.
    """

    def __init__(self, config=None):
        self.config = config or load_config()
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._enter_done = threading.Event()
        self._exit_done = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self.agent: TorqueTuneAgent | None = None
        self._enter_error: BaseException | None = None
        asyncio.run_coroutine_threadsafe(self._lifecycle(), self._loop)
        if not self._enter_done.wait(30):
            raise RuntimeError("MCP session did not open within 30s")
        if self._enter_error is not None:
            raise self._enter_error

    async def _lifecycle(self):
        """Owner task: enters AND exits the agent context in one task."""
        self._stop_event = asyncio.Event()
        try:
            self.agent = TorqueTuneAgent(self.config)
            await self.agent.__aenter__()
        except BaseException as exc:          # report open failures to caller
            self._enter_error = exc
            self._enter_done.set()
            return
        self._enter_done.set()
        await self._stop_event.wait()         # stay alive until close()
        try:
            await self.agent.__aexit__(None, None, None)   # SAME task ✅
        except BaseException:
            pass                              # teardown noise must not kill demo
        finally:
            self._exit_done.set()

    def _run(self, coro, timeout=None):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(
            timeout or self.config.request_timeout_seconds
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self.agent is not None and self.agent.session is not None
        result = self._run(self.agent.session.call_tool(name, arguments), timeout=60)
        if getattr(result, "isError", False):
            raise RuntimeError(f"MCP {name} isError: {tool_result_to_text(result)}")
        raw = tool_result_to_text(result)     # same helper the chat agent uses
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"MCP {name} failed: {data['error']}")
        return data

    def list_tools(self) -> list[str]:
        assert self.agent is not None and self.agent.session is not None
        return [t.name for t in self._run(self.agent.session.list_tools()).tools]

    def close(self):
        async def _stop():
            self._stop_event.set()
        try:
            self._run(_stop(), timeout=5)     # wake owner task → __aexit__ in its own task
            self._exit_done.wait(10)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)


def build_live_stack():
    """(mcp, llm, rag) — everything live, built from the existing infra."""
    try:
        from state_graph.rag_adapter import FleetRagAdapter
    except ImportError:
        from rag_adapter import FleetRagAdapter
    from rag.retriever import VectorRetriever

    cfg = load_config()
    return LiveMcp(cfg), LiveLLM(cfg), FleetRagAdapter(VectorRetriever())