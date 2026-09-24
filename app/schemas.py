from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


Role = Literal["ADMIN", "EMPLOYEE"]
DocumentStatus = Literal["UPLOADED", "PROCESSING", "READY", "FAILED"]
DocumentVisibility = Literal["ALL_EMPLOYEES", "ADMIN_ONLY"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _parse_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        raise ValueError("Enter a valid email address")
    return email


EmailAddress = Annotated[str, AfterValidator(_parse_email)]


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


class Source(BaseModel):
    document: str
    page: int | None = None
    document_id: str | None = None
    score: float | None = None


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4_000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[Source]
    confidence: Literal["grounded", "partial", "none"] = "none"
    grounded: bool = False


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = []
    created_at: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageOut]


class DocumentOut(BaseModel):
    id: str
    filename: str
    original_name: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    visibility: DocumentVisibility = "ALL_EMPLOYEES"
    error_message: str | None = None
    chunk_count: int
    created_at: str
    updated_at: str
