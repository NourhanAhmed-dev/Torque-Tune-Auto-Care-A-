from __future__ import annotations
 
from typing import Any, TypedDict
 
 
class PartRequirement(TypedDict):
    part_id: int
    part_name: str
    quantity: int
    price: float
    preferred_suppliers: list[str]
 
class OrderState(TypedDict, total=False):
    order_id: int
    supplier: str
    status: str  # pending - ordered - backorder - shipped - delivered - cancelled - failed
    quoted_price: float
    final_price: float | None
    part_ids: list[int]
 
 
class InstallationStep(TypedDict, total=False):
    part_id: int
    step_order: int
    description: str
    status: str  # pending - blocked_awaiting_part - in_progress - completed - failed
    dependencies: list[int]
    compatibility_notes: str
    torque_spec: str
 
 
class SourcingState(TypedDict, total=False):
    run_id: str
    vehicle_id: int
    client_id: int
    parts_required: list[PartRequirement]
    orders: dict[int, OrderState]
    delivered_part_ids: list[int]
    cancelled_part_ids: list[int]
    applied_substitutes: dict[int, str]
    installation_sequence: list[InstallationStep]
    last_event: dict[str, Any] | None
 