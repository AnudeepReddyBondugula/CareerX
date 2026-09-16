"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from careerx import __version__
from careerx.api.dependencies import AppState
from careerx.api.errors import register_exception_handlers
from careerx.api.routes import generation, system
from careerx.config.logging import setup_logging
from careerx.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

DESCRIPTION = """\
CareerX turns a candidate's complete profile and a job posting into an
ATS-optimised, LaTeX-typeset resume.

The pipeline chunks the profile into atomic evidence, embeds it into a FAISS
index, retrieves the evidence most relevant to each requirement in the posting,
and generates the resume from that evidence. Every generated resume is then
checked against the source profile, and any employer, project, skill or metric
that does not appear there is removed before rendering.
"""


def static_dir() -> Path:
    return Path(str(resources.files("careerx.api") / "static"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the artifact sweeper and warm the provider."""
    state: AppState = app.state.careerx

    # Warm the provider and embedding backend in the background so the first
    # real request does not pay for a dimension probe or a model load. This is
    # deliberately not awaited: on a free tier the platform's health check must
    # succeed promptly, and the warm-up talks to a third-party API that may be
    # slow or down. Until it finishes, /readyz reports the service as not ready.
    warmup = asyncio.create_task(asyncio.to_thread(state.try_build_service))
    sweeper = asyncio.create_task(_sweep_forever(state))

    try:
        yield
    finally:
        for task in (warmup, sweeper):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def _sweep_forever(state: AppState) -> None:
    """Delete expired runs on a fixed interval for the life of the process."""
    interval = state.settings.artifact_sweep_interval_seconds

    while True:
        try:
            await asyncio.sleep(interval)
            await asyncio.to_thread(state.artifacts.sweep)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the sweeper must never die
            logger.exception("Artifact sweep failed; continuing.")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application."""
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        root_path=settings.root_path,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.state.careerx = AppState(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Tag every request with an id and log how long it took."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)

        response.headers["x-request-id"] = request_id

        if request.url.path not in {"/healthz", "/readyz"}:
            logger.info(
                "%s %s -> %s in %sms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={"request_id": request_id, "duration_ms": duration_ms},
            )

        return response

    register_exception_handlers(app)

    app.include_router(system.router)
    app.include_router(generation.router)

    assets = static_dir()
    if assets.is_dir():
        app.mount("/static", StaticFiles(directory=assets), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(assets / "index.html")

    return app


app = create_app()
