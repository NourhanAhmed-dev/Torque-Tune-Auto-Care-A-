"""Read-only lookups over operational data (clients/vehicles).
API-layer input validation only — the graph's `validating` node
remains the authoritative business rule."""
from state_graph import db

def verify(customer_id: int, vehicle_id: int):
    with db.connect() as conn:
        client = conn.execute("SELECT client_id FROM clients WHERE client_id = ?",
                              (customer_id,)).fetchone()
        if not client:
            return False, "unknown_customer", None
        veh = conn.execute("SELECT client_id FROM vehicles WHERE vehicle_id = ?",
                           (vehicle_id,)).fetchone()
        if not veh:
            return False, "unknown_vehicle", None
        if veh["client_id"] != customer_id:
            return False, "vehicle_not_in_fleet", veh["client_id"]
    return True, None, None