from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.core.rate_limit import enforce_chat_rate_limit
from app.schemas import ChatBody, ChatResponse, ConversationDetail, ConversationSummary
from app.core.security import AuthUser
from app.services import chat_service

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatBody,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    enforce_chat_rate_limit(request)
    return chat_service.ask(user, body.message.strip(), body.conversation_id)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(user: AuthUser = Depends(get_current_user)):
    return chat_service.list_conversations(user)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user: AuthUser = Depends(get_current_user)):
    return chat_service.get_conversation(user, conversation_id)
