"""Plain data types shared across layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class PageText:
    """Text extracted from one page (PDF) or the whole document (DOCX: page is None)."""

    text: str
    page: int | None = None


@dataclass(frozen=True)
class ChunkDraft:
    """A chunk produced by the splitter, before it has an id or an embedding."""

    content: str
    chunk_index: int
    page: int | None = None


@dataclass
class Document:
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    num_chunks: int
    collection: str
    created_at: datetime


@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    filename: str
    content: str
    chunk_index: int
    page: int | None
    # Scores filled in by the different retrieval stages (None when a stage did not see it).
    vector_score: float | None = None
    keyword_score: float | None = None
    fusion_score: float = 0.0
    rerank_score: float | None = None
    sources: set[str] = field(default_factory=set)  # {"vector", "keyword"}
