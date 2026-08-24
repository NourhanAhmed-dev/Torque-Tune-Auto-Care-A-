from pydantic import BaseModel

class ToolSetReq(BaseModel):
    enabled: bool