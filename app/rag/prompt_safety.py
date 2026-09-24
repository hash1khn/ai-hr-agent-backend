"""Strip prompt-delimiter tokens from untrusted user and document text."""

_UNTRUSTED_TOKENS = (
    "</retrieved_documents>",
    "<retrieved_documents>",
    "</conversation_history>",
    "<conversation_history>",
    "</employee_question>",
    "<employee_question>",
    "</doc>",
)


def sanitize_untrusted_text(text: str) -> str:
    cleaned = text or ""
    for token in _UNTRUSTED_TOKENS:
        cleaned = cleaned.replace(token, "")
    return cleaned.replace("<doc", "&lt;doc")
