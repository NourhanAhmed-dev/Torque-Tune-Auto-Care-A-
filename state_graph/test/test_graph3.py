"""Offline suite for the simple Graph 3 — mocks"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from state_graph.failure_node import FailureNode
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.hitl.hitl_manager import HitlManager
from state_graph.hitl.approval_service import ApprovalService
from state_graph.tickets.ticket_manager import TicketManager
from state_graph.tickets.ticket_service import TicketService
from state_graph.graphs.graph3_fleet_rescue.nodes import (
    FleetRescueNodes, FleetAuthorizationNode)
from state_graph.graphs.graph3_fleet_rescue.workflow import FleetRescueWorkflow

CONTRACTS = {
 1: "---\ndoc_type: contract\nclient_id: 1\n---\n# Delta\nRescues costing up to $500 may be auto-approved.",
 2: "---\ndoc_type: contract\nclient_id: 2\n---\n# Nile\nRescues costing up to $1,200 may be auto-approved.",
 3: "---\ndoc_type: contract\nclient_id: 3\n---\n# Giza\nRescues costing up to $300 may be auto-approved.",
}


class FakeRag:
    def __init__(self, empty=False):
        self.empty = empty
    def search(self, query, filter=None, top_k=3):
        cid = (filter or {}).get("client_id")
        if self.empty or cid not in CONTRACTS:
            return []
        return [{"doc_id": f"CONTRACT-{cid}", "content": CONTRACTS[cid],
                 "metadata": {"client_id": str(cid), "doc_type": "contract"}}]


class MockMCP:
    def __init__(self):
        self.providers = {pid: {"provider_id": pid, "name": f"Provider {pid}",
                                "latitude": 30.0, "longitude": 31.0, "status": "available"}
                          for pid in ("PROV-001", "PROV-002", "PROV-003")}
        self.busy = set()
        self.dispatches = {}          # dispatch_id -> provider_id
        self.dispatch_statuses = {}   # dispatch_id -> status
        self.dispatch_calls = 0
        self.fail_search = False
    def call_tool(self, name, arguments):
        if name == "search_providers":
            if self.fail_search:
                raise RuntimeError("provider registry unavailable")
            return {"providers": [dict(p) for p in self.providers.values()]}
        if name == "get_provider_location":
            pid = arguments["provider_id"]
            if pid not in self.providers:
                raise RuntimeError(f"Unknown provider: {pid}")
            return {**self.providers[pid],
                    "status": "busy" if pid in self.busy else "available"}
        if name == "dispatch_tow_truck":
            pid = arguments["provider_id"]
            if pid in self.busy:
                raise RuntimeError(f"Provider {pid} is not available")
            self.dispatch_calls += 1
            self.busy.add(pid)
            self.dispatches[self.dispatch_calls] = pid
            self.dispatch_statuses[self.dispatch_calls] = "dispatched"
            return {"success": True, "dispatch_id": self.dispatch_calls,
                    "provider_id": pid}
        if name == "update_vehicle_status":
            did = arguments["dispatch_id"]
            st = arguments["status"]
            self.dispatch_statuses[did] = st
            if st in ("completed", "failed"):
                self.busy.discard(self.dispatches.get(did))
            return {"success": True}
        if name == "notify_fleet_manager":
            return {"success": True}
        raise RuntimeError(f"unknown tool {name}")


class MockLLM:
    def complete(self, prompt: str) -> str:
        if "provider-search agent" in prompt:                      # Constrained ReAct
            if "OBSERVATION: " not in prompt:
                return '{"tool": "search_providers", "arguments": {}}'
            avoid = re.findall(r"AVOID: \[([^\]]*)\]", prompt)
            avoid_ids = re.findall(r"PROV-\d+", avoid[0]) if avoid else []
            last_obs = prompt.rsplit("OBSERVATION: ", 1)[1]
            if '"tool": "get_provider_location"' not in prompt:
                for pid in re.findall(r'"provider_id": "(PROV-\d+)"', last_obs):
                    if pid not in avoid_ids:
                        return json.dumps({"tool": "get_provider_location",
                                           "arguments": {"provider_id": pid}})
                return '{"done": true}'
            if '"tool": "dispatch_tow_truck"' not in prompt \
               and '"status": "available"' in last_obs:
                pid = re.search(r'"provider_id": "(PROV-\d+)"', last_obs).group(1)
                return json.dumps({"tool": "dispatch_tow_truck",
                                   "arguments": {"provider_id": pid, "distance_km": 10}})
            return '{"done": true}'
        # assessment: judge the USER REQUEST only, not the guidelines text
        request = prompt.split("Request:", 1)[-1].lower()
        cost = 2000.0 if "engine" in request else 120.0
        return json.dumps({"service_type": "tow", "estimated_cost": cost})

def setup(mcp=None, rag=None):
    mcp = mcp or MockMCP()
    cp = CheckpointManager(graph_type="fleet_rescue")
    tm = TicketManager(checkpoints=cp, tickets=TicketService())
    hm = HitlManager(checkpoints=cp, approvals=ApprovalService())
    nodes = FleetRescueNodes(failure_node=FailureNode(manager=tm),
                             fleet_auth_node=FleetAuthorizationNode(manager=hm),
                             llm_client=MockLLM(), mcp_client=mcp,
                             rag_retriever=rag if rag is not None else FakeRag())
    return (FleetRescueWorkflow(nodes=nodes, checkpoints=cp,
                                hitl_manager=hm, ticket_manager=tm), hm, tm, mcp)


def st(run, customer, vehicle, request="flat tire on the road"):
    return {"run_id": run, "customer_id": customer, "vehicle_id": vehicle,
            "rescue_request": request}


def _clean():
    from state_graph import db
    with db.connect() as conn:
        conn.execute("DELETE FROM state_graph_runs WHERE run_id LIKE 't_%'")


def s1():
    print("\n== S1 under threshold: no HITL -> provider -> accepted -> completed ==")
    wf, hm, tm, mcp = setup()
    r = wf.execute("t_s1", st("t_s1", 1, 1))
    assert r["status"] == "waiting_external" and r["wait_for"] == "provider_response", r
    r = wf.resume_from_external("t_s1", provider_response="accepted")
    assert r["status"] == "completed" and mcp.dispatch_calls == 1, r
    print("   ok: completed with one dispatch")


def s2():
    print("\n== S2 over threshold -> HITL approve -> completed ==")
    wf, hm, tm, mcp = setup()
    r = wf.execute("t_s2", st("t_s2", 2, 3, "engine failure, truck stuck"))
    assert r["status"] == "paused_hitl", r
    print(f"   ok: paused (request {r['request_id']})")
    hm.approvals.decide(request_id=r["request_id"], admin_id="admin",
                        approved=True, comment="go")
    r = wf.resume_from_hitl(r["request_id"])
    assert r["status"] == "waiting_external", r
    r = wf.resume_from_external("t_s2", provider_response="accepted")
    assert r["status"] == "completed", r
    print("   ok: approved via HITL then completed")


def s3():
    print("\n== S3 HITL reject -> cancelled ==")
    wf, hm, tm, mcp = setup()
    r = wf.execute("t_s3", st("t_s3", 2, 3, "engine failure"))
    assert r["status"] == "paused_hitl", r
    hm.approvals.decide(request_id=r["request_id"], admin_id="admin",
                        approved=False, comment="too expensive")
    r = wf.resume_from_hitl(r["request_id"])
    assert r["status"] == "cancelled", r
    print("   ok: rejected -> CANCELLED")


def s4():
    print("\n== S4 provider rejected -> cycle back -> second provider -> completed ==")
    wf, hm, tm, mcp = setup()
    r = wf.execute("t_s4", st("t_s4", 1, 1))
    assert r["status"] == "waiting_external", r
    first_dispatch = 1
    r = wf.resume_from_external("t_s4", provider_response="rejected")
    assert r["status"] == "waiting_external", r          # PROVIDER_SEARCH 
    assert mcp.dispatch_calls == 2, r
    assert mcp.dispatch_statuses[first_dispatch] == "failed"
    r = wf.resume_from_external("t_s4", provider_response="accepted")
    assert r["status"] == "completed", r
    print("   ok: real cycle PROVIDER_SEARCH -> WAIT -> rejected -> PROVIDER_SEARCH")


def s5():
    print("\n== S5 search tool fails -> ticket -> resolve -> resume from checkpoint ==")
    wf, hm, tm, mcp = setup()
    mcp.fail_search = True
    r = wf.execute("t_s5", st("t_s5", 1, 1))
    assert r["status"] == "failed_ticket", r
    print(f"   ok: ticket {r['ticket_id']} opened at PROVIDER_SEARCH")
    mcp.fail_search = False
    tm.tickets.resolve(ticket_id=r["ticket_id"], resolution="registry restored")
    r = wf.resume_from_ticket(r["ticket_id"])
    assert r["status"] == "waiting_external", r
    r = wf.resume_from_external("t_s5", provider_response="accepted")
    assert r["status"] == "completed", r
    print("   ok: resumed from the failure checkpoint, not from REQUESTED")


def s6():
    print("\n== S6 no contract indexed -> safe ticket, no silent default ==")
    wf, hm, tm, mcp = setup(rag=FakeRag(empty=True))
    r = wf.execute("t_s6", st("t_s6", 1, 1))
    assert r["status"] == "failed_ticket", r
    print("   ok: ticketed instead of inventing a threshold")


def s7():
    print("\n== S7 vehicle not in customer fleet -> CANCELLED ==")
    wf, hm, tm, mcp = setup()
    r = wf.execute("t_s7", st("t_s7", 1, 3))
    assert r["status"] == "cancelled", r
    print("   ok: invalid request cancelled")


def s8():
    print("\n== S8 crash-restart: new process resumes from checkpoint ==")
    wf1, hm, tm, mcp = setup()
    r = wf1.execute("t_s8", st("t_s8", 1, 1))
    assert r["status"] == "waiting_external", r
    print("   (process killed)")
    wf2, *_ = setup(mcp=mcp)
    r = wf2.resume_from_external("t_s8", provider_response="accepted")
    assert r["status"] == "completed" and mcp.dispatch_calls == 1, r
    print("   ok: resumed with zero duplicated work")


if __name__ == "__main__":
    _clean()
    for fn in (s1, s2, s3, s4, s5, s6, s7, s8):
        fn()
    print("\nALL SCENARIOS PASSED")