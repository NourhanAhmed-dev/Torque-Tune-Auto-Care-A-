import time
from fastapi import APIRouter
from pydantic import BaseModel
from ..services import graph_service

router = APIRouter(prefix="/api/admin/sourcing", tags=["sourcing"])

class StartSourcingReq(BaseModel):
    run_id: str | None = None
    preset: str = "stage2_turbo_stock_power"


class SupplierEventReq(BaseModel):
    event: dict


@router.post("/runs")
def start(body: StartSourcingReq):
    run_id = body.run_id or f"src_{int(time.time() % 1_000_000)}"
    return graph_service.start("graph1_multi_supplier", run_id,
                               {"run_id": run_id, "preset": body.preset})


@router.post("/runs/{run_id}/event")
def event(run_id: str, body: SupplierEventReq):
    return graph_service.external_event("graph1_multi_supplier", run_id,
                                        {"event": body.event})

@router.post("/runs/{run_id}/auto_event")
def auto_event(run_id: str):
    from ..deps import get_stack
    st = get_stack().sourcing_wf.get_status(run_id)["state"] or {}
    orders = st.get("orders") or {}

    def send(event):
        return graph_service.external_event(
            "graph1_multi_supplier", run_id, {"event": event})

    # 1) first order
    for oid in sorted(orders, key=lambda k: int(k)):
        o = orders[oid]
        if o.get("status") == "ordered" and o.get("final_price") is None:
            return send({"event_type": "price_changed",
                         "order_id": oid,
                         "final_price": round(o["quoted_price"] * 1.15, 2)})

    # 2) arrives 
    delivered = set(st.get("delivered_part_ids") or [])
    cancelled = set(st.get("cancelled_part_ids") or [])
    for p in (st.get("parts_required") or []):
        pid = p["part_id"]
        if pid not in delivered and pid not in cancelled:
            return send({"event_type": "delivery_confirmed", "part_id": pid})

    return {"note": "nothing left to do — run should be completed"}
class SupplierDecisionReq(BaseModel):
    kind: str          # accept | raise_price | reject | unavailable
    percent: float = 15.0

class PartDecisionReq(BaseModel):
    part_id: int
    kind: str          # deliver | cancel | substitute

def _state(run_id: str) -> dict:
    from ..deps import get_stack
    return get_stack().sourcing_wf.get_status(run_id)["state"] or {}

def _unresolved(st: dict) -> list:
    delivered = set(st.get("delivered_part_ids") or [])
    cancelled = set(st.get("cancelled_part_ids") or [])
    return [p["part_id"] for p in (st.get("parts_required") or [])
            if p["part_id"] not in delivered and p["part_id"] not in cancelled]

def _send(run_id: str, event: dict):
    return graph_service.external_event("graph1_multi_supplier", run_id,
                                        {"event": event})

def _deliver_all(run_id: str):
    last = None
    for _ in range(10):
        left = _unresolved(_state(run_id))
        if not left:
            break
        last = _send(run_id, {"event_type": "delivery_confirmed",
                              "part_id": left[0]})
    return last

@router.get("/runs/{run_id}/parts")
def parts(run_id: str):
    st = _state(run_id)
    delivered = set(st.get("delivered_part_ids") or [])
    cancelled = set(st.get("cancelled_part_ids") or [])
    return {"run_id": run_id, "parts": [
        {"part_id": p["part_id"], "part_name": p.get("part_name"),
         "fate": ("delivered" if p["part_id"] in delivered
                  else "cancelled" if p["part_id"] in cancelled
                  else "pending")}
        for p in (st.get("parts_required") or [])]}

@router.post("/runs/{run_id}/supplier_decision")
def supplier_decision(run_id: str, body: SupplierDecisionReq):
    st = _state(run_id)
    orders = st.get("orders") or {}
    if body.kind == "accept":
        return _deliver_all(run_id) or {"status": "completed"}
    if body.kind == "raise_price":
        for oid, o in orders.items():
            if o.get("status") == "ordered" and o.get("final_price") is None:
                return _send(run_id, {"event_type": "price_changed",
                                      "order_id": oid, "final_price": round(
                                          o["quoted_price"] * (1 + body.percent / 100), 2)})
        return {"sent": None, "note": "no open order to reprice"}
    if body.kind == "reject":
        last = None
        for pid in _unresolved(st):
            last = _send(run_id, {"event_type": "cancelled", "part_id": pid})
        return last or {"status": "completed"}
    if body.kind == "unavailable":
        left = _unresolved(st)
        if not left:
            return {"sent": None, "note": "nothing left"}
        return _send(run_id, {"event_type": "substitute_offered",
                              "part_id": left[0], "substitute_part": None,
                              "warranty_impact": "non-OEM substitute"})
    return {"error": "unknown kind"}

@router.post("/runs/{run_id}/part_decision")
def part_decision(run_id: str, body: PartDecisionReq):
    ev = {"deliver": {"event_type": "delivery_confirmed", "part_id": body.part_id},
          "cancel": {"event_type": "cancelled", "part_id": body.part_id},
          "substitute": {"event_type": "substitute_offered", "part_id": body.part_id,
                         "substitute_part": None,
                         "warranty_impact": "non-OEM substitute"}}.get(body.kind)
    if ev is None:
        return {"error": "unknown kind"}
    return _send(run_id, ev)