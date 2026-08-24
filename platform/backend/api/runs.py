from fastapi import APIRouter
from ..services import run_service, timeline_service

router = APIRouter(prefix="/api/admin/runs", tags=["runs"])

@router.get("")
def list_runs(limit: int = 50):
    return run_service.list_runs(limit)


@router.get("/{run_id}/timeline")
def run_timeline(run_id: str):
    return timeline_service.timeline(run_id)