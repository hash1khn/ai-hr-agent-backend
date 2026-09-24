from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app import db
from app.config import get_settings
from app.rag.chunker import chunk_pages
from app.rag.extract import extract_pages, mime_for_filename, validate_upload_bytes
from app.rag.llm import embed
from app.rag.retrieve import to_vector_literal
from app.schemas import DocumentOut, DocumentVisibility

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _row_to_document(row: dict) -> DocumentOut:
    return DocumentOut(
        id=str(row["id"]),
        filename=row["filename"],
        original_name=row["original_name"],
        mime_type=row["mime_type"],
        size_bytes=int(row["size_bytes"]),
        status=row["status"],
        visibility=row.get("visibility") or "ALL_EMPLOYEES",
        error_message=row.get("error_message"),
        chunk_count=int(row["chunk_count"] or 0),
        created_at=row["created_at"].isoformat() if row.get("created_at") else "",
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") else "",
    )


def list_documents(company_id: str) -> list[DocumentOut]:
    with db.tenant_connection(company_id) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE company_id = %s
            ORDER BY created_at DESC
            """,
            (company_id,),
        ).fetchall()
    return [_row_to_document(dict(row)) for row in rows]


def get_document(company_id: str, document_id: str) -> DocumentOut:
    with db.tenant_connection(company_id) as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = %s AND company_id = %s",
            (document_id, company_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return _row_to_document(dict(row))


def delete_document(company_id: str, document_id: str) -> None:
    with db.tenant_connection(company_id) as conn:
        row = conn.execute(
            "SELECT filename FROM documents WHERE id = %s AND company_id = %s",
            (document_id, company_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        conn.execute(
            "DELETE FROM documents WHERE id = %s AND company_id = %s",
            (document_id, company_id),
        )
        conn.commit()
    path = UPLOAD_DIR / str(row["filename"])
    if path.is_file():
        path.unlink()


def _enforce_upload_quota(company_id: str, incoming_bytes: int) -> None:
    settings = get_settings()
    with db.tenant_connection(company_id) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS upload_count, COALESCE(SUM(size_bytes), 0) AS upload_bytes
            FROM documents
            WHERE company_id = %s
              AND created_at >= now() - interval '1 day'
            """,
            (company_id,),
        ).fetchone()
    count = int(row["upload_count"] or 0) if row else 0
    used_bytes = int(row["upload_bytes"] or 0) if row else 0
    if count >= settings.max_uploads_per_day:
        raise HTTPException(status_code=429, detail="Daily document upload limit reached")
    if used_bytes + incoming_bytes > settings.max_upload_bytes_per_day:
        raise HTTPException(status_code=429, detail="Daily document upload size limit reached")


async def create_upload(
    company_id: str,
    file: UploadFile,
    visibility: DocumentVisibility = "ALL_EMPLOYEES",
) -> DocumentOut:
    settings = get_settings()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")
    if visibility not in {"ALL_EMPLOYEES", "ADMIN_ONLY"}:
        raise HTTPException(status_code=400, detail="Invalid document visibility")

    original = file.filename or "document.pdf"
    mime = mime_for_filename(original)
    validate_upload_bytes(original, data)
    _enforce_upload_quota(company_id, len(data))
    document_id = str(uuid.uuid4())
    stored_name = f"{document_id}{Path(original).suffix.lower()}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / stored_name).write_bytes(data)

    with db.tenant_connection(company_id) as conn:
        conn.execute(
            """
            INSERT INTO documents (
              id, company_id, filename, original_name, mime_type, size_bytes, status, visibility
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'UPLOADED', %s)
            """,
            (document_id, company_id, stored_name, original, mime, len(data), visibility),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM documents WHERE id = %s", (document_id,)).fetchone()

    logger.info("Queued document %s for company %s", original, company_id)
    return _row_to_document(dict(row))


def process_document(document_id: str, company_id: str | None = None) -> None:
    try:
        _process_document(document_id, company_id)
    except Exception as exc:
        logger.exception("Document processing failed for %s", document_id)
        _mark_failed(document_id, str(exc)[:500], company_id)


def ingest_text(
    company_id: str,
    original_name: str,
    text: str,
    mime_type: str = "text/markdown",
) -> DocumentOut:
    document_id = str(uuid.uuid4())
    stored_name = f"{document_id}.md"
    with db.tenant_connection(company_id) as conn:
        conn.execute(
            """
            INSERT INTO documents (
              id, company_id, filename, original_name, mime_type, size_bytes, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'PROCESSING')
            """,
            (document_id, company_id, stored_name, original_name, mime_type, len(text.encode("utf-8"))),
        )
        conn.commit()
    _store_chunks(document_id, company_id, original_name, [(None, text)])
    return get_document(company_id, document_id)


def _process_document(document_id: str, company_id: str | None = None) -> None:
    scoped = (
        db.tenant_connection(company_id)
        if company_id
        else db.bypass_rls_connection()
    )
    with scoped as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = %s", (document_id,)).fetchone()
        if not row:
            logger.warning("Document %s disappeared before processing", document_id)
            return
        conn.execute(
            "UPDATE documents SET status = 'PROCESSING', updated_at = now() WHERE id = %s",
            (document_id,),
        )
        conn.commit()

    path = UPLOAD_DIR / row["filename"]
    if not path.is_file():
        raise RuntimeError("Uploaded file is missing from disk")

    pages = extract_pages(row["original_name"], path.read_bytes())
    _store_chunks(document_id, str(row["company_id"]), row["original_name"], pages)


def _store_chunks(
    document_id: str,
    company_id: str,
    original_name: str,
    pages: list[tuple[int | None, str]],
) -> None:
    chunks = chunk_pages(pages)
    if not chunks:
        raise RuntimeError("No content to ingest after chunking")

    embeddings = embed([chunk.content for chunk in chunks])
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding count did not match chunk count")

    with db.tenant_connection(company_id) as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
        rows = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            metadata = {
                "filename": original_name,
                "token_estimate": chunk.token_estimate,
            }
            rows.append(
                (
                    str(uuid.uuid4()),
                    document_id,
                    company_id,
                    chunk.content,
                    to_vector_literal(embedding),
                    chunk.page_number,
                    chunk.index,
                    json.dumps(metadata),
                )
            )
        conn.executemany(
            """
            INSERT INTO document_chunks (
              id, document_id, company_id, content, embedding, page_number, chunk_index, metadata
            )
            VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s::jsonb)
            """,
            rows,
        )
        conn.execute(
            """
            UPDATE documents
            SET status = 'READY',
                error_message = NULL,
                chunk_count = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (len(chunks), document_id),
        )
        conn.commit()

    logger.info("Document %s ready with %s chunks", original_name, len(chunks))


def _mark_failed(document_id: str, reason: str, company_id: str | None = None) -> None:
    try:
        scoped = (
            db.tenant_connection(company_id)
            if company_id
            else db.bypass_rls_connection()
        )
        with scoped as conn:
            conn.execute(
                """
                UPDATE documents
                SET status = 'FAILED', error_message = %s, updated_at = now()
                WHERE id = %s
                """,
                (reason, document_id),
            )
            conn.commit()
    except Exception:
        logger.exception("Could not mark document %s as FAILED", document_id)
