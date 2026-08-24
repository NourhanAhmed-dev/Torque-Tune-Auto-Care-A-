from fastapi import APIRouter
from ..schemas.tickets import ResolveReq
from ..services import ticket_service

router = APIRouter(prefix="/api/admin/tickets", tags=["tickets"])

@router.get("")
def list_tickets(status: str | None = None):
    return ticket_service.list_tickets(status)

@router.post("/{ticket_id}/resolve")
def resolve(ticket_id: int, body: ResolveReq):
    return ticket_service.resolve(ticket_id, body.resolution)