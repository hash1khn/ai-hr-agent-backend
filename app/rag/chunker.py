from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    page_number: int | None = None
    token_estimate: int = 0


def clean_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\x00", "")
    lines = [line.rstrip() for line in normalized.split("\n")]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            collapsed.append(" ".join(line.split()))
            blank = False
        elif not blank and collapsed:
            collapsed.append("")
            blank = True
    return "\n".join(collapsed).strip()


def chunk_text(text: str, page_number: int | None = None, start_index: int = 0) -> list[TextChunk]:
    settings = get_settings()
    size = settings.chunk_size if settings.chunk_size > 0 else 1000
    overlap = settings.chunk_overlap if settings.chunk_overlap > 0 else 150
    normalized = clean_text(text)

    if not normalized:
        return []

    if len(normalized) <= size:
        return [
            TextChunk(
                index=start_index,
                content=normalized,
                page_number=page_number,
                token_estimate=_estimate_tokens(normalized),
            )
        ]

    chunks: list[TextChunk] = []
    start = 0
    index = start_index

    while start < len(normalized):
        end = min(start + size, len(normalized))

        if end < len(normalized):
            window = normalized[start:end]
            para = window.rfind("\n\n")
            sentence = window.rfind(". ")
            break_at = -1
            if para >= size * 0.4:
                break_at = para
            elif sentence >= size * 0.4:
                break_at = sentence + 1
            if break_at > 0:
                end = start + break_at + 1

        content = normalized[start:end].strip()
        if content:
            chunks.append(
                TextChunk(
                    index=index,
                    content=content,
                    page_number=page_number,
                    token_estimate=_estimate_tokens(content),
                )
            )
            index += 1

        if end >= len(normalized):
            break

        start = max(end - overlap, start + 1)

    return chunks


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page_number, text in pages:
        pieces = chunk_text(text, page_number=page_number, start_index=len(chunks))
        chunks.extend(pieces)
    return chunks


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
