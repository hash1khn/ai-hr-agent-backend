from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.core.security import AuthUser, decode_access_token, extract_token
from app.services import auth_service


def get_current_user(request: Request) -> AuthUser:
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    user = auth_service.get_user_by_id(str(payload.get("sub")))
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    if user.company_id != str(payload.get("company_id")):
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
