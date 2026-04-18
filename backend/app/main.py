from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router
from app.api.telemetry import router as telemetry_router
from app.config import get_settings
from app.storage.db import close_pool, ensure_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_schema()
        logging.info("Postgres connected — reports will be persisted.")
    except Exception as e:  # noqa: BLE001
        logging.warning(
            "Postgres unavailable — running in memory-only mode. (%s)", type(e).__name__
        )
    yield
    try:
        await close_pool()
    except Exception:
        pass


app = FastAPI(title="Startup Analyzer", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(telemetry_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
