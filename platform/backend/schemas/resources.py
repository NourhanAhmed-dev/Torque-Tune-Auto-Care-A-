from pydantic import BaseModel

class DocAddReq(BaseModel):
    filename: str    
    content: str