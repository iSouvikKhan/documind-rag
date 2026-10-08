"""Second-stage re-ranking of fused candidates."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Protocol

from app.domain import RetrievedChunk

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]: ...


class NoopReranker:
    """Keeps the fusion order."""

    def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return list(chunks)[:top_k]


class FlashRankReranker:
    """Cross-encoder re-ranking with FlashRank (small ONNX models, CPU only).

    The model (~20-40 MB) is downloaded on first use. If it cannot be loaded, for example
    when offline, the reranker logs a warning and falls back to the fusion order instead
    of failing the request.
    """

    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._ranker = None
        self._failed = False
        self._lock = threading.Lock()

    def _load(self):
        if self._ranker is not None or self._failed:
            return self._ranker
        with self._lock:
            if self._ranker is None and not self._failed:
                try:
                    from flashrank import Ranker

                    kwargs = {"model_name": self.model_name}
                    if self.cache_dir:
                        kwargs["cache_dir"] = self.cache_dir
                    self._ranker = Ranker(**kwargs)
                    logger.info("Loaded FlashRank model %s", self.model_name)
                except Exception as exc:
                    self._failed = True
                    logger.warning("Re-ranker unavailable, using fusion order instead: %s", exc)
        return self._ranker

    def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        chunks = list(chunks)
        ranker = self._load()
        if ranker is None or not chunks:
            return chunks[:top_k]

        from flashrank import RerankRequest

        passages = [{"id": i, "text": c.content} for i, c in enumerate(chunks)]
        try:
            results = ranker.rerank(RerankRequest(query=query, passages=passages))
        except Exception as exc:
            logger.warning("Re-ranking failed, using fusion order: %s", exc)
            return chunks[:top_k]

        reranked = []
        for r in results[:top_k]:
            chunk = chunks[int(r["id"])]
            chunk.rerank_score = float(r["score"])
            reranked.append(chunk)
        return reranked


def build_reranker(kind: str, model_name: str, cache_dir: str | None = None) -> Reranker:
    if kind == "none":
        return NoopReranker()
    return FlashRankReranker(model_name, cache_dir)
