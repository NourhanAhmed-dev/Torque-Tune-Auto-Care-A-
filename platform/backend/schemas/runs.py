from pydantic import BaseModel

class StartRescueReq(BaseModel):
    run_id: str
    customer_id: int
    vehicle_id: int
    request: str

class ProviderResponseReq(BaseModel):
    response: str  # accepted | rejected