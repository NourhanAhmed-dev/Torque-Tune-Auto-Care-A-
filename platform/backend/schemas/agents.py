from pydantic import BaseModel

class ChatReq(BaseModel):
    message: str
    agent: str = "tuning-technician"   