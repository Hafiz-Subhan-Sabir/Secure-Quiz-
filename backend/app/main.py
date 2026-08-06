from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.modules.auth.router import router as auth_router
from app.modules.exams.router import router as exams_router
from app.modules.reports.router import router as reports_router
from app.modules.schemas import HealthResponse
from app.modules.sessions.router import router as sessions_router
from app.modules.sync.router import router as sync_router
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_if_empty()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def timing_and_security_headers(request: Request, call_next):
        started = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.endswith("/health"):
            response.headers["Cache-Control"] = "no-store"
        return response

    api = settings.api_prefix

    @app.get(f"{api}/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)

    app.include_router(auth_router, prefix=api)
    app.include_router(exams_router, prefix=api)
    app.include_router(sessions_router, prefix=api)
    app.include_router(sync_router, prefix=api)
    app.include_router(reports_router, prefix=api)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    run()
