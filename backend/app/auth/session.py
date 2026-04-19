"""Session cookies — Fernet-encrypted opaque blobs.

Cookie payload:
  {user_id: UUID, external_id: str, username: str|null, issued_at: iso8601, expires_at: iso8601}

The key is the 'session-encryption-key' Key Vault secret. If `SESSION_ENCRYPTION_KEY`
contains multiple base64 fernet keys comma-separated, we MultiFernet them so old
keys can decrypt old cookies during a rolling rotation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, MultiFernet

from app.config import get_settings

log = logging.getLogger(__name__)

# Sessions live effectively forever ("until logged out" per product spec).
# 365 days keeps the cookie max-age within the RFC 6265 practical bounds
# while meaning the user never gets silently signed out. On every /session
# call we re-issue the cookie with a fresh 365-day window (sliding), so
# active users rotate their expiry continuously.
SESSION_LIFETIME = timedelta(days=365)
# Re-issue a fresh cookie when less than this much time is left, so active
# users never drop below a near-full lifetime window.
SESSION_SLIDING_THRESHOLD = timedelta(days=7)
COOKIE_NAME = "co_session"


@dataclass
class SessionCookie:
    user_id: str
    external_id: str
    username: str | None
    issued_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


def _fernet() -> MultiFernet:
    settings = get_settings()
    raw = settings.session_encryption_key
    if not raw:
        raise RuntimeError("SESSION_ENCRYPTION_KEY is required")
    keys = [Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("No valid Fernet keys in SESSION_ENCRYPTION_KEY")
    return MultiFernet(keys)


def create_session_cookie(*, user_id: str, external_id: str, username: str | None) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + SESSION_LIFETIME
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "external_id": external_id,
        "username": username,
        "issued_at": now.isoformat(),
        "expires_at": exp.isoformat(),
    }
    token = _fernet().encrypt(json.dumps(payload).encode())
    return token.decode(), exp


def decrypt_session_cookie(token: str) -> SessionCookie | None:
    try:
        plain = _fernet().decrypt(token.encode())
    except Exception as e:  # noqa: BLE001
        log.debug("session cookie decrypt failed: %s", type(e).__name__)
        return None
    try:
        payload = json.loads(plain)
        cookie = SessionCookie(
            user_id=payload["user_id"],
            external_id=payload["external_id"],
            username=payload.get("username"),
            issued_at=datetime.fromisoformat(payload["issued_at"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
        )
    except (KeyError, ValueError, TypeError):
        return None
    if cookie.is_expired():
        return None
    return cookie
