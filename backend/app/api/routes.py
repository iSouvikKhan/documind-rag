from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat, get_ingestion, get_repository, get_services
from app.api.schemas import (
    COLLECTION_PATTERN,
    ChatRequest,
    ChatResponse,
    DocumentOut,
    ErrorOut,
    HealthOut,
    ProviderInfo,
)
from app.container import Services
from app.db.repository import DocumentRepository
from app.ingestion.parsers import IngestionError
from app.ingestion.service import DuplicateDocumentError, FileTooLargeError, IngestionService
from app.rag.chat import ChatService
from app.rag.citations import to_sources
from app.rag.prompts import ChatTurn
from app.rag.sse import format_sse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

READ_CHUNK = 1024 * 1024


@router.get("/health", response_model=HealthOut, tags=["system"])
def health(services: Services = Depends(get_services)) -> HealthOut:
    s = services.settings
    db_ok = False
    if services.repository is not None:
        try:
            db_ok = bool(services.repository.ping())
        except Exception as exc:
            logger.warning("Health check database ping failed: %s", exc)
    return HealthOut(
        status="ok" if services.ready and db_ok else "degraded",
        database=db_ok,
        llm=ProviderInfo(provider=s.llm_provider, model=s.resolved_llm_model),
        embeddings=ProviderInfo(provider=s.embedding_provider, model=s.resolved_embedding_model),
        embedding_dim=s.embedding_dim,
        reranker=s.reranker if s.reranker == "none" else f"flashrank:{s.reranker_model}",
        errors=services.errors,
    )


@router.get("/documents", response_model=list[DocumentOut], tags=["documents"])
def list_documents(
    collection: str = Query("default", pattern=COLLECTION_PATTERN),
    repository: DocumentRepository = Depends(get_repository),
) -> list[DocumentOut]:
    return [DocumentOut(**asdict(d)) for d in repository.list_documents(collection)]


@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorOut}, 409: {"model": ErrorOut}, 413: {"model": ErrorOut}},
    tags=["documents"],
)
def upload_document(
    file: UploadFile = File(..., description="PDF or DOCX file"),
    collection: str = Query("default", pattern=COLLECTION_PATTERN),
    ingestion: IngestionService = Depends(get_ingestion),
) -> DocumentOut:
    # Read at most limit + 1 bytes so oversized uploads are rejected without buffering them.
    limit = ingestion.max_upload_bytes
    buffer = bytearray()
    while chunk := file.file.read(READ_CHUNK):
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise HTTPException(413, f"File exceeds the {limit // 1_048_576} MB upload limit")

    try:
        document = ingestion.ingest(file.filename or "", bytes(buffer), collection)
    except DuplicateDocumentError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except FileTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return DocumentOut(**asdict(document))


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    responses={404: {"model": ErrorOut}},
    tags=["documents"],
)
def get_document(
    document_id: UUID, repository: DocumentRepository = Depends(get_repository)
) -> DocumentOut:
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentOut(**asdict(document))


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorOut}},
    tags=["documents"],
)
def delete_document(
    document_id: UUID, repository: DocumentRepository = Depends(get_repository)
) -> None:
    if not repository.delete_document(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


@router.post("/chat/stream", tags=["chat"])
async def chat_stream(
    body: ChatRequest, request: Request, chat: ChatService = Depends(get_chat)
) -> StreamingResponse:
    """Stream an answer as Server-Sent Events.

    Events: ``sources`` (retrieved chunks, sent first), ``token`` (answer text deltas),
    ``done`` (cited source numbers) or ``error``.
    """
    history = [ChatTurn(t.role, t.content) for t in body.history]

    async def events() -> AsyncIterator[str]:
        async for event in chat.stream(body.question, body.collection, history):
            if await request.is_disconnected():
                logger.info("Client disconnected, stopping stream")
                return
            yield format_sse(event.event, event.data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat_once(body: ChatRequest, chat: ChatService = Depends(get_chat)) -> ChatResponse:
    """Non-streaming answer, convenient for scripts and curl."""
    try:
        answer = await chat.answer(body.question, body.collection)
    except Exception as exc:
        logger.exception("Chat failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Answer generation failed: {exc}"
        ) from exc
    return ChatResponse(answer=answer.text, sources=to_sources(answer.chunks), cited=answer.cited)
