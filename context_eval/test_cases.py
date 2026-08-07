"""
Long-context test suite for context_eval.

Does NOT depend on memory/short_term.py — synthetic transcripts, per the lab brief
("bury an early decision under later tool noise").

GUARDRAIL: once evaluation runs start, this file is FROZEN.
Changing cases between runs invalidates the comparison table.
"""
import json

from .schema import Message, TurnType

CRITICAL_FACT = "Customer says this car was in an accident and has an aftermarket radiator installed."
CRITICAL_FACT_SNIPPET = "aftermarket radiator"
QUERY = "Anything non-stock I must know before ordering the cooling parts?"


def _parts_payload(k: int) -> str:
    """Realistic, varied, ~1.2k tokens of tool JSON — the bloat we bury the decision under."""
    parts = [
        {
            "part_id": f"PT-{k * 30 + j:04d}",
            "name": ["brake_pad_set", "oil_filter", "coolant_radiator", "timing_belt", "spark_plug"][j % 5],
            "in_stock": j % 3 == 0,
            "price_egp": 350 + (j * 37 + k * 11) % 4000,
            "oem": j % 2 == 0,
        }
        for j in range(30)
    ]
    return json.dumps(parts)


def build_burial_transcript(n_tool_turns: int = 30, fact_in_tool_output: bool = False):
    """System turn, one early turn holding the critical fact, `n_tool_turns` of tool bloat,
    then a final user turn that requires recalling the buried fact."""
    out = []
    seq = 0

    def add(turn, role, content, **kw):
        nonlocal seq
        out.append(Message(turn_id=turn, role=role, content=content, seq=seq, **kw))
        seq += 1

    add(0, TurnType.SYSTEM, "You are the Torque-Tune Auto Care service assistant.", pinned=True)

    if fact_in_tool_output:                   
        add(1, TurnType.USER, "Pull up the vehicle history for plate ABC-1234.")
        add(1, TurnType.TOOL_CALL, "get_vehicle_history(...)", tool_name="get_vehicle_history")
        add(1, TurnType.TOOL_RESULT,
            json.dumps({"vehicle_id": 42, "odometer": 81200, "notes": CRITICAL_FACT}),
            tool_name="get_vehicle_history")
        add(1, TurnType.ASSISTANT, "History loaded, noted.")
    else:                                        
        add(1, TurnType.USER, CRITICAL_FACT)
        add(1, TurnType.ASSISTANT, "Got it, noting that down.")

    for k in range(n_tool_turns):                # iteration = turn 
        add(2 + k, TurnType.TOOL_CALL, "search_parts(...)", tool_name="search_parts")
        add(2 + k, TurnType.TOOL_RESULT, _parts_payload(k), tool_name="search_parts")

    add(2 + n_tool_turns, TurnType.USER, QUERY)
    return out


# 10 variations: bloat length varies, and cases 7 & 9 hide the fact inside a tool output.
BURIAL_CASES = [
    build_burial_transcript(n_tool_turns=25 + i, fact_in_tool_output=(i in (7, 9)))
    for i in range(10)
]