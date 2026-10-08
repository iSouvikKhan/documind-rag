from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain import RetrievedChunk
from app.rag.prompts import source_label

_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
SNIPPET_CHARS = 320


def extract_citations(answer: str, num_sources: int) -> list[int]:
    """Return the distinct, valid source numbers cited in ``answer``, in first-use order.

    Handles ``[1]``, ``[1][2]`` and ``[1, 2]``; numbers outside 1..num_sources are ignored.
    """
    seen: list[int] = []
    for match in _CITATION.finditer(answer):
        for part in match.group(1).split(","):
            n = int(part)
            if 1 <= n <= num_sources and n not in seen:
                seen.append(n)
    return seen


def snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def to_sources(chunks: Sequence[RetrievedChunk]) -> list[dict]:
    """Serializable source list sent to the client before the answer streams."""
    return [
        {
            "id": i,
            "document_id": str(c.document_id),
            "chunk_id": str(c.chunk_id),
            "filename": c.filename,
            "page": c.page,
            "label": source_label(c),
            "snippet": snippet(c.content),
            "content": c.content,
            "scores": {
                "vector": c.vector_score,
                "keyword": c.keyword_score,
                "fusion": round(c.fusion_score, 6),
                "rerank": c.rerank_score,
            },
            "matched_by": sorted(c.sources),
        }
        for i, c in enumerate(chunks, start=1)
    ]
