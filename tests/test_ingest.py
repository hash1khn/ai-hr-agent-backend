import pytest
from fastapi import HTTPException

from app.rag.chunker import chunk_pages, chunk_text, clean_text
from app.rag.extract import extract_pages, mime_for_filename


def test_clean_text_collapses_whitespace():
    text = clean_text("Hello   world\n\n\nNext   line\x00")
    assert text == "Hello world\n\nNext line"


def test_chunk_text_respects_size(monkeypatch):
    from app.rag import chunker

    monkeypatch.setattr(
        chunker,
        "get_settings",
        lambda: type("S", (), {"chunk_size": 40, "chunk_overlap": 8})(),
    )
    chunks = chunk_text("A" * 100)
    assert len(chunks) > 1
    assert chunks[0].index == 0
    assert all(len(chunk.content) <= 40 for chunk in chunks)


def test_chunk_pages_keeps_page_numbers(monkeypatch):
    from app.rag import chunker

    monkeypatch.setattr(
        chunker,
        "get_settings",
        lambda: type("S", (), {"chunk_size": 1000, "chunk_overlap": 50})(),
    )
    chunks = chunk_pages([(1, "Page one policy."), (2, "Page two policy.")])
    assert [chunk.page_number for chunk in chunks] == [1, 2]


def test_reject_unsupported_upload_type():
    with pytest.raises(HTTPException) as exc:
        mime_for_filename("secrets.exe")
    assert exc.value.status_code == 400


def test_extract_markdown_pages():
    pages = extract_pages("leave-policy.md", b"# Leave\n\nEmployees receive 24 annual leaves.")
    assert pages[0][0] is None
    assert "24 annual leaves" in pages[0][1]


def test_reject_pdf_with_wrong_magic_bytes():
    from app.rag.extract import validate_upload_bytes

    with pytest.raises(HTTPException) as exc:
        validate_upload_bytes("policy.pdf", b"not-a-pdf")
    assert exc.value.status_code == 400


def test_reject_docx_with_wrong_magic_bytes():
    from app.rag.extract import validate_upload_bytes

    with pytest.raises(HTTPException) as exc:
        validate_upload_bytes("policy.docx", b"not-a-zip")
    assert exc.value.status_code == 400
