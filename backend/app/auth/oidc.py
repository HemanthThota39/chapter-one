"""Entra External ID OIDC client.

We use Authlib for the OAuth2 client + JWT validation. All tenant/client
config is loaded from settings; at runtime, JWKs are fetched from the
tenant's well-known endpoint and cached.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class OidcClaims:
    sub: str            # user subject (our external_id)
    email: str
    name: str | None
    picture: str | None
    raw: dict[str, Any]


class OidcClient:
    """Single OIDC client against Entra External ID. One per env."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._jwks: PyJWKClient | None = None
        self._jwks_url: str | None = None
        self._config: dict[str, Any] | None = None
        self._config_expires = 0
        self._config_lock = asyncio.Lock()

    async def _discovery(self) -> dict[str, Any]:
        now = time.time()
        if self._config and now < self._config_expires:
            return self._config
        async with self._config_lock:
            if self._config and time.time() < self._config_expires:
                return self._config
            settings = self._settings
            if not settings.entra_tenant_id:
                raise RuntimeError("ENTRA_TENANT_ID not configured")
            # Entra External ID uses ciamlogin.com; format below is standard.
            url = (
                f"https://{settings.entra_tenant_subdomain}.ciamlogin.com/"
                f"{settings.entra_tenant_id}/v2.0/.well-known/openid-configuration"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                self._config = resp.json()
            self._jwks_url = self._config.get("jwks_uri")
            self._config_expires = time.time() + 3600
            return self._config

    async def authorization_url(self, redirect_uri: str, state: str, nonce: str) -> str:
        from urllib.parse import urlencode

        cfg = await self._discovery()
        auth_endpoint = cfg["authorization_endpoint"]
        params = {
            "client_id": self._settings.entra_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "openid email profile offline_access",
            "state": state,
            "nonce": nonce,
        }
        return f"{auth_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        cfg = await self._discovery()
        token_endpoint = cfg["token_endpoint"]
        data = {
            "client_id": self._settings.entra_client_id,
            "client_secret": self._settings.entra_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_endpoint, data=data)
            resp.raise_for_status()
            return resp.json()

    async def verify_id_token(self, id_token: str, expected_nonce: str | None = None) -> OidcClaims:
        cfg = await self._discovery()
        if not self._jwks_url:
            raise RuntimeError("JWKS URL not discovered")
        jwks_client = PyJWKClient(self._jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        try:
            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._settings.entra_client_id,
                issuer=cfg.get("issuer"),
                options={"require": ["exp", "iat", "sub", "aud"]},
            )
        except jwt.InvalidTokenError as e:
            log.warning("id_token validation failed: %s", e)
            raise

        if expected_nonce and payload.get("nonce") != expected_nonce:
            raise ValueError("nonce mismatch")

        return OidcClaims(
            sub=str(payload["sub"]),
            email=str(payload.get("email") or payload.get("preferred_username") or ""),
            name=payload.get("name"),
            picture=payload.get("picture"),
            raw=payload,
        )


_client: OidcClient | None = None


def get_oidc_client() -> OidcClient:
    global _client
    if _client is None:
        _client = OidcClient()
    return _client
