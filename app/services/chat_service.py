from __future__ import annotations

import json
import uuid

from fastapi import HTTPException

from app import db
from app.rag import query_cache
from app.rag.answer import generate_answer
from app.rag.retrieve import retrieve_chunks
from app.schemas import ChatResponse, ConversationDetail, ConversationSummary, MessageOut, Source
from app.core.security import AuthUser


def list_conversations(user: AuthUser) -> list[ConversationSummary]:
    with db.tenant_connection(user.company_id) as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE company_id = %s AND user_id = %s
            ORDER BY updated_at DESC
            LIMIT 100
            """,
            (user.company_id, user.id),
        ).fetchall()
    return [
        ConversationSummary(
            id=str(row["id"]),
            title=row["title"],
            created_at=_iso(row["created_at"]),
            updated_at=_iso(row["updated_at"]),
        )
        for row in rows
    ]


def get_conversation(user: AuthUser, conversation_id: str) -> ConversationDetail:
    with db.tenant_connection(user.company_id) as conn:
        convo = conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = %s AND company_id = %s AND user_id = %s
            """,
            (conversation_id, user.company_id, user.id),
        ).fetchone()
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        rows = conn.execute(
            """
            SELECT id, role, content, sources, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
    return ConversationDetail(
        id=str(convo["id"]),
        title=convo["title"],
        created_at=_iso(convo["created_at"]),
        updated_at=_iso(convo["updated_at"]),
        messages=[_message_out(dict(row)) for row in rows],
    )


def ask(user: AuthUser, message: str, conversation_id: str | None = None) -> ChatResponse:
    conversation_id = _ensure_conversation(user, conversation_id, message)
    history = _recent_history(user, conversation_id)
    cache_key = _cache_key_for(user, message, history)
    cached = query_cache.get(cache_key) if cache_key else None
    if isinstance(cached, ChatResponse):
        _insert_message(user.company_id, conversation_id, "user", message, [])
        _insert_message(user.company_id, conversation_id, "assistant", cached.answer, [s.model_dump() for s in cached.sources])
        _touch_conversation(user.company_id, conversation_id)
        return ChatResponse(
            conversation_id=conversation_id,
            answer=cached.answer,
            sources=cached.sources,
            confidence=cached.confidence,
            grounded=cached.grounded,
        )

    _insert_message(user.company_id, conversation_id, "user", message, [])
    chunks = retrieve_chunks(user.company_id, message, role=user.role, history=history)
    answer, sources, confidence = generate_answer(message, chunks, history)
    _insert_message(user.company_id, conversation_id, "assistant", answer, [s.model_dump() for s in sources])
    _touch_conversation(user.company_id, conversation_id)
    response = ChatResponse(
        conversation_id=conversation_id,
        answer=answer,
        sources=sources,
        confidence=confidence,  # type: ignore[arg-type]
        grounded=confidence == "grounded",
    )
    if cache_key:
        query_cache.set_value(cache_key, response)
    return response


def _touch_conversation(company_id: str, conversation_id: str) -> None:
    with db.tenant_connection(company_id) as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = %s",
            (conversation_id,),
        )
        conn.commit()


def _recent_history(user: AuthUser, conversation_id: str, limit: int = 4) -> str:
    with db.tenant_connection(user.company_id) as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (conversation_id, limit),
        ).fetchall()
    parts: list[str] = []
    for row in reversed(rows):
        role = "Employee" if row["role"] == "user" else "Assistant"
        content = str(row["content"] or "").replace("\n", " ").strip()[:400]
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _cache_key_for(user: AuthUser, message: str, history: str) -> str | None:
    try:
        with db.tenant_connection(user.company_id) as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(updated_at)::text, 'none') AS version
                FROM documents
                WHERE company_id = %s
                """,
                (user.company_id,),
            ).fetchone()
        version = str(row["version"]) if row else "none"
    except Exception:
        return None
    return query_cache.make_key(user.company_id, user.role, message, history, version)


def _ensure_conversation(user: AuthUser, conversation_id: str | None, message: str) -> str:
    if conversation_id:
        with db.tenant_connection(user.company_id) as conn:
            row = conn.execute(
                """
                SELECT id FROM conversations
                WHERE id = %s AND company_id = %s AND user_id = %s
                """,
                (conversation_id, user.company_id, user.id),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation_id

    new_id = str(uuid.uuid4())
    title = message.strip().replace("\n", " ")[:80] or "New conversation"
    with db.tenant_connection(user.company_id) as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, company_id, user_id, title)
            VALUES (%s, %s, %s, %s)
            """,
            (new_id, user.company_id, user.id, title),
        )
        conn.commit()
    return new_id


def _insert_message(
    company_id: str,
    conversation_id: str,
    role: str,
    content: str,
    sources: list[dict],
) -> None:
    with db.tenant_connection(company_id) as conn:
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, sources)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (str(uuid.uuid4()), conversation_id, role, content, json.dumps(sources)),
        )
        conn.commit()


def _message_out(row: dict) -> MessageOut:
    raw_sources = row.get("sources") or []
    if isinstance(raw_sources, str):
        raw_sources = json.loads(raw_sources)
    sources = [Source.model_validate(item) for item in raw_sources]
    return MessageOut(
        id=str(row["id"]),
        role=row["role"],
        content=row["content"],
        sources=sources,
        created_at=_iso(row["created_at"]),
    )


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
