from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analysis import router as analysis_router
from app.api.telemetry import router as telemetry_router
from app.api.v1.analyses import router as analyses_router_v1
from app.api.v1.auth import router as auth_router_v1
from app.api.v1.social import feed_router as feed_router_v1
from app.api.v1.social import notif_router as notif_router_v1
from app.api.v1.users import router as users_router_v1
from app.config import get_settings
from app.db.pool import close_pool, get_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await get_pool()
        logging.info("Postgres connected — users + all features enabled.")
    except Exception as e:  # noqa: BLE001
        logging.warning(
            "Postgres unavailable — running without DB features. (%s)",
            type(e).__name__,
        )
    yield
    try:
        await close_pool()
    except Exception:
        pass


app = FastAPI(title="Chapter One API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler — log the full traceback and ensure the 500
# response carries CORS headers so the browser doesn't mask the real error
# as "CORS: No 'Access-Control-Allow-Origin' header".
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.error(
        "Unhandled exception on %s %s:\n%s",
        request.method, request.url.path,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    origin = request.headers.get("origin", "")
    allowed = origin if origin in settings.cors_origin_list else ""
    headers = {}
    if allowed:
        headers["Access-Control-Allow-Origin"] = allowed
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=500,
        content={"detail": "internal_error", "error": type(exc).__name__, "message": str(exc)[:300]},
        headers=headers,
    )

# v1 — new auth + users + analyses + social
app.include_router(auth_router_v1)
app.include_router(users_router_v1)
app.include_router(analyses_router_v1)
app.include_router(feed_router_v1)
app.include_router(notif_router_v1)

# Legacy (Phase 1) — will be migrated in M2
app.include_router(analysis_router)
app.include_router(telemetry_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
