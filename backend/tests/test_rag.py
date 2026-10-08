from __future__ import annotations

import json
import uuid

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain import RetrievedChunk
from app.rag.chat import ChatService
from app.rag.citations import extract_citations, snippet, to_sources
from app.rag.prompts import NOT_FOUND_ANSWER, ChatTurn, build_messages, format_context
from app.rag.sse import format_sse
from tests.conftest import fake_llm, make_docx


def chunk(content: str, page: int | None = 2) -> RetrievedChunk:
    return RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "doc.pdf", content, 0, page)


def test_extract_citations_handles_formats_and_bounds():
    answer = "A [2]. B [1][2]. C [3, 1]. D [9]. E [0]."
    assert extract_citations(answer, 3) == [2, 1, 3]


def test_snippet_truncates_on_word_boundary():
    text = "word " * 200
    s = snippet(text, 50)
    assert s.endswith("…") and len(s) <= 51


def test_format_context_numbers_sources_with_pages():
    ctx = format_context([chunk("alpha"), chunk("beta", page=None)])
    assert ctx.startswith("[1] (doc.pdf, page 2)\nalpha")
    assert "[2] (doc.pdf)\nbeta" in ctx


def test_build_messages_is_safe_with_braces_and_limits_history():
    history = [ChatTurn("user", f"q{i}") for i in range(20)]
    messages = build_messages("Q?", [chunk('json {"a": 1} {context}')], "grounded", history)
    assert isinstance(messages[0], SystemMessage)
    assert '{"a": 1}' in messages[0].content
    assert isinstance(messages[-1], HumanMessage) and messages[-1].content == "Q?"
    assert len(messages) == 1 + 8 + 1


def test_build_messages_rejects_unknown_style():
    with pytest.raises(ValueError):
        build_messages("q", [], "poetic")


def test_to_sources_shape():
    [src] = to_sources([chunk("text")])
    assert src["id"] == 1 and src["label"] == "doc.pdf, page 2"
    assert set(src["scores"]) == {"vector", "keyword", "fusion", "rerank"}


def test_format_sse_is_single_data_line():
    msg = format_sse("token", {"text": "line1\nline2"})
    assert msg.startswith("event: token\ndata: ")
    assert msg.endswith("\n\n")
    assert msg.count("\n") == 3
    assert json.loads(msg.split("data: ", 1)[1]) == {"text": "line1\nline2"}


async def collect(service, question="What is the policy?"):
    return [e async for e in service.stream(question)]


async def test_stream_emits_sources_tokens_and_done(ingestion, retriever):
    ingestion.ingest("policy.docx", make_docx("The policy grants 21 days of leave."))
    events = await collect(ChatService(retriever, fake_llm("Employees get 21 days [1].")))
    kinds = [e.event for e in events]
    assert kinds[0] == "sources" and kinds[-1] == "done"
    assert "token" in kinds
    text = "".join(e.data["text"] for e in events if e.event == "token")
    assert text == "Employees get 21 days [1]."
    assert events[-1].data["cited"] == [1]


async def test_stream_without_documents_returns_not_found(retriever):
    events = await collect(ChatService(retriever, fake_llm("unused")))
    assert [e.event for e in events] == ["sources", "token", "done"]
    assert events[1].data["text"] == NOT_FOUND_ANSWER


async def test_stream_reports_llm_errors(ingestion, retriever):
    class BrokenLLM:
        async def astream(self, messages):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

    ingestion.ingest("policy.docx", make_docx("Some policy text."))
    events = await collect(ChatService(retriever, BrokenLLM()))
    assert events[-1].event == "error"
    assert "connection refused" in events[-1].data["message"]


async def test_generate_uses_given_chunks():
    service = ChatService(retriever=None, llm=fake_llm("It is blue [1]."))
    answer = await service.generate("color?", [chunk("The sky is blue.")], "basic")
    assert answer.text == "It is blue [1]." and answer.cited == [1]
