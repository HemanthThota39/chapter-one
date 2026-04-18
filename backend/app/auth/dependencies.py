"""FastAPI dependencies for authentication.

Usage:
    @router.get("/me")
    async def me(user: CurrentUser) -> dict:
        return {"id": user.id, ...}

CurrentUser raises 401 if not authenticated. For optional auth use
get_current_user_optional which returns None instead of raising.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status  # noqa: F401 (Depends used via Annotated)

from app.auth.session import COOKIE_NAME, SessionCookie, decrypt_session_cookie

log = logging.getLogger(__name__)


@dataclass
class CurrentUserData:
    id: str
    external_id: str
    username: str | None
    session: SessionCookie


async def get_current_user_optional(
    co_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> CurrentUserData | None:
    if not co_session:
        return None
    cookie = decrypt_session_cookie(co_session)
    if cookie is None:
        return None

    username = cookie.username
    # Lazy reconciliation: if the cookie was minted before onboarding
    # completed, pull the current username from the DB so downstream
    # endpoints (e.g. POST /analyses) see the correct state without
    # requiring the user to log out + back in.
    if username is None:
        try:
            from app.db import fetchrow
            row = await fetchrow(
                "SELECT username FROM users WHERE id = $1::uuid",
                cookie.user_id,
            )
            if row and row["username"]:
                username = row["username"]
        except Exception:  # noqa: BLE001
            log.exception("failed to reconcile username from DB; falling back to cookie")

    return CurrentUserData(
        id=cookie.user_id,
        external_id=cookie.external_id,
        username=username,
        session=cookie,
    )


async def get_current_user(
    user: Annotated[CurrentUserData | None, Depends(get_current_user_optional)],
) -> CurrentUserData:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return user


CurrentUser = Annotated[CurrentUserData, Depends(get_current_user)]
OptionalCurrentUser = Annotated[CurrentUserData | None, Depends(get_current_user_optional)]
