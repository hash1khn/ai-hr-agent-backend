from fastapi import APIRouter, Depends, Request, Response

from app.deps import get_current_user, require_admin
from app.rate_limit import enforce_auth_rate_limit
from app.schemas import CreateEmployeeBody, EmployeeOut, LoginBody, RegisterBody, UserOut
from app.security import AuthUser, clear_session_cookie, create_access_token, set_session_cookie
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserOut)
def register(body: RegisterBody, request: Request, response: Response):
    enforce_auth_rate_limit(request)
    user = auth_service.register_company_admin(
        body.company_name,
        body.name,
        body.email,
        body.password,
    )
    set_session_cookie(response, create_access_token(user))
    return auth_service.to_user_out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginBody, request: Request, response: Response):
    enforce_auth_rate_limit(request)
    user = auth_service.authenticate(body.email, body.password)
    set_session_cookie(response, create_access_token(user))
    return auth_service.to_user_out(user)


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: AuthUser = Depends(get_current_user)):
    return auth_service.to_user_out(user)


@users_router.get("", response_model=list[EmployeeOut])
def list_users(user: AuthUser = Depends(require_admin)):
    return auth_service.list_employees(user.company_id)


@users_router.post("", response_model=EmployeeOut)
def create_user(body: CreateEmployeeBody, user: AuthUser = Depends(require_admin)):
    return auth_service.create_employee(user.company_id, body.name, body.email, body.password)
