from pydantic import BaseModel
class DecideReq(BaseModel):
    approved: bool
    comment: str = ""