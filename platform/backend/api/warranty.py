import time
from fastapi import APIRouter
from pydantic import BaseModel
from ..services import graph_service

router = APIRouter(prefix="/api/admin/warranty", tags=["warranty"])


class StartWarrantyReq(BaseModel):
    run_id: str | None = None
    vehicle_id: int
    client_id: int | None = None
    description: str = ""


class InspectionReq(BaseModel):
    status: str      # tuning_fault | unrelated | inconclusive
    notes: str = ""


class DecisionReq(BaseModel):
    decision: str    # accept | reject | escalate


@router.post("/runs")
def start(body: StartWarrantyReq):
    run_id = body.run_id or f"war_{int(time.time() % 1_000_000)}"
    return graph_service.start("warranty_dispute", run_id, {
        "run_id": run_id, "vehicle_id": body.vehicle_id,
        "client_id": body.client_id,
        "complaint": {"description": body.description}})


@router.post("/runs/{run_id}/inspection")
def inspection(run_id: str, body: InspectionReq):
    return graph_service.external_event(
        "warranty_dispute", run_id,
        {"inspection": {"status": body.status, "notes": body.notes}})


@router.post("/runs/{run_id}/decision")
def decision(run_id: str, body: DecisionReq):
    return graph_service.external_event(
        "warranty_dispute", run_id, {"decision": body.decision})