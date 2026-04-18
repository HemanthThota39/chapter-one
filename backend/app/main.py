from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.telemetry import router as telemetry_router
from app.api.v1.auth import router as auth_router_v1
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

# v1 — new auth + users
app.include_router(auth_router_v1)
app.include_router(users_router_v1)

# Legacy (Phase 1) — will be migrated in M2
app.include_router(analysis_router)
app.include_router(telemetry_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
