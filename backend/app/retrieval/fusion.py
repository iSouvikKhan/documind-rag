"""Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, SIGIR 2009)."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: dict[str, Sequence[RetrievedChunk]], k: int = 60
) -> list[RetrievedChunk]:
    """Merge ranked lists into one, scoring each chunk by sum(1 / (k + rank)).

    ``ranked_lists`` maps a source name ("vector", "keyword") to results ordered best
    first. Chunks found by several sources are merged, keeping every source's score.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    merged: dict[object, RetrievedChunk] = {}
    for source, results in ranked_lists.items():
        for rank, chunk in enumerate(results, start=1):
            current = merged.get(chunk.chunk_id)
            if current is None:
                current = RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    page=chunk.page,
                )
                merged[chunk.chunk_id] = current
            current.fusion_score += 1.0 / (k + rank)
            current.sources.add(source)
            if chunk.vector_score is not None:
                current.vector_score = chunk.vector_score
            if chunk.keyword_score is not None:
                current.keyword_score = chunk.keyword_score
    return sorted(merged.values(), key=lambda c: c.fusion_score, reverse=True)
