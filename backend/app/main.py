"""DocuMind API.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, get_settings
from app.container import Services, build_services

logger = logging.getLogger("documind")


def create_app(
    settings: Settings | None = None,
    services_factory: Callable[[Settings], Services] = build_services,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services_factory(settings)
        try:
            yield
        finally:
            app.state.services.close()

    app = FastAPI(
        title="DocuMind API",
        version="1.0.0",
        description="RAG over PDF and DOCX documents with hybrid retrieval and cited answers.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    app.include_router(router)
    return app


app = create_app()
