from __future__ import annotations 
import argparse
import asyncio
import re
from dotenv import load_dotenv 
from agent.Agent_Clint import PlanningReview, TorqueTuneAgent
from agent.config import load_config
 
 
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
 
 
async def run_planning_guard(agent: TorqueTuneAgent, request: str) -> PlanningReview:
    """
    Planning Toolkit is used BEFORE the agent executes or continues a
    high-risk case (Decomposition/Plan -> Execute/Reflection -> Grounded
    Validation -> HOLD/RELEASE/ESCALATE).
 
    This demo uses the seeded database relationship:
    client 2 -> vehicle 3 -> technician 2 -> appointment 3.
    """
 
    section("PLANNING GUARD: DECOMPOSITION + REFLEXION + SQLITE VALIDATION")
 
    review = await agent.review_high_risk_job(
        goal=request,
        client_id=2,
        vehicle_id=3,
        tech_id=2,
        appointment_id=3,
 
        # Known/assumed up front for this seeded demo case, so the guard
        # can run before any live MCP tool calls happen.
        technician_authenticated=True,
 
        # No disclosure evidence is supplied intentionally.
        # The safe expected decision is HOLD / ESCALATE.
        disclosure_confirmed=False,
        modification_logged=False,
 
        mode="reflexion",
        max_trials=3,
        memory_size=3,
    )
 
    print(f"Planning accepted: {review.success}")
    print(f"Planning decision: {review.decision}")
    print("\nPlanning output (decomposition -> reflection -> validation):\n")
    print(review.decision_plan)
 
    print("\nGrounded validator feedback:")
    for detail in review.validator_details:
        print(f"- {detail}")
 
    return review
 
 
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
 
    # For an automated demo, this accepts the emissions disclosure if the user
    # explicitly requests an emissions modification. Remove this line for manual
    # console confirmation instead.
    object.__setattr__(
        config,
        "scripted_elicitation_responses",
        ({"confirm": True, "customer_signature": "Demo Customer"},),
    )
 
    async with TorqueTuneAgent(config) as agent:
        section("CASE STUDY: USER REQUEST")
        print(request)
 
        # ---- HIGH-RISK CHECK -------------------------------------------
        section("STEP 1: IS THIS A HIGH-RISK CASE?")
        high_risk = is_high_risk(request)
        print(f"High risk case: {high_risk}")
 
        # ---- PLANNING TOOLKIT (runs BEFORE the agent touches the case) --
        planning_result = ""
        decision = "RELEASE"  # nothing to gate on when the case isn't high risk
 
        if high_risk:
            review: PlanningReview = await run_planning_guard(agent, request)
            planning_result = review.decision_plan
            decision = review.decision
 
        guard_note = build_guard_note(planning_result, decision)
 
        # ---- TORQUETUNEAGENT EXECUTES / CONTINUES THE CASE --------------
        section("STEP 2: TORQUETUNEAGENT EXECUTES THE CASE")
        print("Initial tools:", sorted(tool.name for tool in agent.tools))
 
        first_answer = await agent.run_turn(
            f"{SYSTEM_INSTRUCTIONS}\n\nUSER REQUEST:\n{request}{guard_note}"
        )
        print("\nAgent response:\n")
        print(first_answer)
 
        # Authentication may trigger the MCP tools/list_changed notification.
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
 
        final_answer = await agent.run_turn(
            f"{SYSTEM_INSTRUCTIONS}\n\n{continuation}"
        )
 
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

    parser = argparse.ArgumentParser(
        description="Torque-Tune interactive agent case-study demo"
    )
    parser.add_argument(
        "--request",
        help="Service request to send to the agent.",
    )
    args = parser.parse_args()

    request = args.request.strip() if args.request else DEFAULT_CASE

    asyncio.run(run_case(request))


if __name__ == "__main__":
    main()