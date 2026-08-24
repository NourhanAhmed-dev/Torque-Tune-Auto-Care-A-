"""Agent service — chat with the TorqueTuneAgent (Sessions 1-3) from the
platform. The agent lives on its own event loop in a background thread;
HTTP endpoints forward calls via asyncio.run_coroutine_threadsafe."""
from __future__ import annotations

import asyncio
import threading

_agent = None
_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _ensure_agent():
    global _agent, _loop
    with _lock:
        if _agent is None:
            from agent.client import TorqueTuneAgent
            from agent.config import load_config

            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True).start()
            _agent = TorqueTuneAgent(load_config())
            asyncio.run_coroutine_threadsafe(_agent.__aenter__(), _loop).result(30)
    return _agent, _loop


def list_agents():
    """Agents available on the platform."""
    return [
        {"id": "tuning-technician",
         "description": "TorqueTuneAgent (Sessions 1-3): tuning assistant "
                        "with MCP tools, RAG and memory.",
         "kind": "chat"},
        {"id": "fleet-rescue",
         "description": "Fleet Rescue concierge: tell it who you are and what "
                        "happened; it opens and tracks the rescue for you.",
         "kind": "chat"},
    ]


def chat(message: str, agent: str = "tuning-technician") -> dict:
    if agent != "tuning-technician":
        raise ValueError(f"unknown agent: {agent}")
    a, loop = _ensure_agent()
    fut = asyncio.run_coroutine_threadsafe(a.run_turn(message), loop)
    return {"reply": fut.result(120)}