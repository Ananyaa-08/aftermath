from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aftermath.adapters.archive.files import FileAnswerArchive
from aftermath.adapters.persistence.corpus import PostgresCorpusStore
from aftermath.adapters.persistence.database import PostgresProbe
from aftermath.adapters.providers.gemini import GeminiAnswerProvider
from aftermath.adapters.storage.local import LocalObjectStore
from aftermath.api.corpus import corpus_router
from aftermath.api.limits import BodyLimitMiddleware
from aftermath.application.answers import AnswerService
from aftermath.application.corpus import CorpusService
from aftermath.application.health import readiness
from aftermath.config import Settings
from aftermath.core.errors import DomainError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = PostgresProbe(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        database.close()

    app = FastAPI(title="AFTERMATH corpus storage", lifespan=lifespan)
    store = PostgresCorpusStore(database.engine)
    service = CorpusService(
        store,
        LocalObjectStore(settings.data_dir),
        settings.max_source_bytes,
        settings.max_corpus_versions,
        settings.max_passages_per_document,
        settings.max_passage_length,
        settings.max_alignment_candidate_pairs,
        settings.max_timeline_breakpoints,
        settings.max_documents_per_delivery,
    )
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
    provider = GeminiAnswerProvider(key) if key else None
    answering = AnswerService(
        store,
        service,
        provider,
        FileAnswerArchive(settings.data_dir),
        settings.max_source_bytes,
        settings.force_fallback,
    )
    app.include_router(corpus_router(service, answering, settings))
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "Request failed validation",
                    "fields": [".".join(map(str, item["loc"])) for item in error.errors()],
                }
            },
            status_code=422,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization"],
        allow_credentials=False,
    )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        available = readiness(database)
        return JSONResponse(
            status_code=200 if available else 503,
            content={
                "status": "ready" if available else "unavailable",
                "dependencies": {"postgresql": "ready" if available else "unavailable"},
            },
        )

    return app
