from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

COLLECTION_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    num_chunks: int
    collection: str
    created_at: datetime


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    collection: str = Field(default="default", pattern=COLLECTION_PATTERN)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class SourceOut(BaseModel):
    id: int
    document_id: str
    chunk_id: str
    filename: str
    page: int | None
    label: str
    snippet: str
    content: str
    scores: dict[str, float | None]
    matched_by: list[str]


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    cited: list[int]


class ProviderInfo(BaseModel):
    provider: str
    model: str


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    llm: ProviderInfo
    embeddings: ProviderInfo
    embedding_dim: int
    reranker: str
    errors: list[str]


class ErrorOut(BaseModel):
    detail: str
