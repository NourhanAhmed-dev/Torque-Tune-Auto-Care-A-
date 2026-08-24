from fastapi import APIRouter, HTTPException, Query
from ..schemas.resources import DocAddReq
from ..services import resource_service

router = APIRouter(prefix="/api/admin/resources", tags=["resources"])

@router.get("/documents")
def list_documents():
    return resource_service.list_documents()

@router.post("/documents")
def add_document(body: DocAddReq):
    try:
        return resource_service.add_document(body.filename, body.content)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.delete("/documents")
def remove_document(filename: str = Query(...)):
    try:
        return resource_service.remove_document(filename)
    except FileNotFoundError:
        raise HTTPException(404, "not found")