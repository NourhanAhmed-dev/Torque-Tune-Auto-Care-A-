"""Graph registry — the single dispatch point the platform uses to talk
to any registered state graph."""
from __future__ import annotations

from ..deps import get_stack


def _wf(graph: str):
    stack = get_stack()
    if graph == "fleet_rescue":
        return stack.rescue_wf
    if graph == "graph1_multi_supplier":
        return stack.sourcing_wf
    if graph == "warranty_dispute":
        return stack.warranty_wf
    raise ValueError(f"unknown graph: {graph}")


def start(graph: str, run_id: str, state: dict):
    return _wf(graph).execute(run_id, state)


def status(graph: str, run_id: str):
    return _wf(graph).get_status(run_id)


def external_event(graph: str, run_id: str, payload: dict):
    if graph == "fleet_rescue":
        return _wf(graph).resume_from_external(run_id,
                                               provider_response=payload["response"])
    if graph == "graph1_multi_supplier":
        return _wf(graph).resume_from_external(run_id, event=payload["event"])
    if graph == "warranty_dispute":
        return _wf(graph).resume_from_external(
            run_id,
            inspection=payload.get("inspection"),
            decision=payload.get("decision"))
    raise ValueError(f"no external event for {graph}")