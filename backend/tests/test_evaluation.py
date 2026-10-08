from __future__ import annotations

import uuid

import pytest

from app.domain import RetrievedChunk
from app.evaluation.judge import judge_faithfulness, parse_judgement
from app.evaluation.metrics import (
    EvalItem,
    document_hit,
    hit_at_k,
    is_refusal,
    keyword_recall,
    reciprocal_rank,
    safe_mean,
)
from app.evaluation.run import ItemResult, load_dataset, render_markdown, summarize
from tests.conftest import fake_llm

ITEM = EvalItem("q1", "How long?", "manual.pdf", "2-year  limited\nwarranty", ["2-year"])


def chunk(filename: str, content: str) -> RetrievedChunk:
    return RetrievedChunk(uuid.uuid4(), uuid.uuid4(), filename, content, 0, 1)


def test_retrieval_metrics():
    chunks = [
        chunk("manual.pdf", "Install the C-wire."),
        chunk("other.pdf", "2-year limited warranty"),  # right text, wrong document
        chunk("manual.pdf", "It has a 2-Year Limited Warranty."),
    ]
    assert hit_at_k(chunks, ITEM, 2) == 0.0
    assert hit_at_k(chunks, ITEM, 3) == 1.0
    assert reciprocal_rank(chunks, ITEM) == pytest.approx(1 / 3)
    assert document_hit(chunks, ITEM) == 1.0
    assert reciprocal_rank(chunks[:2], ITEM) == 0.0


def test_keyword_recall_and_refusal():
    assert keyword_recall("It has a 2-year warranty", ["2-year", "limited"]) == 0.5
    assert keyword_recall("anything", []) is None
    assert is_refusal("I couldn’t find this in the uploaded documents.")
    assert not is_refusal("The warranty lasts 2 years [1].")


def test_safe_mean_skips_none():
    assert safe_mean([1.0, None, 0.0]) == 0.5
    assert safe_mean([None]) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '{"claims": [{"claim": "a", "supported": true}, {"claim": "b", "supported": false}]}',
            (1, 2),
        ),
        ('Sure! ```json\n{"claims": [{"claim": "a", "supported": "true"}]}\n```', (1, 1)),
        ('{"claims": []}', (0, 0)),
        ("not json", None),
        ('{"verdict": "ok"}', None),
    ],
)
def test_parse_judgement(raw, expected):
    assert parse_judgement(raw) == expected


async def test_judge_faithfulness_scores_claims():
    llm = fake_llm(
        '{"claims": [{"claim": "x", "supported": true}, {"claim": "y", "supported": true}, '
        '{"claim": "z", "supported": false}]}'
    )
    result = await judge_faithfulness(llm, "context", "answer")
    assert result.score == pytest.approx(2 / 3)
    assert (result.supported, result.total) == (2, 3)


def test_summarize_and_markdown():
    def r(item_id, answerable, hit, faith, refused):
        return ItemResult(
            item_id, "small", "grounded", answerable, hit, hit, hit, faith, None, refused, "", []
        )

    rows = summarize(
        [
            r("a", True, 1.0, 1.0, False),
            r("b", True, 0.0, 0.5, True),
            r("c", False, None, None, True),
        ]
    )
    [row] = rows
    assert row["hit_at_k"] == 0.5
    assert row["faithfulness"] == 0.75
    assert row["false_refusal_rate"] == 0.5
    assert row["unanswerable_refusal_rate"] == 1.0
    md = render_markdown(
        rows,
        {
            "run_at": "t",
            "llm": "l",
            "embeddings": "e",
            "reranker": "r",
            "judge": "j",
            "top_k": 4,
            "questions": 3,
        },
    )
    assert "| small | grounded | 0.500 |" in md


def test_bundled_dataset_loads():
    from app.evaluation.run import EVAL_DIR

    items = load_dataset(EVAL_DIR / "dataset.json")
    assert len(items) >= 15
    assert any(not i.answerable for i in items)
    assert all(i.evidence for i in items if i.answerable)
