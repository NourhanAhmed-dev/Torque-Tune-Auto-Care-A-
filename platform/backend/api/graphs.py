from fastapi import APIRouter, HTTPException
from ..schemas.runs import StartRescueReq, ProviderResponseReq
from ..services import graph_service

router = APIRouter(prefix="/api/graphs", tags=["graphs"])

@router.post("/{graph}/runs")
def start(graph: str, body: StartRescueReq):
    return graph_service.start(graph, body.run_id, {
        "run_id": body.run_id, "customer_id": body.customer_id,
        "vehicle_id": body.vehicle_id, "rescue_request": body.request})


@router.post("/{graph}/runs/{run_id}/event")
def event(graph: str, run_id: str, body: ProviderResponseReq):
    try:
        return graph_service.external_event(graph, run_id, {"response": body.response})
    except ValueError as e:
        raise HTTPException(409, str(e))