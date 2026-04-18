from __future__ import annotations

import logging

import redis.asyncio as redis

from app.config import get_settings

log = logging.getLogger(__name__)

_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
