"""Answer generation over retrieved chunks, streamed token by token."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from starlette.concurrency import run_in_threadpool

from app.domain import RetrievedChunk
from app.rag.citations import extract_citations, to_sources
from app.rag.prompts import NOT_FOUND_ANSWER, ChatTurn, build_messages
from app.retrieval.retriever import HybridRetriever

logger = logging.getLogger(__name__)


@dataclass
class ChatEvent:
    event: str  # "sources" | "token" | "done" | "error"
    data: Any


@dataclass
class Answer:
    text: str
    chunks: list[RetrievedChunk]
    cited: list[int] = field(default_factory=list)


def _text(content: Any) -> str:
    """Message chunks may carry a string or a list of content parts depending on provider."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return ""


class ChatService:
    def __init__(
        self, retriever: HybridRetriever, llm: BaseChatModel, prompt_style: str = "grounded"
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.prompt_style = prompt_style

    async def stream(
        self, question: str, collection: str = "default", history: Sequence[ChatTurn] = ()
    ) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        try:
            chunks = await run_in_threadpool(self.retriever.retrieve, question, collection)
        except Exception as exc:
            logger.exception("Retrieval failed")
            yield ChatEvent("error", {"message": f"Retrieval failed: {exc}"})
            return

        yield ChatEvent("sources", {"sources": to_sources(chunks)})

        if not chunks:
            yield ChatEvent("token", {"text": NOT_FOUND_ANSWER})
            yield ChatEvent("done", {"cited": [], "elapsed_ms": _ms(started)})
            return

        messages = build_messages(question, chunks, self.prompt_style, history)
        answer = []
        try:
            async for piece in self.llm.astream(messages):
                text = _text(piece.content)
                if text:
                    answer.append(text)
                    yield ChatEvent("token", {"text": text})
        except Exception as exc:
            logger.exception("LLM streaming failed")
            yield ChatEvent("error", {"message": f"The language model failed: {exc}"})
            return

        cited = extract_citations("".join(answer), len(chunks))
        yield ChatEvent("done", {"cited": cited, "elapsed_ms": _ms(started)})

    async def answer(
        self,
        question: str,
        collection: str = "default",
        prompt_style: str | None = None,
        top_k: int | None = None,
    ) -> Answer:
        """Non-streaming variant of :meth:`stream`."""
        chunks = await run_in_threadpool(self.retriever.retrieve, question, collection, top_k)
        return await self.generate(question, chunks, prompt_style)

    async def generate(
        self, question: str, chunks: list[RetrievedChunk], prompt_style: str | None = None
    ) -> Answer:
        """Answer from already-retrieved chunks (lets the evaluation reuse one retrieval)."""
        if not chunks:
            return Answer(NOT_FOUND_ANSWER, [], [])
        messages = build_messages(question, chunks, prompt_style or self.prompt_style)
        result = await self.llm.ainvoke(messages)
        text = _text(result.content)
        return Answer(text, chunks, extract_citations(text, len(chunks)))


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
