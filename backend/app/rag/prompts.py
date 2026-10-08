"""Prompt templates. Two styles exist so the evaluation can compare them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.domain import RetrievedChunk

GROUNDED_SYSTEM = """You are DocuMind, an assistant that answers questions about the user's \
documents.

Rules:
- Use ONLY the numbered sources below. Do not use outside knowledge.
- Cite the sources that support each sentence with their numbers in square brackets, \
for example [1] or [2][3].
- If the sources do not contain the answer, reply exactly: "I couldn't find this in the \
uploaded documents." Do not guess.
- Be concise and precise. Quote numbers and names exactly as written in the sources.

Sources:
{context}"""

BASIC_SYSTEM = """Answer the user's question using the context below. \
Mention source numbers like [1] when helpful.

Context:
{context}"""

PROMPTS = {"grounded": GROUNDED_SYSTEM, "basic": BASIC_SYSTEM}

NOT_FOUND_ANSWER = "I couldn't find this in the uploaded documents."
MAX_HISTORY_MESSAGES = 8


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


def source_label(chunk: RetrievedChunk) -> str:
    return f"{chunk.filename}, page {chunk.page}" if chunk.page else chunk.filename


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{i}] ({source_label(c)})\n{c.content}" for i, c in enumerate(chunks, start=1)
    )


def build_messages(
    question: str,
    chunks: Sequence[RetrievedChunk],
    style: str = "grounded",
    history: Sequence[ChatTurn] = (),
) -> list[BaseMessage]:
    if style not in PROMPTS:
        raise ValueError(f"Unknown prompt style '{style}'. Choose from {sorted(PROMPTS)}")
    # Context is inserted with str.replace (not str.format) so braces in documents are safe.
    system = PROMPTS[style].replace("{context}", format_context(chunks))
    messages: list[BaseMessage] = [SystemMessage(content=system)]
    for turn in list(history)[-MAX_HISTORY_MESSAGES:]:
        cls = HumanMessage if turn.role == "user" else AIMessage
        messages.append(cls(content=turn.content))
    messages.append(HumanMessage(content=question))
    return messages
