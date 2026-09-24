from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import HTTPException

from app.rag.chunker import clean_text

UPLOAD_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

EXTRACT_TYPES = {
    **UPLOAD_TYPES,
    ".md": "text/markdown",
    ".txt": "text/plain",
}

PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 20


def allowed_upload_suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in UPLOAD_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF or DOCX file.",
        )
    return suffix


def mime_for_filename(filename: str) -> str:
    suffix = allowed_upload_suffix(filename)
    return UPLOAD_TYPES[suffix]


def validate_upload_bytes(filename: str, data: bytes) -> None:
    suffix = allowed_upload_suffix(filename)
    if suffix == ".pdf":
        if not data.startswith(PDF_MAGIC):
            raise HTTPException(status_code=400, detail="File is not a valid PDF")
        return
    if suffix == ".docx":
        _validate_docx_bytes(data)


def _validate_docx_bytes(data: bytes) -> None:
    if not data.startswith(ZIP_MAGIC):
        raise HTTPException(status_code=400, detail="File is not a valid DOCX")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if "word/document.xml" not in names:
                raise HTTPException(status_code=400, detail="File is not a valid DOCX")
            uncompressed = 0
            for info in archive.infolist():
                if info.file_size < 0 or info.compress_size < 0:
                    raise HTTPException(status_code=400, detail="DOCX archive is invalid")
                uncompressed += info.file_size
                if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_DOCX_COMPRESSION_RATIO:
                    raise HTTPException(status_code=400, detail="DOCX appears to be compressed unsafely")
                if uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise HTTPException(status_code=400, detail="DOCX uncompressed size is too large")
    except HTTPException:
        raise
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="File is not a valid DOCX") from exc

UPLOAD_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

EXTRACT_TYPES = {
    **UPLOAD_TYPES,
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def allowed_upload_suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in UPLOAD_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF or DOCX file.",
        )
    return suffix


def mime_for_filename(filename: str) -> str:
    suffix = allowed_upload_suffix(filename)
    return UPLOAD_TYPES[suffix]


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in EXTRACT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF or DOCX file.",
        )
    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix == ".docx":
        return _extract_docx(data)
    text = clean_text(data.decode("utf-8"))
    if not text:
        raise HTTPException(status_code=400, detail="File contained no extractable text")
    return [(None, text)]


def _extract_pdf(data: bytes) -> list[tuple[int | None, str]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this PDF") from exc

    pages: list[tuple[int | None, str]] = []
    for i, page in enumerate(reader.pages):
        text = clean_text(page.extract_text() or "")
        if text:
            pages.append((i + 1, text))
    if not pages:
        raise HTTPException(status_code=400, detail="PDF contained no extractable text")
    return pages


def _extract_docx(data: bytes) -> list[tuple[int | None, str]]:
    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this DOCX file") from exc

    parts = [p.text.strip() for p in document.paragraphs if p.text and p.text.strip()]
    text = clean_text("\n\n".join(parts))
    if not text:
        raise HTTPException(status_code=400, detail="DOCX contained no extractable text")
    return [(None, text)]
