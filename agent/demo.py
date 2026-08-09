"""End-to-end demo: every Session-1 + Session-3 concern firing, in order.

Thin driver only — it sends inputs and prints what the system did.
All behaviour lives in mcp_server/, memory/, rag/, context_eval/, agent/pipeline.py.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from agent.client import TorqueTuneAgent
from agent.config import load_config
from agent.helpers import call_tool_with_progress


load_dotenv(override=True)


def _section(title: str) -> None:
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)


async def progress_callback(progress, total, message):
    print(f"   [progress] {progress}/{total}: {message}")


def _format_rag(result) -> str:
    if isinstance(result, str):
        return result
    answer = getattr(result, "answer", None) or (
        result.get("answer") if isinstance(result, dict) else str(result))
    retrieved = getattr(result, "retrieved", None) or (
        result.get("retrieved") if isinstance(result, dict) else [])
    arch = getattr(result, "architecture", "?") or (
        result.get("architecture") if isinstance(result, dict) else "?")
    preview = (answer[:220] + "…") if isinstance(answer, str) and len(answer) > 220 else answer
    return f"arch={arch} | retrieved={len(retrieved)} | answer: {preview}"


async def _answer(engine, q):
    fn = getattr(engine, "answer", None) or getattr(engine, "run", None) or getattr(engine, "query", None)
    res = fn(q)
    if inspect.isawaitable(res):
        res = await res
    return res


# ── Session-1: MCP protocol ──────────────────────────────────────────────
async def s01_capability(agent):
    _section("1) CAPABILITY NEGOTIATION")
    assert agent.negotiated is not None
    print(f"Server declares tools.listChanged = {agent.negotiated.supports_tools_list_changed}")


async def s02_baseline_tools(agent):
    _section("2) BASELINE TOOL SET (Unauthenticated)")
    print("Available Tools:", sorted(t.name for t in agent.tools))


async def s03_auth_notifications(agent):
    _section("3) AUTHENTICATE TECHNICIAN & NOTIFICATIONS (tools/list_changed)")
    auth = await call_tool_with_progress(agent, "authenticate_technician",
                                         {"tech_id": 1, "tech_phone": "01099998888"})
    print("Auth Result:", auth.content[0].text)
    await asyncio.sleep(0.3)
    await agent.wait_for_pending_notifications()
    print("Tools after authentication unlock:", sorted(t.name for t in agent.tools))


async def s04_defensive_design(agent):
    _section("4) DEFENSIVE TOOL DESIGN & VALIDATION (Cosmetic Modification)")
    r = await call_tool_with_progress(agent, "log_tuning_modification", {
        "vehicle_id": 2, "tech_id": 1, "category": "cosmetic",
        "description": "New alloy wheels installed", "status": "completed"})
    print("Result:", r.content[0].text)


async def s05_elicitation_sampling(agent):
    _section("5) ELICITATION & SAMPLING (Emissions-Affecting Modification)")
    r = await call_tool_with_progress(agent, "log_tuning_modification", {
        "vehicle_id": 3, "tech_id": 1, "category": "emissions_affecting",
        "description": "Catalytic converter delete", "status": "completed"})
    print("Result:", r.content[0].text)


async def s06_invoice(agent):
    _section("6) INVOICE CREATION & AUTHORIZATION CHECK")
    r = await call_tool_with_progress(agent, "create_invoice",
                                      {"client_id": 1, "total_amount": 950.0, "payment": "paid"})
    print("Invoice Result:", r.content[0].text)


async def s07_progress(agent):
    _section("7) PROGRESS TRACKING (Generate Service Report)")
    if agent.session:
        report = await agent.session.call_tool(
            "generate_service_report", {"client_id": 1},
            progress_callback=progress_callback, meta={"progressToken": "report-1"})
        print("Report generated successfully. Report keys:",
              list(json.loads(report.content[0].text).keys()))


async def s08_resources_prompts(agent):
    _section("8) RESOURCES & PROMPTS CHECK")
    if agent.resources:
        print("Policy Resource Content:\n",
              (await agent.read_resource_text(agent.resources[0].uri))[:200], "...")
    messages = await agent.get_prompt_messages(
        "tuning_disclosure", {"vehicle_id": "3", "modification": "ECU remap"})
    print("Rendered Prompt:\n", messages[0].content.text)


async def s09_gemini_loop(agent):
    _section("9) GEMINI REASONING LOOP")
    if agent._llm:
        print("Gemini Answer:\n", await agent.run_turn(
            "What modifications were performed for vehicle 3 and what are the compliance rules?"))
    else:
        print("Gemini API key not configured.")


# ── Session-3: memory, context, retrieval ────────────────────────────────
def s10_promote_or_drop(agent):
    _section("10) MEMORY: PROMOTE-OR-DROP ON OVERFLOW")
    promoted = agent.memory.route_message({
        "role": "user",
        "content": "IMPORTANT: Installed an aftermarket radiator on vehicle 3. Non-OEM part — warranty affected.",
        "metadata": {"vehicle_id": 3, "client_id": 1, "tech_id": 1}})
    discarded = agent.memory.route_message(
        {"role": "user", "content": "ok thanks", "metadata": {}})
    print("Router decisions (same code path as the live loop):")
    print(f"  radiator note : {'PROMOTED to episodic' if promoted else 'discarded'}")
    print(f"  filler 'ok'   : {'PROMOTED (unexpected)' if discarded else 'DISCARDED as expected'}")
    if log := agent.memory.routing_log():
        print("  routing log tail:")
        for line in log[-4:]:
            print("   ", line)


def s11_consolidation(agent):
    _section("11) CONSOLIDATION RESOLVES REAL CONTRADICTION")
    from memory.models import EpisodicMemory
    from memory.utils import generate_id
    for text in ("Vehicle 4's service manual specifies 5W-30 oil.",
                 "Correction: Vehicle 4's manual updated — now specifies 0W-20 oil."):
        agent.memory.episodic.add(EpisodicMemory(
            memory_id=generate_id(), content=text, memory_type="preference",
            importance=6, vehicle_id=4, metadata={"vehicle_id": 4}))
    agent.memory.consolidate_now()
    print("Semantic facts after consolidation (versioned, dated):")
    print(json.dumps(agent.memory.semantic_facts(), indent=2, default=str))


async def s12_selfrag(agent):
    _section("12) SELF-RAG: GROUNDED PASS vs UNSUPPORTED CATCH")
    if not agent._llm:
        print("Gemini API key not configured.")
        return
    print("In-corpus (should pass):\n ", await agent.run_turn(
        "What does TSB-2026-002 say about EcoBoost 2.3 carbon buildup?"))
    print("Out-of-corpus (should be flagged):\n ", await agent.run_turn(
        "What's the recommended tire pressure for a 1987 DeLorean DMC-12?"))


def s13_context_strategies():
    _section("13) CONTEXT MANAGEMENT: ALL FOUR STRATEGIES ON THE FROZEN SUITE")
    from context_eval import observation_masking, recursive_summary, sliding_window, zone_pruning
    from context_eval.recursive_summary import _naive_summarizer
    from context_eval.test_cases import BURIAL_CASES, CRITICAL_FACT_SNIPPET
    from context_eval.utils import transcript_tokens
    case = BURIAL_CASES[0]
    print(f"case 0: {len(case)} msgs, {transcript_tokens(case)} tokens")
    for name, fn, kw in [
        ("sliding_window", sliding_window.prune, {"window_size": 10}),
        ("observation_masking", observation_masking.prune, {"keep_last_n_tool_outputs": 3}),
        ("recursive_summary", recursive_summary.prune, {"chunk_size": 15, "summarizer": _naive_summarizer}),
        ("zone_pruning", zone_pruning.prune, {"summarizer": _naive_summarizer}),
    ]:
        pruned = fn(case, **kw)
        recalled = any(CRITICAL_FACT_SNIPPET.lower() in m.content.lower() for m in pruned)
        print(f"  {name:22s} {transcript_tokens(pruned):6d} tokens  recall={recalled}")
    if (t := Path("context_eval/comparison_table.md")).exists():
        print("\nFrozen full-run table:")
        print(t.read_text(encoding="utf-8"))


async def s14_retrieval(agent):
    _section("14) RETRIEVAL ARCHITECTURES: SAME QUESTION, THREE WAYS")
    q = "What does TSB-2026-002 say about carbon buildup on EcoBoost 2.3 intake valves?"
    from rag.hybrid_rag import HybridRAG
    from rag.naive_rag import NaiveRAG

    naive = NaiveRAG()
    hybrid = HybridRAG()
    for label, engine in (("Naive", naive), ("Hybrid", hybrid),
                          ("Agentic", agent.memory.agentic_rag)):
        try:
            print(f"{label} RAG:\n  ", _format_rag(await _answer(engine, q)))
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                print(f"{label} RAG: skipped — free-tier quota exhausted; engine implemented in rag/.")
            else:
                raise
        time.sleep(5)


async def run(auto: bool) -> None:
    config = load_config()
    if auto:
        object.__setattr__(config, "scripted_elicitation_responses", ({"confirm": True},))
    async with TorqueTuneAgent(config) as agent:
        await s01_capability(agent)
        await s02_baseline_tools(agent)
        await s03_auth_notifications(agent)
        await s04_defensive_design(agent)
        await s05_elicitation_sampling(agent)
        await s06_invoice(agent)
        await s07_progress(agent)
        await s08_resources_prompts(agent)
        await s09_gemini_loop(agent)
        s10_promote_or_drop(agent)
        s11_consolidation(agent)
        await s12_selfrag(agent)
        s13_context_strategies()
        await s14_retrieval(agent)
        _section("DONE")


def main() -> None:
    parser = argparse.ArgumentParser(description="Torque-Tune end-to-end demo")
    parser.add_argument("--auto", action="store_true", help="Use scripted parameters.")
    asyncio.run(run(auto=parser.parse_args().auto))


if __name__ == "__main__":
    main()
