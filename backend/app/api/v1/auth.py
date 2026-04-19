"""Auth endpoints — OIDC login flow + session + logout."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
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


def _login_error_redirect(settings: Any, reason: str) -> RedirectResponse:
    """Send the user back to the landing page with a friendly error query
    param, instead of leaving them on a blank "400 Bad Request"."""
    url = f"{settings.frontend_base_url}/?auth_error={reason}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """OIDC callback — validate, upsert user, issue session."""
    settings = get_settings()

    # Entra can redirect back with an error instead of a code (user cancelled,
    # consent denied, AADSTS flakiness). Surface that cleanly.
    if error:
        log.warning("OIDC callback error from IdP: %s — %s", error, error_description)
        return _login_error_redirect(settings, "idp_error")

    if not code or not state:
        log.warning("OIDC callback missing code or state")
        return _login_error_redirect(settings, "missing_params")

    stored_state = request.cookies.get("co_oidc_state")
    if stored_state is None:
        # Cookie was dropped. Most common cause: user's browser blocked
        # third-party cookies during the cross-site redirect, or the state
        # cookie expired (10 min TTL). Don't hang them on 400; send them
        # back to retry.
        log.warning("OIDC callback: co_oidc_state cookie missing")
        return _login_error_redirect(settings, "session_lost")
    if stored_state != state:
        log.warning("OIDC callback: state mismatch")
        return _login_error_redirect(settings, "state_mismatch")

    stored_nonce = request.cookies.get("co_oidc_nonce")
    post_login_redirect = request.cookies.get("co_post_login_redirect") or f"{settings.frontend_base_url}/feed"

    oidc = get_oidc_client()
    redirect_uri = f"{settings.api_base_url}/api/v1/auth/callback"
    try:
        tokens = await oidc.exchange_code(code=code, redirect_uri=redirect_uri)
    except Exception:
        log.exception("OIDC code exchange failed")
        return _login_error_redirect(settings, "token_exchange_failed")

    id_token = tokens.get("id_token")
    if not id_token:
        log.warning("OIDC callback: no id_token in token response")
        return _login_error_redirect(settings, "no_id_token")

    try:
        claims = await oidc.verify_id_token(id_token=id_token, expected_nonce=stored_nonce)
    except Exception:
        log.exception("OIDC id_token verification failed")
        return _login_error_redirect(settings, "token_invalid")

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
async def session(user: OptionalCurrentUser, response: Response) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    # total_analyses = only status='done' — matches the public profile stat
    # (failed / in-progress don't count toward the idea counter).
    row = await fetchrow(
        """SELECT u.id, u.external_id, u.email, u.username, u.display_name,
                  u.avatar_url, u.avatar_kind, u.avatar_seed, u.timezone,
                  u.default_visibility,
                  u.current_streak, u.longest_streak, u.fires_received,
                  COALESCE(cnt.n, 0)::int AS total_analyses
             FROM users u
        LEFT JOIN (
                  SELECT owner_id, COUNT(*) AS n
                    FROM analyses
                   WHERE status = 'done'
                   GROUP BY owner_id
             ) cnt ON cnt.owner_id = u.id
            WHERE u.id = $1::uuid""",
        user.id,
    )
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    data = dict(row)
    data["id"] = str(data["id"])
    data["onboarding_complete"] = bool(data.get("username"))

    # Self-heal: if the cookie is stale (cookie.username != db.username),
    # mint a fresh cookie so subsequent requests don't need the DB fallback.
    if user.session.username != row["username"]:
        token, _ = create_session_cookie(
            user_id=user.id,
            external_id=user.external_id,
            username=row["username"],
        )
        _set_session_cookie(response, token)

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
