"""Admin gate """
import os
import secrets
from fastapi import APIRouter, Header, HTTPException

_tokens: set[str] = set()
router = APIRouter(tags=["auth"])


def _passcode() -> str:
    return os.getenv("ADMIN_PASSCODE", "nour2026")


@router.post("/api/admin/auth")
def login(body: dict):
    if body.get("passcode") != _passcode():
        raise HTTPException(401, "wrong passcode")
    token = secrets.token_urlsafe(24)
    _tokens.add(token)
    return {"token": token}


def require_admin(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "admin token required")
    if authorization.split(" ", 1)[1] not in _tokens:
        raise HTTPException(401, "invalid admin token")