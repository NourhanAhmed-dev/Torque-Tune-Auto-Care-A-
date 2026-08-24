from ..deps import get_stack
from . import graph_service


def _graph_of(run_id: str) -> str:
    """اسم الجراف من صف الـ run — متسامح مع اسم العمود."""
    from state_graph import runs as runs_db
    run = runs_db.get_run(run_id)
    if not run:
        return "fleet_rescue"
    for key in ("graph_name", "graph_type"):
        try:
            val = run[key]
            if val:
                return val
        except (IndexError, KeyError):
            continue
    return "fleet_rescue"


def list_requests(status: str | None = "pending"):
    return get_stack().hitl.approvals.list_requests(status=status)


def get(request_id: int):
    s = get_stack()
    req = s.hitl.approvals.get_request(request_id)
    resume = s.hitl.resume_data(request_id) if req["status"] == "pending" else None
    return {"request": req, "resume_state": resume}


def decide(request_id: int, approved: bool, comment: str):
    s = get_stack()
    s.hitl.approvals.decide(request_id=request_id, admin_id="admin@platform",
                            approved=approved, comment=comment)
    req = s.hitl.approvals.get_request(request_id)
    return graph_service._wf(_graph_of(req["run_id"])).resume_from_hitl(request_id)