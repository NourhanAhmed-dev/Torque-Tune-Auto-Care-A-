from __future__ import annotations

import argparse
import asyncio
import json
from agent.client import TorqueTuneAgent
from agent.config import load_config
from agent.helpers import call_tool_with_progress
from dotenv import load_dotenv

load_dotenv(override=True)


def _section(title: str) -> None:
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)


async def progress_callback(progress: float, total: float | None, message: str | None) -> None:
    print(f"   [progress notification] {progress}/{total}: {message}")


async def run(auto: bool) -> None:
    config = load_config()
    if auto:
        object.__setattr__(
            config,
            "scripted_elicitation_responses",
            ({"confirm": True},),
        )

    async with TorqueTuneAgent(config) as agent:
        _section("1) CAPABILITY NEGOTIATION")
        assert agent.negotiated is not None
        print(f"Server declares tools.listChanged = {agent.negotiated.supports_tools_list_changed}")

        _section("2) BASELINE TOOL SET (Unauthenticated)")
        print("Available Tools:", sorted(t.name for t in agent.tools))

        _section("3) AUTHENTICATE TECHNICIAN & NOTIFICATIONS (tools/list_changed)")
        auth = await call_tool_with_progress(
            agent,
            "authenticate_technician",
            {"tech_id": 1, "tech_phone": "01099998888"},
        )
        print("Auth Result:", auth.content[0].text)
        
        await asyncio.sleep(0.3)
        
        # wait for any pending notification tasks to complete (e.g., catalog refresh)
        await agent.wait_for_pending_notifications()
        
        print("Tools after authentication unlock:", sorted(t.name for t in agent.tools))
        _section("4) DEFENSIVE TOOL DESIGN & VALIDATION (Cosmetic Modification)")
        cosmetic = await call_tool_with_progress(
            agent,
            "log_tuning_modification",
            {
                "vehicle_id": 2,
                "tech_id": 1,
                "category": "cosmetic",
                "description": "New alloy wheels installed",
                "status": "completed"
            },
        )
        print("Result:", cosmetic.content[0].text)

        _section("5) ELICITATION & SAMPLING (Emissions-Affecting Modification)")
        risky = await call_tool_with_progress(
            agent,
            "log_tuning_modification",
            {
                "vehicle_id": 3,
                "tech_id": 1,
                "category": "emissions_affecting",
                "description": "Catalytic converter delete",
                "status": "completed"
            },
        )
        print("Result:", risky.content[0].text)

        _section("6) INVOICE CREATION & AUTHORIZATION CHECK")
        invoice = await call_tool_with_progress(
            agent,
            "create_invoice",
            {"client_id": 1, "total_amount": 950.0, "payment": "paid"},
        )
        print("Invoice Result:", invoice.content[0].text)

        _section("7) PROGRESS TRACKING (Generate Service Report)")
        if agent.session:
            report = await agent.session.call_tool(
                "generate_service_report",
                {"client_id": 1},
                progress_callback=progress_callback,
                meta={"progressToken": "report-1"},
            )
            report_data = json.loads(report.content[0].text)
            print("Report generated successfully. Report keys:", list(report_data.keys()))

        _section("8) RESOURCES & PROMPTS CHECK")
        if agent.resources:
            policy_text = await agent.read_resource_text(agent.resources[0].uri)
            print("Policy Resource Content:\n", policy_text[:200], "...")

        messages = await agent.get_prompt_messages(
            "tuning_disclosure",
            {"vehicle_id": "3", "modification": "ECU remap"},
        )
        print("Rendered Prompt:\n", messages[0].content.text)

        _section("9) GEMINI REASONING LOOP")
        if agent._llm:
            reply = await agent.run_turn("What modifications were performed for vehicle 3 and what are the compliance rules?")
            print("Gemini Answer:\n", reply)
        else:
            print("Gemini API key not configured.")

        _section("DONE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto", action="store_true", help="Use scripted parameters.")
    args = parser.parse_args()
    asyncio.run(run(auto=args.auto))


if __name__ == "__main__":
    main()