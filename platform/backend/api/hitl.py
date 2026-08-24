from fastapi import APIRouter
from ..schemas.hitl import DecideReq
from ..services import hitl_service

router = APIRouter(prefix="/api/admin/hitl", tags=["hitl"])

@router.get("")
def list_hitl(status: str = "pending"):
    return hitl_service.list_requests(status)

@router.get("/{request_id}")
def detail(request_id: int):
    return hitl_service.get(request_id)

@router.post("/{request_id}/decide")
def decide(request_id: int, body: DecideReq):
    return hitl_service.decide(request_id, body.approved, body.comment)