"""Evaluate retrieval accuracy and answer faithfulness across chunking and prompt settings.

For every chunking config the sample corpus is ingested into its own collection
(``eval_<name>``). Each question is retrieved once per chunking config, then answered with
every prompt style. Results are written as JSON and Markdown.

Usage (from backend/, with PostgreSQL and the model provider running)::

    python -m app.evaluation.run
    python -m app.evaluation.run --limit 5 --prompts grounded
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings, get_settings
from app.container import retrieval_config
from app.db.pool import create_pool
from app.db.repository import PostgresRepository
from app.db.schema import ensure_schema
from app.evaluation.judge import judge_faithfulness
from app.evaluation.metrics import (
    EvalItem,
    document_hit,
    hit_at_k,
    is_refusal,
    keyword_recall,
    reciprocal_rank,
    safe_mean,
)
from app.ingestion.service import ChunkingConfig, IngestionService
from app.providers import build_chat_model, build_embeddings
from app.rag.chat import ChatService
from app.rag.prompts import format_context
from app.retrieval.reranker import build_reranker
from app.retrieval.retriever import HybridRetriever

logger = logging.getLogger("documind.eval")

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"


@dataclass
class ItemResult:
    item_id: str
    chunking: str
    prompt_style: str
    answerable: bool
    hit_at_k: float | None
    reciprocal_rank: float | None
    document_hit: float | None
    faithfulness: float | None
    keyword_recall: float | None
    refused: bool
    answer: str
    retrieved: list[str]


def load_dataset(path: Path) -> list[EvalItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [EvalItem(**item) for item in raw["items"]]


def summarize(results: list[ItemResult]) -> list[dict]:
    groups: dict[tuple[str, str], list[ItemResult]] = {}
    for r in results:
        groups.setdefault((r.chunking, r.prompt_style), []).append(r)
    rows = []
    for (chunking, style), items in groups.items():
        answerable = [r for r in items if r.answerable]
        unanswerable = [r for r in items if not r.answerable]
        rows.append(
            {
                "chunking": chunking,
                "prompt_style": style,
                "questions": len(items),
                "hit_at_k": safe_mean(r.hit_at_k for r in answerable),
                "mrr": safe_mean(r.reciprocal_rank for r in answerable),
                "document_hit": safe_mean(r.document_hit for r in answerable),
                "faithfulness": safe_mean(r.faithfulness for r in items),
                "keyword_recall": safe_mean(r.keyword_recall for r in answerable),
                "false_refusal_rate": safe_mean(float(r.refused) for r in answerable),
                "unanswerable_refusal_rate": safe_mean(float(r.refused) for r in unanswerable),
            }
        )
    return rows


def render_markdown(rows: list[dict], meta: dict) -> str:
    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.3f}"

    lines = [
        "# DocuMind evaluation",
        "",
        f"- Run at: {meta['run_at']}",
        f"- LLM: {meta['llm']} · Embeddings: {meta['embeddings']} · Re-ranker: {meta['reranker']}",
        f"- Judge: {meta['judge']} · top_k: {meta['top_k']} · questions: {meta['questions']}",
        "",
        "| Chunking | Prompt | Hit@k | MRR | Doc hit | Faithfulness | Keyword recall "
        "| False refusals | Refused unanswerable |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['chunking']} | {r['prompt_style']} | {fmt(r['hit_at_k'])} | {fmt(r['mrr'])} | "
            f"{fmt(r['document_hit'])} | {fmt(r['faithfulness'])} | {fmt(r['keyword_recall'])} | "
            f"{fmt(r['false_refusal_rate'])} | {fmt(r['unanswerable_refusal_rate'])} |"
        )
    return "\n".join(lines) + "\n"


async def evaluate(
    settings: Settings,
    items: list[EvalItem],
    docs_dir: Path,
    chunkings: list[dict],
    prompt_styles: list[str],
    top_k: int,
    keep: bool,
) -> tuple[list[ItemResult], dict]:
    ensure_schema(settings.database_url, settings.embedding_dim, settings.db_connect_timeout)
    pool = create_pool(settings.database_url, 1, 4, settings.db_connect_timeout)
    repository = PostgresRepository(pool)
    embeddings = build_embeddings(settings)
    llm = build_chat_model(settings)
    judge = build_chat_model(settings, temperature=0.0)
    reranker = build_reranker(
        settings.reranker, settings.reranker_model, settings.reranker_cache_dir
    )
    retriever = HybridRetriever(repository, embeddings, reranker, retrieval_config(settings))
    chat = ChatService(retriever, llm)
    ingestion = IngestionService(
        repository,
        embeddings,
        settings.resolved_embedding_model,
        ChunkingConfig(settings.chunk_size, settings.chunk_overlap),
        settings.max_upload_bytes,
    )
    files = sorted(p for p in docs_dir.iterdir() if p.suffix.lower() in {".pdf", ".docx"})
    if not files:
        raise SystemExit(f"No PDF/DOCX files found in {docs_dir}")

    results: list[ItemResult] = []
    try:
        for cfg in chunkings:
            collection = f"eval_{cfg['name']}"
            repository.delete_collection(collection)
            chunking = ChunkingConfig(cfg["chunk_size"], cfg["chunk_overlap"])
            for f in files:
                ingestion.ingest(f.name, f.read_bytes(), collection, chunking)
            logger.info("Ingested %d files into %s", len(files), collection)

            for item in items:
                chunks = await asyncio.to_thread(
                    retriever.retrieve, item.question, collection, top_k
                )
                answerable = item.answerable
                for style in prompt_styles:
                    answer = await chat.generate(item.question, chunks, style)
                    refused = is_refusal(answer.text)
                    faith = None
                    if chunks and not refused:
                        judged = await judge_faithfulness(
                            judge, format_context(chunks), answer.text
                        )
                        faith = judged.score
                    results.append(
                        ItemResult(
                            item_id=item.id,
                            chunking=cfg["name"],
                            prompt_style=style,
                            answerable=answerable,
                            hit_at_k=hit_at_k(chunks, item, top_k) if answerable else None,
                            reciprocal_rank=reciprocal_rank(chunks, item) if answerable else None,
                            document_hit=document_hit(chunks, item) if answerable else None,
                            faithfulness=faith,
                            keyword_recall=keyword_recall(answer.text, item.answer_keywords),
                            refused=refused,
                            answer=answer.text,
                            retrieved=[f"{c.filename}#{c.chunk_index}" for c in chunks],
                        )
                    )
                    logger.info(
                        "[%s/%s] %s hit=%s faith=%s refused=%s",
                        cfg["name"],
                        style,
                        item.id,
                        results[-1].hit_at_k,
                        faith,
                        refused,
                    )
            if not keep:
                repository.delete_collection(collection)
    finally:
        pool.close()

    meta = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "llm": f"{settings.llm_provider}:{settings.resolved_llm_model}",
        "embeddings": f"{settings.embedding_provider}:{settings.resolved_embedding_model}",
        "reranker": settings.reranker,
        "judge": f"{settings.llm_provider}:{settings.resolved_llm_model} (temperature 0)",
        "top_k": top_k,
        "questions": len(items),
    }
    return results, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DocuMind evaluation")
    parser.add_argument("--dataset", type=Path, default=EVAL_DIR / "dataset.json")
    parser.add_argument("--docs", type=Path, default=EVAL_DIR / "sample_docs")
    parser.add_argument("--configs", type=Path, default=EVAL_DIR / "configs.json")
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results")
    parser.add_argument("--prompts", nargs="+", help="Override prompt styles from the config")
    parser.add_argument("--limit", type=int, help="Only evaluate the first N questions")
    parser.add_argument("--keep", action="store_true", help="Keep eval_* collections afterwards")
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(message)s")

    items = load_dataset(args.dataset)[: args.limit]
    config = json.loads(args.configs.read_text(encoding="utf-8"))
    prompt_styles = args.prompts or config["prompt_styles"]

    results, meta = asyncio.run(
        evaluate(
            settings,
            items,
            args.docs,
            config["chunking"],
            prompt_styles,
            config["top_k"],
            args.keep,
        )
    )
    rows = summarize(results)

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out / f"eval_{stamp}.json"
    md_path = args.out / f"eval_{stamp}.md"
    json_path.write_text(
        json.dumps(
            {"meta": meta, "summary": rows, "items": [asdict(r) for r in results]}, indent=2
        ),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(rows, meta), encoding="utf-8")
    print(render_markdown(rows, meta))
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
