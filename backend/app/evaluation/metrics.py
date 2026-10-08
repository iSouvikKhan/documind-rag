"""Evaluation metrics. Everything here is pure and unit-tested; the LLM judge lives in judge.py."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from statistics import mean

from app.domain import RetrievedChunk

_REFUSAL_PATTERNS = (
    "couldn't find",
    "could not find",
    "not in the uploaded documents",
    "not mentioned in",
    "no information",
    "does not contain",
    "do not contain",
    "don't contain",
)


@dataclass
class EvalItem:
    id: str
    question: str
    expected_document: str | None  # None means the corpus does not contain the answer
    evidence: str | None = None  # short exact phrase from the expected document
    answer_keywords: list[str] = field(default_factory=list)

    @property
    def answerable(self) -> bool:
        return self.expected_document is not None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def is_relevant(chunk: RetrievedChunk, item: EvalItem) -> bool:
    """A chunk is relevant if it comes from the expected document and contains the evidence."""
    if not item.answerable or chunk.filename != item.expected_document:
        return False
    return item.evidence is None or normalize(item.evidence) in normalize(chunk.content)


def first_relevant_rank(chunks: Sequence[RetrievedChunk], item: EvalItem) -> int | None:
    for rank, chunk in enumerate(chunks, start=1):
        if is_relevant(chunk, item):
            return rank
    return None


def hit_at_k(chunks: Sequence[RetrievedChunk], item: EvalItem, k: int) -> float:
    rank = first_relevant_rank(chunks[:k], item)
    return 1.0 if rank is not None else 0.0


def reciprocal_rank(chunks: Sequence[RetrievedChunk], item: EvalItem) -> float:
    rank = first_relevant_rank(chunks, item)
    return 1.0 / rank if rank else 0.0


def document_hit(chunks: Sequence[RetrievedChunk], item: EvalItem) -> float:
    return 1.0 if any(c.filename == item.expected_document for c in chunks) else 0.0


def keyword_recall(answer: str, keywords: Iterable[str]) -> float | None:
    """Share of expected keywords present in the answer (None when no keywords are defined)."""
    keywords = list(keywords)
    if not keywords:
        return None
    text = normalize(answer)
    return sum(1 for k in keywords if normalize(k) in text) / len(keywords)


def is_refusal(answer: str) -> bool:
    text = normalize(answer).replace("’", "'")
    return any(p in text for p in _REFUSAL_PATTERNS)


def safe_mean(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(mean(present), 4) if present else None
