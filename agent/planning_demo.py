"""Torque-Tune case-study demo: Week-4 planning guard + existing MCP agent.

The planning guard (decomposition -> routing -> Reflexion -> grounded SQLite
validation) runs BEFORE the memory/RAG agent executes a high-risk case.
The memory/RAG code path (run_turn) is reused for execution, never duplicated.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.planning_client import TorqueTuneAgent
from agent.config import load_config
from planning.torque_tune_environment import PlanningContext, TorqueTuneEnvironment
from planning_toolkit.planning_lab.algorithms import (
    Environment,
    decompose_goal,
    reflexion,
)

from planning_toolkit.planning_lab.algorithms.router import route_subtask


DEFAULT_CASE = """
I am technician Mahmoud Salem (tech_id 2, phone 01077776666).
Review the catalytic-converter-delete request for vehicle 3, assigned to me in
appointment 3. Check the vehicle/service information and the compliance policy.
Before performing, completing, or invoicing any emissions-affecting modification,
make a safe decision and provide the next actions. Do not invent facts.
""".strip()

SYSTEM_INSTRUCTIONS = """
You are the Torque-Tune case-study agent.
Handle the customer's request end-to-end using MCP tools only when useful.
Rules:
1. Start from the currently available MCP tools.
2. If a restricted operation or service report is necessary, authenticate only
   with technician credentials explicitly supplied by the user.
3. After authentication, the tool list may change. The demo will give you a
   continuation turn after the catalog refresh.
4. For policy, bulletin, torque, specification, warranty, or procedure questions,
   use grounded knowledge-base evidence. Never invent a fact.
5. For emissions-affecting work, do not mark work complete or create an invoice
   unless customer disclosure has been confirmed through MCP elicitation.
6. If evidence is missing, choose HOLD or ESCALATE and explain safe next actions.
7. Keep the response concise, evidence-based, and suitable for a service advisor.
""".strip()


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def is_high_risk(request: str) -> bool:
    return bool(
        re.search(
            r"\b(ecu\s*remap|decat|catalytic\s*converter|dpf|egr|emissions)\b",
            request,
            re.IGNORECASE,
        )
    )


@dataclass(frozen=True)
class PlanningReview:
    mode: str
    success: bool
    decision: str
    decision_plan: str
    validator_details: list[str]

class _TextNormalizingLLM:
    """Gemini 3.x may return content as a list of parts; the toolkit expects str."""

    def __init__(self, inner):
        self._inner = inner

    @staticmethod
    def _normalize(out):
        content = getattr(out, "content", "")
        if isinstance(content, list):
            out.content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return out

    def invoke(self, messages, **kw):
        return self._normalize(self._inner.invoke(messages, **kw))

    def with_structured_output(self, schema, *, method):
        return self._inner.with_structured_output(schema, method=method)

    
async def run_planning_guard(request: str) -> PlanningReview:
    """Real Planning Toolkit guard: decomposition -> routing -> Reflexion -> SQLite validation."""
    section("PLANNING GUARD: DECOMPOSITION + ROUTING + REFLEXION + SQLITE VALIDATION")
    llm = _TextNormalizingLLM(ChatGoogleGenerativeAI(
        google_api_key=os.environ["GEMINI_API_KEY"],
        model=os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        temperature=0.2,
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        },
    ))
    validator = TorqueTuneEnvironment(PlanningContext(
        client_id=2, vehicle_id=3, tech_id=2, appointment_id=3,
        technician_authenticated=True,
        disclosure_confirmed=False,   
        modification_logged=False,
        request_text=request,
    ))
    environment = Environment(validator.evaluate)

    plan = decompose_goal(request, llm)
    print("Execution batches:", plan.execution_batches())
    for task in plan.tasks:
        print(f"  route[{task.id}] -> {route_subtask(task.instruction).value}")

    outcome = reflexion(request, llm, environment, max_trials=3, memory_size=3)
    for trial in outcome.trials:
        print(f"Trial {trial.number}: success={trial.feedback.success}")
        if trial.reflection:
            print(f"  reflection: {trial.reflection}")

    decision = validator._decision(outcome.output) or "HOLD"
    feedback = validator.evaluate(outcome.output)
    print("\nGrounded validator feedback:")
    for detail in feedback.details:
        print(f"- {detail}")
    return PlanningReview("reflexion", outcome.success, decision, outcome.output, feedback.details)


def build_guard_note(planning_result: str, decision: str) -> str:
    if not planning_result:
        return ""
    return f"""
Planning Toolkit result (must be respected as a hard safety constraint):
{planning_result}

Decision: {decision}
- If decision is HOLD or ESCALATE: do NOT perform, complete, or invoice the
  modification. Explain the safe next actions instead and stop after any
  necessary authentication / read-only checks.
- If decision is RELEASE: continue and execute the case normally, still
  respecting the elicitation/disclosure rules in the system instructions.
"""


async def run_case(request: str) -> None:
    config = load_config()
    # Automated demo: script the disclosure elicitation. Remove for manual confirmation.
    object.__setattr__(
        config,
        "scripted_elicitation_responses",
        ({"confirm": True, "customer_signature": "Demo Customer"},),
    )

    async with TorqueTuneAgent(config) as agent:
        section("CASE STUDY: USER REQUEST")
        print(request)

        section("STEP 1: IS THIS A HIGH-RISK CASE?")
        high_risk = is_high_risk(request)
        print(f"High risk case: {high_risk}")

        planning_result = ""
        decision = "RELEASE"  # nothing to gate on when the case isn't high risk
        if high_risk:
            review = await run_planning_guard(request)
            planning_result = review.decision_plan
            decision = review.decision
        guard_note = build_guard_note(planning_result, decision)

        section("STEP 2: TORQUETUNEAGENT EXECUTES THE CASE")
        print("Initial tools:", sorted(tool.name for tool in agent.tools))
        first_answer = await agent.run_turn(
            f"{SYSTEM_INSTRUCTIONS}\n\nUSER REQUEST:\n{request}{guard_note}"
        )
        print("\nAgent response:\n")
        print(first_answer)

        await asyncio.sleep(0.5)
        await agent.wait_for_pending_notifications()

        section("MCP CATALOG AFTER AUTHENTICATION")
        print("Current tools:", sorted(tool.name for tool in agent.tools))

        section("STEP 3: TORQUETUNEAGENT CONTINUES / CLOSES THE CASE")
        continuation = f"""
Continue the same user request below.
The MCP tool catalog has now been refreshed after authentication.
Use any newly available MCP tools only when they are necessary.
Original request:
{request}
{guard_note}
"""
        final_answer = await agent.run_turn(f"{SYSTEM_INSTRUCTIONS}\n\n{continuation}")
        print("\nFinal agent response:\n")
        print(final_answer)

        section("MEMORY / RAG SUMMARY")
        print("Verified semantic facts:", len(agent.semantic_facts()))
        print("Recent routing decisions:")
        for line in agent.routing_log(limit=5):
            print("-", line)

        section("CASE STUDY COMPLETE")


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Torque-Tune interactive agent case-study demo")
    parser.add_argument("--request", help="Service request to send to the agent.")
    args = parser.parse_args()
    request = args.request.strip() if args.request else DEFAULT_CASE
    asyncio.run(run_case(request))


if __name__ == "__main__":
    main()