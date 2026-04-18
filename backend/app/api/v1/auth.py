"""Auth endpoints — OIDC login flow + session + logout."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import OptionalCurrentUser
from app.auth.oidc import get_oidc_client
from app.auth.session import COOKIE_NAME, SESSION_LIFETIME, create_session_cookie
from app.config import get_settings
from app.db import fetchrow, transaction

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _is_deployed() -> bool:
    """True when running on Azure (dev or prod); False in local dev on http://localhost."""
    import os
    env = os.environ.get("CHAPTER_ONE_ENV", "").lower()
    return env in {"dev", "prod"}


def _cross_site_mode() -> bool:
    """True when the frontend and API are on different origins.

    In our Azure deploy the frontend lives on *.azurestaticapps.net and the
    API on *.azurecontainerapps.io — always cross-site. Locally, both are on
    localhost and same-site. This decides the SameSite/Secure cookie profile.
    """
    settings = get_settings()
    try:
        from urllib.parse import urlparse
        return urlparse(settings.frontend_base_url).netloc != urlparse(settings.api_base_url).netloc
    except Exception:
        return _is_deployed()


def _cookie_profile() -> dict:
    """Return the right SameSite / Secure combo for this environment."""
    if _cross_site_mode():
        # Cross-site: SameSite=None requires Secure (HTTPS-only). Browsers reject
        # SameSite=None cookies without Secure, even on HTTPS.
        return {"samesite": "none", "secure": True}
    # Same-site / local dev over HTTP: Lax is fine; Secure optional.
    return {"samesite": "lax", "secure": _is_deployed()}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        **_cookie_profile(),
    )


@router.get("/login")
async def login(redirect: str | None = None) -> RedirectResponse:
    """Kick off OIDC flow; sends the user to the Entra authorize endpoint."""
    settings = get_settings()
    oidc = get_oidc_client()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    # State/nonce stored in short-lived cookies (not sessions) so the callback can verify them.
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/callback"
    url = await oidc.authorization_url(redirect_uri=redirect_uri, state=state, nonce=nonce)

    final_redirect = redirect or f"{settings.frontend_base_url}/feed"
    resp = RedirectResponse(url=url, status_code=302)
    cp = _cookie_profile()
    resp.set_cookie("co_oidc_state", state, httponly=True, max_age=600, **cp)
    resp.set_cookie("co_oidc_nonce", nonce, httponly=True, max_age=600, **cp)
    resp.set_cookie("co_post_login_redirect", final_redirect, httponly=True, max_age=600, **cp)
    return resp


@router.get("/callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    """OIDC callback — validate, upsert user, issue session."""
    settings = get_settings()

    stored_state = request.cookies.get("co_oidc_state")
    if stored_state is None or stored_state != state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_state")

    stored_nonce = request.cookies.get("co_oidc_nonce")
    post_login_redirect = request.cookies.get("co_post_login_redirect") or f"{settings.frontend_base_url}/feed"

    oidc = get_oidc_client()
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/callback"
    tokens = await oidc.exchange_code(code=code, redirect_uri=redirect_uri)
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no id_token in response")

    claims = await oidc.verify_id_token(id_token=id_token, expected_nonce=stored_nonce)

    user = await _upsert_user_from_claims(
        external_id=claims.sub,
        email=claims.email,
        name=claims.name,
    )

    token, _ = create_session_cookie(
        user_id=str(user["id"]),
        external_id=user["external_id"],
        username=user.get("username"),
    )

    # Decide where to send them based on onboarding completeness
    needs_onboarding = not user.get("username")
    target = f"{settings.frontend_base_url}/onboarding" if needs_onboarding else post_login_redirect

    resp = RedirectResponse(url=target, status_code=302)
    _set_session_cookie(resp, token)
    # Clear OIDC transient cookies
    for c in ("co_oidc_state", "co_oidc_nonce", "co_post_login_redirect"):
        resp.delete_cookie(c, path="/")
    return resp


@router.get("/session")
async def session(user: OptionalCurrentUser) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    row = await fetchrow(
        """SELECT id, external_id, email, username, display_name, avatar_url, avatar_kind,
                  avatar_seed, timezone, default_visibility, total_analyses,
                  current_streak, longest_streak, fires_received
             FROM users WHERE id = $1::uuid""",
        user.id,
    )
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    data = dict(row)
    data["id"] = str(data["id"])
    data["onboarding_complete"] = bool(data.get("username"))
    return {"user": data}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "logged_out"}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

async def _upsert_user_from_claims(
    *, external_id: str, email: str, name: str | None,
) -> dict[str, Any]:
    async with transaction() as conn:
        row = await conn.fetchrow(
            """SELECT id, external_id, email, username, display_name
                 FROM users WHERE external_id = $1""",
            external_id,
        )
        if row:
            return dict(row)
        # First-time sign-in: insert minimal record. Username is null until onboarding.
        # display_name defaults to the OIDC `name` claim or email local-part.
        display_name = (name or email.split("@", 1)[0])[:40]
        inserted = await conn.fetchrow(
            """INSERT INTO users (external_id, email, display_name, avatar_kind, username)
                 VALUES ($1, $2, $3, 'initials', NULL)
                 RETURNING id, external_id, email, username, display_name""",
            external_id, email, display_name,
        )
        return dict(inserted)
