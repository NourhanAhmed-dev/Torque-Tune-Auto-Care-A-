from fastapi import APIRouter
from ..schemas.tools import ToolSetReq
from ..services import tool_registry_service

router = APIRouter(prefix="/api/admin/tools", tags=["tools"])

@router.get("")
def list_tools():
    return tool_registry_service.list_tools()

@router.post("/{tool_name}/set")
def set_tool(tool_name: str, body: ToolSetReq):
    return tool_registry_service.set_tool(tool_name, body.enabled)