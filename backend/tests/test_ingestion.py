from __future__ import annotations

import pytest

from app.domain import PageText
from app.ingestion.chunking import chunk_pages
from app.ingestion.parsers import (
    EmptyDocumentError,
    UnsupportedFileError,
    detect_content_type,
    extract_text,
    normalize_text,
)
from app.ingestion.service import ChunkingConfig, DuplicateDocumentError, FileTooLargeError
from tests.conftest import make_docx, make_pdf


def test_pdf_pages_keep_page_numbers():
    content_type, pages = extract_text("a.pdf", make_pdf("First page text.", "", "Third page."))
    assert content_type == "application/pdf"
    assert [p.page for p in pages] == [1, 3]  # blank page 2 skipped
    assert pages[0].text == "First page text."


def test_docx_extracts_paragraphs():
    content_type, pages = extract_text("a.docx", make_docx("Hello world.", "", "Second para."))
    assert content_type.endswith("wordprocessingml.document")
    assert pages[0].page is None
    assert pages[0].text == "Hello world.\nSecond para."


def test_unsupported_extension_rejected():
    with pytest.raises(UnsupportedFileError, match="Unsupported"):
        detect_content_type("notes.txt", b"hello")


def test_mismatched_signature_rejected():
    with pytest.raises(UnsupportedFileError, match="does not look like"):
        detect_content_type("fake.pdf", b"PK\x03\x04not a pdf")


def test_pdf_without_text_is_empty():
    with pytest.raises(EmptyDocumentError, match="OCR"):
        extract_text("scan.pdf", make_pdf(""))


def test_normalize_text_joins_hyphenation_and_collapses_spaces():
    assert normalize_text("infor-\nmation   is\n\n\n\nkey ") == "information is\n\nkey"


def test_chunking_preserves_pages_and_indexes():
    pages = [PageText("word " * 100, 1), PageText("other " * 100, 2)]
    chunks = chunk_pages(pages, chunk_size=120, chunk_overlap=20)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.page for c in chunks} == {1, 2}
    assert all(len(c.content) <= 120 for c in chunks)


def test_chunking_rejects_overlap_not_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_pages([PageText("x")], chunk_size=100, chunk_overlap=100)


def test_ingest_stores_document_and_chunks(ingestion, repository):
    data = make_docx("Brightpath gives 21 days of PTO. " * 20)
    doc = ingestion.ingest("handbook.docx", data)
    assert doc.filename == "handbook.docx"
    assert doc.num_chunks == len(repository.chunks) > 1
    assert all(len(e) == 16 for _, _, e in repository.chunks)


def test_ingest_strips_directories_from_filename(ingestion):
    doc = ingestion.ingest("C:\\Users\\me\\report.pdf", make_pdf("Some text here."))
    assert doc.filename == "report.pdf"


def test_ingest_rejects_duplicates_per_collection(ingestion):
    data = make_pdf("Same content.")
    ingestion.ingest("a.pdf", data)
    with pytest.raises(DuplicateDocumentError):
        ingestion.ingest("b.pdf", data)
    assert ingestion.ingest("a.pdf", data, collection="other").collection == "other"


def test_ingest_rejects_oversized_and_empty_files(ingestion):
    with pytest.raises(FileTooLargeError):
        ingestion.ingest("big.pdf", b"%PDF-" + b"0" * (ingestion.max_upload_bytes + 1))
    with pytest.raises(EmptyDocumentError):
        ingestion.ingest("empty.pdf", b"")


def test_ingest_uses_override_chunking(ingestion, repository):
    ingestion.ingest(
        "a.docx", make_docx("alpha beta gamma delta. " * 40), chunking=ChunkingConfig(500, 0)
    )
    big = len(repository.chunks)
    ingestion.ingest(
        "b.docx", make_docx("alpha beta gamma delta! " * 40), chunking=ChunkingConfig(100, 0)
    )
    assert len(repository.chunks) - big > big
