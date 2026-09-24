from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
