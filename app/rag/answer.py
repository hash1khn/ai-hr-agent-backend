from __future__ import annotations

from app.rag import llm
from app.schemas import Source


def _sanitize_excerpt(text: str) -> str:
    return (
        (text or "")
        .replace("</retrieved_documents>", "")
        .replace("<retrieved_documents>", "")
        .replace("</doc>", "")
        .replace("<doc", "&lt;doc")
    )


def _trim_overlap(previous: str, current: str) -> str:
    if not previous or not current:
        return current
    max_overlap = min(len(previous), len(current), 200)
    for size in range(max_overlap, 19, -1):
        if current.startswith(previous[-size:]):
            return current[size:].lstrip()
    return current


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    parts: list[str] = []
    previous_content = ""
    for i, chunk in enumerate(chunks, start=1):
        page = f", page {chunk['page']}" if chunk.get("page") else ""
        source = str(chunk.get("document") or "unknown").replace('"', "'")
        raw = str(chunk.get("content") or "")
        content = _sanitize_excerpt(raw)
        same_document = i > 1 and chunk.get("document") == chunks[i - 2].get("document")
        if same_document:
            content = _trim_overlap(_sanitize_excerpt(previous_content), content)
        previous_content = raw
        if not content:
            continue
        parts.append(f'<doc index="{i}" source="{source}{page}">\n{content}\n</doc>')
    return "\n\n".join(parts)


def confidence_from(chunks: list[dict], used_excerpts: list[int]) -> str:
    if not chunks:
        return "none"
    if used_excerpts:
        return "grounded"
    return "partial"


def generate_answer(
    question: str,
    chunks: list[dict],
    history: str = "",
) -> tuple[str, list[Source], str]:
    context = build_context(chunks)
    answer, used = llm.complete_grounded(question, context, history)
    confidence = confidence_from(chunks, used)
    if not chunks:
        return answer, [], confidence
    return answer, sources_from_chunks(chunks, used), confidence


def sources_from_chunks(chunks: list[dict], used_excerpts: list[int] | None = None) -> list[Source]:
    selected = chunks
    if used_excerpts:
        selected = [
            chunk
            for index, chunk in enumerate(chunks, start=1)
            if index in used_excerpts
        ] or chunks
    seen: set[tuple[str, int | None]] = set()
    sources: list[Source] = []
    for chunk in selected:
        key = (chunk["document"], chunk.get("page"))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            Source(
                document=chunk["document"],
                page=chunk.get("page"),
                document_id=chunk.get("document_id"),
                score=chunk.get("score"),
            )
        )
    return sources
