from fastapi import APIRouter
from pydantic import BaseModel
from ..services import concierge_service

router = APIRouter(prefix="/api/agents", tags=["agents"])

class RescueChatReq(BaseModel):
    message: str
    run_id: str | None = None

@router.post("/rescue_chat")
def rescue_chat(body: RescueChatReq):
    return concierge_service.chat(body.message, body.run_id)

@router.get("/rescue_status")
def rescue_status(run_id: str | None = None):
    return concierge_service.news(run_id)

# graph 1
from ..services import build_concierge

class BuildChatReq(BaseModel):
    message: str
    run_id: str | None = None

@router.post("/build_chat")
def build_chat(body: BuildChatReq):
    return build_concierge.chat(body.message, body.run_id)

@router.get("/build_status")
def build_status(run_id: str | None = None):
    return build_concierge.news(run_id)

# graph 2 — warranty & comebacks
from ..services import warranty_concierge

class WarrantyChatReq(BaseModel):
    message: str
    run_id: str | None = None

@router.post("/warranty_chat")
def warranty_chat(body: WarrantyChatReq):
    return warranty_concierge.chat(body.message, body.run_id)

@router.get("/warranty_status")
def warranty_status(run_id: str | None = None):
    return warranty_concierge.news(run_id)

# general technician chat (Sessions 1-3 agent)
from ..services import agent_service

class TechChatReq(BaseModel):
    message: str
    agent: str = "tuning-technician"

@router.post("/chat")
def tech_chat(body: TechChatReq):
    return agent_service.chat(body.message)