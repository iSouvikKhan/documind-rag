"""Hybrid retrieval: vector search + full-text search -> RRF -> re-ranking."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings

from app.db.repository import DocumentRepository
from app.domain import RetrievedChunk
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


@dataclass
class RetrievalConfig:
    vector_top_k: int = 20
    keyword_top_k: int = 20
    rrf_k: int = 60
    rerank_candidates: int = 20
    final_top_k: int = 5


class HybridRetriever:
    def __init__(
        self,
        repository: DocumentRepository,
        embeddings: Embeddings,
        reranker: Reranker,
        config: RetrievalConfig,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.reranker = reranker
        self.config = config

    def retrieve(
        self, query: str, collection: str = "default", top_k: int | None = None
    ) -> list[RetrievedChunk]:
        query = query.strip()
        if not query:
            return []
        cfg = self.config
        final_k = top_k or cfg.final_top_k

        query_vector = self.embeddings.embed_query(query)
        vector_hits = self.repository.vector_search(collection, query_vector, cfg.vector_top_k)
        keyword_hits = self.repository.keyword_search(collection, query, cfg.keyword_top_k)

        fused = reciprocal_rank_fusion(
            {"vector": vector_hits, "keyword": keyword_hits}, k=cfg.rrf_k
        )
        candidates = fused[: max(cfg.rerank_candidates, final_k)]
        results = self.reranker.rerank(query, candidates, final_k)
        logger.debug(
            "retrieve q=%r vector=%d keyword=%d fused=%d returned=%d",
            query,
            len(vector_hits),
            len(keyword_hits),
            len(fused),
            len(results),
        )
        return results
