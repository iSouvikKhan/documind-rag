"""Ingestion pipeline: validate -> extract text -> chunk -> embed -> store."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings

from app.db.repository import DocumentRepository
from app.domain import Document
from app.ingestion.chunking import chunk_pages
from app.ingestion.parsers import EmptyDocumentError, IngestionError, extract_text

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


class FileTooLargeError(IngestionError):
    pass


class DuplicateDocumentError(IngestionError):
    def __init__(self, existing: Document) -> None:
        super().__init__(f"'{existing.filename}' with identical content is already ingested")
        self.existing = existing


@dataclass
class ChunkingConfig:
    chunk_size: int
    chunk_overlap: int


class IngestionService:
    def __init__(
        self,
        repository: DocumentRepository,
        embeddings: Embeddings,
        embedding_model: str,
        chunking: ChunkingConfig,
        max_upload_bytes: int,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.embedding_model = embedding_model
        self.chunking = chunking
        self.max_upload_bytes = max_upload_bytes

    def ingest(
        self,
        filename: str,
        data: bytes,
        collection: str = "default",
        chunking: ChunkingConfig | None = None,
    ) -> Document:
        filename = (filename or "").strip().replace("\\", "/").split("/")[-1]
        if not filename:
            raise IngestionError("A file name is required")
        if not data:
            raise EmptyDocumentError("The uploaded file is empty")
        if len(data) > self.max_upload_bytes:
            raise FileTooLargeError(
                f"File is {len(data) / 1_048_576:.1f} MB; the limit is "
                f"{self.max_upload_bytes // 1_048_576} MB"
            )

        sha256 = hashlib.sha256(data).hexdigest()
        existing = self.repository.find_by_hash(collection, sha256)
        if existing:
            raise DuplicateDocumentError(existing)

        content_type, pages = extract_text(filename, data)
        cfg = chunking or self.chunking
        chunks = chunk_pages(pages, cfg.chunk_size, cfg.chunk_overlap)
        if not chunks:
            raise EmptyDocumentError(f"No text chunks could be created from '{filename}'")

        texts = [c.content for c in chunks]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            vectors.extend(self.embeddings.embed_documents(texts[start : start + EMBED_BATCH_SIZE]))

        document = self.repository.add_document(
            collection=collection,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha256,
            embedding_model=self.embedding_model,
            chunks=chunks,
            embeddings=vectors,
        )
        logger.info("Ingested %s: %d pages, %d chunks", filename, len(pages), len(chunks))
        return document
