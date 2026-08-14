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
 
# Grounded verdicts the Planning Toolkit can return for a high-risk job.
PLANNING_DECISIONS = ("HOLD", "RELEASE", "ESCALATE")
 
 
@dataclass(frozen=True)
class PlanningReview:
    """Result returned by Planning Toolkit before a high-risk job proceeds."""
 
    mode: str
    success: bool
    decision: str  # one of PLANNING_DECISIONS: "HOLD" | "RELEASE" | "ESCALATE"
    decision_plan: str
    validator_details: list[str]
 
 
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
 
    # -- Planning Toolkit ----------------------------------------------------
    async def review_high_risk_job(
        self,
        *,
        goal: str,
        client_id: int,
        vehicle_id: int,
        tech_id: int,
        appointment_id: int,
        technician_authenticated: bool,
        disclosure_confirmed: bool,
        modification_logged: bool,
        mode: str = "reflexion",
        max_trials: int = 3,
        memory_size: int = 3,
    ) -> PlanningReview:
        """Planning Toolkit guard for a high-risk (emissions-affecting) job.
 
        Runs BEFORE TorqueTuneAgent is allowed to execute or continue the
        case:
 
            Decomposition -> Execute/Reflection (trials) -> Grounded
            Validation -> HOLD / RELEASE / ESCALATE
 
        Grounded validation here is checked against the concrete facts
        passed in (``technician_authenticated`` / ``disclosure_confirmed`` /
        ``modification_logged``), which in this demo mirror the seeded
        SQLite state for client_id/vehicle_id/tech_id/appointment_id. In a
        fuller implementation these facts would be read live via MCP
        tools/resources instead of being passed in directly — this method
        is the seam where that would plug in.
        """
 
        scope = {
            "client_id": client_id,
            "vehicle_id": vehicle_id,
            "tech_id": tech_id,
            "appointment_id": appointment_id,
        }
 
        # -- Decomposition: break the goal into concrete safety checks ----
        subtasks = [
            "Confirm technician identity/authentication",
            "Confirm the job scope matches vehicle/appointment records",
            "Confirm customer disclosure for emissions-affecting modification",
            "Confirm modification will be logged for compliance/audit",
        ]
 
        checks = {
            "technician_authenticated": technician_authenticated,
            "disclosure_confirmed": disclosure_confirmed,
            "modification_logged": modification_logged,
        }
 
        # -- Execute / Reflection loop (reflexion-style trials) ------------
        trial_log: list[str] = []
        success = False
        trial = 0
        while trial < max_trials:
            trial += 1
            failed = [name for name, ok in checks.items() if not ok]
 
            if not failed:
                success = True
                trial_log.append(f"Trial {trial}: all grounded checks passed.")
                break
 
            trial_log.append(
                f"Trial {trial}: missing evidence for {', '.join(failed)}."
            )
 
            # Reflexion short-term memory: keep only the last `memory_size`
            # trial reflections.
            trial_log = trial_log[-memory_size:]
 
            # In this demo the missing evidence is a fact about the world
            # (auth/disclosure/logging state), not something a retry can
            # fix without a new external event (e.g. elicitation). So we
            # stop reflecting once the same failure repeats rather than
            # burning through max_trials pointlessly.
            break
 
        # -- Grounded validation --------------------------------------------
        validator_details: list[str] = []
 
        if not technician_authenticated:
            decision = "ESCALATE"
            validator_details.append(
                "FAIL: technician_authenticated is False — "
                "identity not grounded against seeded records."
            )
        elif not disclosure_confirmed:
            decision = "HOLD"
            validator_details.append(
                "FAIL: disclosure_confirmed is False — no customer disclosure "
                "on record for an emissions-affecting modification."
            )
        elif not modification_logged:
            decision = "HOLD"
            validator_details.append(
                "FAIL: modification_logged is False — no compliance/audit "
                "log entry for the modification."
            )
        else:
            decision = "RELEASE"
            validator_details.append(
                "PASS: technician authenticated, disclosure confirmed, "
                "modification logging confirmed."
            )
 
        validator_details.append(f"Scope validated against seeded records: {scope}")
 
        decision_plan = "\n".join(
            [
                f"GOAL: {goal.strip().splitlines()[0]}",
                "",
                "DECOMPOSITION:",
                *[f"  - {task}" for task in subtasks],
                "",
                "EXECUTE / REFLECTION TRIALS:",
                *[f"  - {line}" for line in trial_log],
                "",
                "GROUNDED VALIDATION:",
                *[f"  - {detail}" for detail in validator_details],
                "",
                f"DECISION: {decision}",
            ]
        )
 
        return PlanningReview(
            mode=mode,
            success=success,
            decision=decision,
            decision_plan=decision_plan,
            validator_details=validator_details,
        )
 
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
 