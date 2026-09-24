from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import EmailAddress, Role


class RegisterBody(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=120)
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailAddress
    password: str = Field(..., min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailAddress
    password: str = Field(..., min_length=1, max_length=128)


class CreateEmployeeBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailAddress
    password: str = Field(..., min_length=8, max_length=128)


class CompanyOut(BaseModel):
    id: str
    name: str
    slug: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: Role
    company: CompanyOut


class EmployeeOut(BaseModel):
    id: str
    email: str
    name: str
    role: Role
    created_at: str
