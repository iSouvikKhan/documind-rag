"""LLM-as-judge faithfulness: the share of an answer's claims supported by the context."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = """You check whether an answer is faithful to a context.

1. Split the ANSWER into short, atomic factual claims. Ignore citation markers like [1].
2. For each claim decide if it is directly supported by the CONTEXT (true) or not (false).
   A claim that adds facts not stated in the context is NOT supported.
3. Reply with JSON only, no prose, in this exact shape:
{"claims": [{"claim": "...", "supported": true}]}
If the answer only says the information could not be found, reply {"claims": []}."""


@dataclass
class FaithfulnessResult:
    score: float | None  # None when the answer made no factual claims or parsing failed
    supported: int
    total: int
    raw: str


def parse_judgement(raw: str) -> tuple[int, int] | None:
    """Return (supported, total) from the judge output, or None if it cannot be parsed."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        return None
    flags = [c.get("supported") for c in claims if isinstance(c, dict)]
    supported = sum(1 for f in flags if f is True or str(f).lower() == "true")
    return supported, len(flags)


async def judge_faithfulness(llm: BaseChatModel, context: str, answer: str) -> FaithfulnessResult:
    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=f"CONTEXT:\n{context}\n\nANSWER:\n{answer}"),
    ]
    result = await llm.ainvoke(messages)
    raw = result.content if isinstance(result.content, str) else str(result.content)
    parsed = parse_judgement(raw)
    if parsed is None:
        logger.warning("Could not parse judge output: %s", raw[:200])
        return FaithfulnessResult(None, 0, 0, raw)
    supported, total = parsed
    score = supported / total if total else None
    return FaithfulnessResult(score, supported, total, raw)
