"""Request and response models, grouped by feature."""

from app.schemas.auth import (
    CompanyOut,
    CreateEmployeeBody,
    EmployeeOut,
    LoginBody,
    RegisterBody,
    UserOut,
)
from app.schemas.chat import (
    ChatBody,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    MessageOut,
    Source,
)
from app.schemas.common import EmailAddress, Role
from app.schemas.documents import DocumentOut, DocumentStatus, DocumentVisibility

__all__ = [
    "ChatBody",
    "ChatResponse",
    "CompanyOut",
    "ConversationDetail",
    "ConversationSummary",
    "CreateEmployeeBody",
    "DocumentOut",
    "DocumentStatus",
    "DocumentVisibility",
    "EmailAddress",
    "EmployeeOut",
    "LoginBody",
    "MessageOut",
    "RegisterBody",
    "Role",
    "Source",
    "UserOut",
]
