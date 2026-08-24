from state_graph import runs as runs_db
from ..deps import get_stack
from . import graph_service
from .hitl_service import _graph_of


def list_tickets(status: str | None = None):
    # The core TicketService.list_tickets() takes no args — filter here.
    rows = get_stack().tickets.tickets.list_tickets()
    if status:
        rows = [t for t in rows if t.get("status") == status]
    return rows


def resolve(ticket_id: int, resolution: str):
    s = get_stack()
    s.tickets.tickets.resolve(ticket_id=ticket_id, resolution=resolution)
    t = s.tickets.tickets.get(ticket_id)
    return graph_service._wf(_graph_of(t["run_id"])).resume_from_ticket(ticket_id)