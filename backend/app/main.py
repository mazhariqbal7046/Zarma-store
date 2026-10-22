import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.settings import settings
from app.api import router as api_router
from app.logging_config import configure_logging, metrics_snapshot, record_request, request_id_context
from app.supabase_rest import close_http_client

configure_logging()
logger = logging.getLogger("zarma.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_http_client()


app = FastAPI(title="Zarma Store API", version="0.1.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Idempotency-Key"],
)

app.include_router(api_router)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = str(uuid.uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record_request(status_code=status_code, duration_ms=duration_ms)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        logger.info(
            "request_complete",
            extra={
                "method": request.method,
                "route": route,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
        request_id_context.reset(token)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """Return a safe error while logging only non-sensitive diagnostics."""

    logger.error(
        "unhandled_request",
        extra={"method": request.method, "route": "unmatched", "exception_type": type(exc).__name__},
    )
    response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-ID"] = request_id_context.get()
    return response


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zarma-store-api"}


@app.get("/api/v1/config", tags=["system"])
def public_config() -> dict[str, str]:
    return {"currency": settings.currency, "commission_rate": str(settings.commission_rate)}


@app.get("/metrics", tags=["system"])
def metrics(request: Request) -> dict:
    """Expose aggregate metrics only when a monitoring token is configured."""

    if not settings.metrics_token or request.headers.get("X-Metrics-Token") != settings.metrics_token:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return metrics_snapshot()
