"""Wires settings into concrete services at startup.

If the database or a provider is misconfigured the API still starts: the problem is
reported by /api/health and dependent endpoints answer 503 with the reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from psycopg_pool import ConnectionPool

from app.config import Settings
from app.db.pool import create_pool
from app.db.repository import DocumentRepository, PostgresRepository
from app.db.schema import ensure_schema
from app.ingestion.service import ChunkingConfig, IngestionService
from app.providers import build_chat_model, build_embeddings
from app.rag.chat import ChatService
from app.retrieval.reranker import build_reranker
from app.retrieval.retriever import HybridRetriever, RetrievalConfig

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    repository: DocumentRepository | None = None
    ingestion: IngestionService | None = None
    retriever: HybridRetriever | None = None
    chat: ChatService | None = None
    pool: ConnectionPool | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.chat is not None and self.ingestion is not None and not self.errors

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()


def retrieval_config(settings: Settings) -> RetrievalConfig:
    return RetrievalConfig(
        vector_top_k=settings.vector_top_k,
        keyword_top_k=settings.keyword_top_k,
        rrf_k=settings.rrf_k,
        rerank_candidates=max(settings.vector_top_k, settings.keyword_top_k),
        final_top_k=settings.final_top_k,
    )


def build_services(settings: Settings) -> Services:
    services = Services(settings=settings)

    try:
        embeddings = build_embeddings(settings)
        llm = build_chat_model(settings)
    except Exception as exc:
        logger.error("Model provider configuration error: %s", exc)
        services.errors.append(str(exc))
        return services

    try:
        ensure_schema(settings.database_url, settings.embedding_dim, settings.db_connect_timeout)
        services.pool = create_pool(
            settings.database_url,
            settings.db_pool_min_size,
            settings.db_pool_max_size,
            settings.db_connect_timeout,
        )
    except Exception as exc:
        logger.error("Database unavailable: %s", exc)
        services.errors.append(f"Database unavailable: {exc}")
        return services

    repository = PostgresRepository(services.pool)
    retriever = HybridRetriever(
        repository,
        embeddings,
        build_reranker(settings.reranker, settings.reranker_model, settings.reranker_cache_dir),
        retrieval_config(settings),
    )
    services.repository = repository
    services.retriever = retriever
    services.ingestion = IngestionService(
        repository,
        embeddings,
        settings.resolved_embedding_model,
        ChunkingConfig(settings.chunk_size, settings.chunk_overlap),
        settings.max_upload_bytes,
    )
    services.chat = ChatService(retriever, llm, settings.prompt_style)
    return services
