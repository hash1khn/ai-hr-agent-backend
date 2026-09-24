from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DocumentStatus = Literal["UPLOADED", "PROCESSING", "READY", "FAILED"]
DocumentVisibility = Literal["ALL_EMPLOYEES", "ADMIN_ONLY"]


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
