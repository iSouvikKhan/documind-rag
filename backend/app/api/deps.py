from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.container import Services
from app.db.repository import DocumentRepository
from app.ingestion.service import IngestionService
from app.rag.chat import ChatService


def get_services(request: Request) -> Services:
    return request.app.state.services


def _unavailable(services: Services) -> HTTPException:
    reason = "; ".join(services.errors) or "Service is not ready"
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=reason)


def get_repository(request: Request) -> DocumentRepository:
    services = get_services(request)
    if services.repository is None:
        raise _unavailable(services)
    return services.repository


def get_ingestion(request: Request) -> IngestionService:
    services = get_services(request)
    if services.ingestion is None:
        raise _unavailable(services)
    return services.ingestion


def get_chat(request: Request) -> ChatService:
    services = get_services(request)
    if services.chat is None:
        raise _unavailable(services)
    return services.chat
