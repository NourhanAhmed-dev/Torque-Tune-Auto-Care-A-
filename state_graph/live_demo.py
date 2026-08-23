"""Live demo CLI for Graph 3 — real MCP server + real Gemini + real Chroma.

Usage:
    python -m state_graph.live_demo start <customer_id> <vehicle_id> "<breakdown>"
    python -m state_graph.live_demo respond <accepted|rejected>
    python -m state_graph.live_demo hitl
    python -m state_graph.live_demo approve <request_id>
    python -m state_graph.live_demo reject <request_id>
    python -m state_graph.live_demo ticket_resolve <ticket_id> "<resolution>"
    python -m state_graph.live_demo status
"""
import json
import sys

from state_graph import db
from state_graph.live_bridge import build_live_stack
from state_graph.failure_node import FailureNode
from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.hitl.hitl_manager import HitlManager
from state_graph.hitl.approval_service import ApprovalService
from state_graph.tickets.ticket_manager import TicketManager
from state_graph.tickets.ticket_service import TicketService
from state_graph.graphs.graph3_fleet_rescue.nodes import (
    FleetRescueNodes, FleetAuthorizationNode)
from state_graph.graphs.graph3_fleet_rescue.workflow import FleetRescueWorkflow

RUN = "live_demo_1"


def build():
    mcp, llm, rag = build_live_stack()
    cp = CheckpointManager(graph_type="fleet_rescue")
    tm = TicketManager(checkpoints=cp, tickets=TicketService())
    hm = HitlManager(checkpoints=cp, approvals=ApprovalService())
    nodes = FleetRescueNodes(
        failure_node=FailureNode(manager=tm),
        fleet_auth_node=FleetAuthorizationNode(manager=hm),
        llm_client=llm, mcp_client=mcp, rag_retriever=rag)
    return (FleetRescueWorkflow(nodes=nodes, checkpoints=cp,
                                hitl_manager=hm, ticket_manager=tm), hm, tm, mcp)


def show(r):
    extra = {k: r.get(k) for k in ("wait_for", "request_id", "ticket_id")
             if r.get(k) is not None}
    print("STATUS:", r["status"], extra if extra else "")


def main():
    cmd = sys.argv[1]
    wf, hm, tm, mcp = build()
    try:
        if cmd == "start":
            # delete any old start
            # clean checkpoints/hitl/tickets
            with db.connect() as conn:
                conn.execute(
                    "DELETE FROM state_graph_runs WHERE run_id LIKE 'live_%'")
            show(wf.execute(RUN, {"run_id": RUN,
                                  "customer_id": int(sys.argv[2]),
                                  "vehicle_id": int(sys.argv[3]),
                                  "rescue_request": sys.argv[4]}))
        elif cmd == "respond":
            show(wf.resume_from_external(RUN, provider_response=sys.argv[2]))
        elif cmd == "hitl":
            reqs = hm.approvals.list_requests(run_id=RUN, status="pending")
            for q in reqs:
                print(f"#{q['request_id']} | {q['reason']}")
            if not reqs:
                print("no pending HITL")
        elif cmd in ("approve", "reject"):
            rid = int(sys.argv[2])
            hm.approvals.decide(request_id=rid, admin_id="admin@platform",
                                approved=(cmd == "approve"), comment=cmd)
            show(wf.resume_from_hitl(rid))
        elif cmd == "ticket_resolve":
            tid = int(sys.argv[2])
            tm.tickets.resolve(ticket_id=tid, resolution=sys.argv[3])
            show(wf.resume_from_ticket(tid))
        elif cmd == "status":
            print(json.dumps(wf.get_status(RUN), default=str, indent=2))
    finally:
        mcp.close()


if __name__ == "__main__":
    main()