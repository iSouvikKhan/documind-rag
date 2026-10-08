from __future__ import annotations

import sys
import uuid

import pytest

from app.domain import RetrievedChunk
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.reranker import FlashRankReranker, NoopReranker
from tests.conftest import make_docx


def chunk(name: str, **scores) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        document_id=uuid.uuid4(),
        filename=f"{name}.pdf",
        content=name,
        chunk_index=0,
        page=1,
        **scores,
    )


def test_rrf_rewards_items_found_by_both_retrievers():
    a, b, c = chunk("a"), chunk("b"), chunk("c")
    fused = reciprocal_rank_fusion({"vector": [a, b], "keyword": [c, b]}, k=60)
    assert fused[0].content == "b"  # ranked 2nd twice beats 1st once
    assert fused[0].sources == {"vector", "keyword"}
    assert fused[0].fusion_score == pytest.approx(2 / 62)
    assert {f.content for f in fused} == {"a", "b", "c"}


def test_rrf_keeps_scores_from_each_source():
    v = chunk("x", vector_score=0.9)
    k = chunk("x", keyword_score=0.4)
    [fused] = reciprocal_rank_fusion({"vector": [v], "keyword": [k]})
    assert fused.vector_score == 0.9
    assert fused.keyword_score == 0.4


def test_rrf_rejects_invalid_k():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"vector": []}, k=0)


def test_noop_reranker_truncates():
    chunks = [chunk(str(i)) for i in range(5)]
    assert [c.content for c in NoopReranker().rerank("q", chunks, 2)] == ["0", "1"]


def test_flashrank_falls_back_when_model_cannot_load(monkeypatch):
    monkeypatch.setitem(sys.modules, "flashrank", None)  # makes `import flashrank` fail
    chunks = [chunk("a"), chunk("b"), chunk("c")]
    reranker = FlashRankReranker("missing-model")
    assert [c.content for c in reranker.rerank("q", chunks, 2)] == ["a", "b"]
    assert reranker._failed


def test_flashrank_reorders_with_scores(monkeypatch):
    class FakeRanker:
        def rerank(self, request):
            return [{"id": 2, "score": 0.9}, {"id": 0, "score": 0.5}, {"id": 1, "score": 0.1}]

    reranker = FlashRankReranker("fake")
    reranker._ranker = FakeRanker()
    result = reranker.rerank("q", [chunk("a"), chunk("b"), chunk("c")], 2)
    assert [c.content for c in result] == ["c", "a"]
    assert result[0].rerank_score == 0.9


def test_hybrid_retriever_returns_relevant_chunk(ingestion, retriever):
    ingestion.ingest("pets.docx", make_docx("Cats sleep most of the day. " * 3))
    ingestion.ingest("cars.docx", make_docx("Electric vehicles need charging stations. " * 3))
    results = retriever.retrieve("Where do electric vehicles get charging?")
    assert results
    assert results[0].filename == "cars.docx"
    assert "keyword" in results[0].sources
    assert len(results) <= 3


def test_hybrid_retriever_ignores_blank_query(retriever):
    assert retriever.retrieve("   ") == []
