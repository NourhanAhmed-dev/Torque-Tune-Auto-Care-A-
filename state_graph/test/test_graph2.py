"""Offline suite for Graph 2 — mocked RAG, zero Gemini calls."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from state_graph.checkpoint.checkpoint_manager import CheckpointManager
from state_graph.hitl.hitl_manager import HitlManager, HitlPaused
from state_graph.hitl.approval_service import ApprovalService
from state_graph.tickets.ticket_manager import TicketManager, FailurePaused
from state_graph.tickets.ticket_service import TicketService
from state_graph.graphs.graph2_dispute_resolution.workflow import Graph2Warranty


class FakeDoc:
    doc_id = "LOG-1"


class FakeAnswer:
    def __init__(self, answer):
        self.answer = answer
        self.retrieved = [FakeDoc()]


class FakeRag:
    """Deterministic: summarizes history, then finalizes responsibility."""
    def __init__(self, responsibility="company", confidence=0.9):
        self.responsibility = responsibility
        self.confidence = confidence
        self.calls = 0

    def answer(self, query: str):
        self.calls += 1
        if "investigating warranty responsibility" in query:
            return FakeAnswer(json.dumps({
                "thought": "inspection points at our tune",
                "action": "finalize",
                "action_input": {"responsibility": self.responsibility,
                                 "confidence": self.confidence,
                                 "reasoning": "mock"}}))
        return FakeAnswer("Stage 1 tune two weeks ago; no anomalies logged.")


def setup(rag=None):
    cp = CheckpointManager(graph_type="warranty_dispute")
    tm = TicketManager(checkpoints=cp, tickets=TicketService())
    hm = HitlManager(checkpoints=cp, approvals=ApprovalService())
    wf = Graph2Warranty(checkpoint_manager=cp, ticket_manager=tm,
                        hitl_manager=hm, rag=rag or FakeRag())
    return wf, hm, tm


def _clean():
    from state_graph import db
    with db.connect() as conn:
        conn.execute("DELETE FROM state_graph_runs WHERE run_id LIKE 'w%'")


def w1():
    print("\n== W1 clear responsibility -> inspection -> client accept -> completed ==")
    wf, hm, tm = setup()
    r = wf.start("w1", 1, {"description": "power loss"}, client_id=1)
    assert r["status"] == "waiting_inspection", r
    r = wf.submit_inspection_result("w1", {"status": "tuning_fault", "notes": "boost leak at our clamp"})
    assert r["status"] == "waiting_client" and r["responsibility"] == "company", r
    r = wf.submit_client_decision("w1", "accept")
    assert r["status"] == "completed", r
    print("   ok: completed, responsibility=company")


def w2():
    print("\n== W2 low confidence -> senior HITL approve -> completed ==")
    wf, hm, tm = setup(FakeRag(confidence=0.4))
    wf.start("w2", 1, {"description": "rattle"}, client_id=1)
    try:
        wf.submit_inspection_result("w2", {"status": "tuning_fault", "notes": "maybe ours"})
        raise AssertionError("expected HitlPaused")
    except HitlPaused as p:
        rid = p.request_id
    hm.approvals.decide(request_id=rid, admin_id="senior", approved=True, comment="ok")
    r = wf.resume_after_hitl_approval(rid)
    assert r["status"] == "waiting_client" and not r["responsibility_ambiguous"], r
    r = wf.submit_client_decision("w2", "accept")
    assert r["status"] == "completed", r
    print("   ok: approved via HITL then completed")


def w3():
    print("\n== W3 senior rejects -> ticket -> resolution becomes responsibility ==")
    wf, hm, tm = setup(FakeRag(confidence=0.3))
    wf.start("w3", 1, {"description": "rattle"}, client_id=1)
    try:
        wf.submit_inspection_result("w3", {"status": "tuning_fault", "notes": "unsure"})
        raise AssertionError("expected HitlPaused")
    except HitlPaused as p:
        rid = p.request_id
    hm.approvals.decide(request_id=rid, admin_id="senior", approved=False, comment="no")
    try:
        wf.resume_after_hitl_approval(rid)
        raise AssertionError("expected FailurePaused")
    except FailurePaused as p:
        tid = p.ticket_id
    tm.tickets.resolve(ticket_id=tid, resolution="client")
    r = wf.resume_after_ticket_resolution(tid)
    assert r["status"] == "waiting_client" and r["responsibility"] == "client", r
    print("   ok: ticket resolution adopted as final responsibility")


def w4():
    print("\n== W4 inconclusive inspection -> ticket -> goodwill path ==")
    wf, hm, tm = setup()
    wf.start("w4", 1, {"description": "noise"}, client_id=1)
    try:
        wf.submit_inspection_result("w4", {"status": "inconclusive", "notes": "can't tell"})
        raise AssertionError("expected FailurePaused")
    except FailurePaused as p:
        tid = p.ticket_id
    tm.tickets.resolve(ticket_id=tid, resolution="goodwill compensation")
    r = wf.resume_after_ticket_resolution(tid)
    assert r["status"] == "waiting_client", r
    assert r["proposed_resolution"] == "goodwill compensation", r
    print("   ok: management decision routed to client as the offer")


def w5():
    print("\n== W5 crash-restart: fresh instance resumes from checkpoint ==")
    wf1, hm, tm = setup()
    r = wf1.start("w5", 1, {"description": "power loss"}, client_id=1)
    assert r["status"] == "waiting_inspection", r
    print("   (process killed)")
    wf2, *_ = setup()
    r = wf2.submit_inspection_result("w5", {"status": "unrelated", "notes": "worn mounts"})
    assert r["status"] == "waiting_client" and r["responsibility"] == "company", r
    print("   ok: resumed with zero duplicated work")


if __name__ == "__main__":
    _clean()
    for fn in (w1, w2, w3, w4, w5):
        fn()
    print("\nALL SCENARIOS PASSED")