from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aftermath.adapters.persistence.database import PostgresProbe
from aftermath.application.health import readiness
from aftermath.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = PostgresProbe(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        database.close()

    app = FastAPI(title="AFTERMATH foundation", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
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
