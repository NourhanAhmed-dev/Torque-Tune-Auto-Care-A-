from __future__ import annotations
from dataclasses import dataclass
import asyncio
from contextlib import AsyncExitStack
from typing import Any
 
from google import genai
from google.genai import types as gtypes
from mcp import ClientSession, types as mcp_types
 
import agent.elicitation
import agent.notification
import agent.sampling
import agent.tools
from agent.config import AgentConfig
from agent.handshake import NegotiatedCapabilities, perform_handshake
from agent.helpers import (
    call_tool_with_progress,
    mcp_tools_to_gemini,
    tool_result_to_text,
)
from agent.pipeline import SessionPipeline
from agent.transport import open_transport
 
class TorqueTuneAgent:
    """Core agent orchestrator for Torque-Tune-Auto-Care MCP system.
 
    Session-3 memory/RAG concerns live in agent/pipeline.py (self.memory);
    the seven HOOKs in run_turn() wire them into the live loop.
    """
 
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.negotiated: NegotiatedCapabilities | None = None
        self.tools: list[mcp_types.Tool] = []
        self.resources: list[mcp_types.Resource] = []
        self.prompts: list[mcp_types.Prompt] = []
 
        self._elicitation_queue: list[dict[str, Any]] = list(
            config.scripted_elicitation_responses
        )
        self._pending_notification_tasks: list[asyncio.Task[None]] = []
 
        self._llm = (
            genai.Client(api_key=config.gemini_api_key)
            if config.gemini_api_key
            else None
        )
        # Session-3: every memory/RAG concern lives in agent/pipeline.py
        self.memory = SessionPipeline()
 
    # -- readable aliases so demo/README snippets stay natural ------------
    @property
    def short_term(self):
        return self.memory.short_term
 
    @property
    def scratchpad(self):
        return self.memory.scratchpad
 
    @property
    def router(self):
        return self.memory.router
 
    @property
    def episodic(self):
        return self.memory.episodic
 
    @property
    def semantic(self):
        return self.memory.semantic
 
    @property
    def consolidator(self):
        return self.memory.consolidator
 
    @property
    def rag(self):
        return self.memory.naive_rag
 
    @property
    def agentic_rag(self):
        return self.memory.agentic_rag
 
    def semantic_facts(self) -> list:
        return self.memory.semantic_facts()
 
    def routing_log(self, limit: int = 15) -> list:
        return self.memory.routing_log(limit)
 
    # -- MCP lifecycle (unchanged from Session-1) --------------------------
    async def __aenter__(self) -> TorqueTuneAgent:
 
        transport_result = await self._exit_stack.enter_async_context(
            open_transport(self.config)
        )
        read, write = transport_result[0], transport_result[1]
 
        self.session = await self._exit_stack.enter_async_context(
            ClientSession(
                read,
                write,
                sampling_callback=lambda ctx, params: agent.sampling.handle_sampling(
                    self, params
                ),
                elicitation_callback=lambda ctx, params: agent.elicitation.handle_elicitation(
                    self, params
                ),
                message_handler=lambda *args, **kwargs: agent.notification.handle_notification(
                    self, *args, **kwargs
                ),
                client_info=mcp_types.Implementation(
                    name=self.config.client_name,
                    version=self.config.client_version,
                ),
            )
        )
        self.negotiated = await perform_handshake(self.session)
        await agent.tools.refresh_catalog(self)
        return self
 
    async def __aexit__(self, *exc_info: object) -> None:
        try:
            await self._exit_stack.aclose()
        except BaseExceptionGroup as eg:
            import anyio
 
            if not all(isinstance(e, anyio.BrokenResourceError) for e in eg.exceptions):
                raise
 
    async def wait_for_pending_notifications(self) -> None:
        tasks, self._pending_notification_tasks = self._pending_notification_tasks, []
        if tasks:
            await asyncio.gather(*tasks)
 
    async def read_resource_text(self, uri: str) -> str:
        assert self.session is not None
        if self.negotiated and not self.negotiated.supports_resources:
            self.negotiated.require("resources", needed_for=f"reading {uri}")
        result = await self.session.read_resource(uri)
        parts = [
            c.text
            for c in result.contents
            if isinstance(c, mcp_types.TextResourceContents)
        ]
        return "\n".join(parts)
 
    async def get_prompt_messages(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> list[mcp_types.PromptMessage]:
        assert self.session is not None
        result = await self.session.get_prompt(name, arguments)
        return result.messages
 
    # -- live loop with the 7 Session-3 hooks ------------------------------
    async def run_turn(self, user_message: str, *, system: str | None = None) -> str:
        if self._llm is None:
            raise RuntimeError("GEMINI_API_KEY is required to run the agent loop.")
        assert self.session is not None
        if system is None:
            system = """
You are Torque-Tune-Auto-Care's expert AI technician assistant.
Rules:
- Always authenticate the technician before executing restricted write tools.
- Handle emissions-affecting modifications with proper regulatory disclosures and risk summaries.
- Base every answer strictly on tool outputs and database records.
- Never invent tuning specifications or vehicle modifications.
"""
        gen_config = gtypes.GenerateContentConfig(
            system_instruction=system,
            tools=mcp_tools_to_gemini(self.tools),
        )
 
        # HOOK 1 — buffer + scratchpad (all Session-3 state lives in self.memory)
        self.memory.ingest("user", user_message)
        self.memory.note_goal(user_message)
        # HOOK 2 — long-term recall, Self-RAG verified
        recalled = self.memory.recall(user_message)
        # HOOK 3 — grounded retrieval for knowledge-shaped questions
        kb = (
            await self.memory.retrieve(user_message)
            if self.memory.needs_knowledge(user_message)
            else None
        )
        # HOOK 4 — pruned context (shipped strategy); scratchpad never pruned
        contents = self.memory.compose_context(user_message, recalled, kb)
 
        while True:
            response = await self._llm.aio.models.generate_content(
                model=self.config.gemini_model,
                contents=contents,
                config=gen_config,
            )
 
            if not response.function_calls:
                final_answer = response.text or ""
                # HOOK 5 — Self-RAG gate before the user sees anything
                supported, critique = self.memory.verify(
                    user_message, self.memory.sources_of(recalled, kb), final_answer
                )
                if not supported:
                    final_answer = f"[Low confidence — {critique}] {final_answer}"
                self.memory.ingest("assistant", final_answer)
                self.memory.tick_consolidation()
                return final_answer
 
            if response.candidates and response.candidates[0].content:
                contents.append(response.candidates[0].content)
 
            function_responses = []
            for call in response.function_calls:
                print(f"[agent] calling tool: {call.name}({call.args})")
                args = dict(call.args) if call.args else {}
                result = await call_tool_with_progress(self, call.name, args)
                function_responses.append(
                    gtypes.Part.from_function_response(
                        name=call.name,
                        response={
                            "content": tool_result_to_text(result),
                            "is_error": result.isError or False,
                        },
                    )
                )
                # HOOK 6 — tool result enters buffer; overflow fires promote-or-drop
                scope_keys = {
                    "client_id",
                    "customer_id",
                    "vehicle_id",
                    "tech_id",
                    "technician_id",
                    "appointment_id",
                }
                scope = {
                    key: value
                    for key, value in args.items()
                    if key in scope_keys and value is not None
                }
                self.memory.update_scope(scope)
                self.memory.scratchpad.add_step(f"Called MCP tool: {call.name}")
                self.memory.ingest(
                    "tool",
                    tool_result_to_text(result),
                    metadata={"tool_name": call.name, **scope},
                )
 
            contents.append(gtypes.Content(role="user", parts=function_responses))
            # HOOK 7 — periodic consolidation (separate pass, own trigger)
            self.memory.tick_consolidation()
 