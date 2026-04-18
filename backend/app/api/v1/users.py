"""User endpoints — onboard, me, profile, delete."""

from __future__ import annotations

import io
import logging
import re
import secrets
from typing import Annotated, Any, Literal  # noqa: F401 (Any kept for JSON response typing hints)

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, constr

from app.auth.dependencies import CurrentUser
from app.auth.session import COOKIE_NAME
from app.config import get_settings
from app.db import fetchrow, transaction

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/users", tags=["users"])

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
RESERVED_USERNAMES = {
    "admin", "administrator", "root", "api", "auth", "login", "logout",
    "signup", "signin", "register", "help", "support", "about", "contact",
    "settings", "me", "u", "user", "users", "feed", "home", "chapterone",
    "chapter-one", "dev", "prod", "production", "www", "app",
}


class OnboardRequest(BaseModel):
    username: constr(pattern=r"^[a-z0-9_]{3,20}$") = Field(...)
    display_name: constr(strip_whitespace=True, min_length=1, max_length=40) = Field(...)
    avatar_kind: Literal["upload", "library", "initials"] = "initials"
    avatar_library_id: str | None = None  # e.g. "geo-07" when kind=library
    timezone: str = "Asia/Kolkata"


class UserMe(BaseModel):
    id: str
    external_id: str
    email: str
    username: str | None
    display_name: str
    avatar_url: str | None
    avatar_kind: str
    avatar_seed: str | None
    timezone: str
    default_visibility: str
    total_analyses: int
    current_streak: int
    longest_streak: int
    fires_received: int
    joined_at: str


class PublicProfile(BaseModel):
    username: str
    display_name: str
    avatar_url: str | None
    avatar_kind: str
    avatar_seed: str | None
    joined_at: str
    total_analyses: int
    current_streak: int
    longest_streak: int
    fires_received: int


# ---------------------------------------------------------------------
# POST /onboard
# ---------------------------------------------------------------------
@router.post("/onboard", status_code=status.HTTP_201_CREATED)
async def onboard(
    user: CurrentUser,
    username: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    avatar_kind: Annotated[Literal["upload", "library", "initials"], Form()] = "initials",
    avatar_library_id: Annotated[str | None, Form()] = None,
    timezone: Annotated[str, Form()] = "Asia/Kolkata",
    avatar_file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    username = username.lower().strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username_invalid")
    if username in RESERVED_USERNAMES:
        raise HTTPException(status.HTTP_409_CONFLICT, "username_reserved")

    display_name = display_name.strip()[:40]
    if not display_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "display_name_required")

    # Handle avatar by kind
    avatar_url: str | None = None
    avatar_seed: str | None = None

    if avatar_kind == "initials":
        avatar_seed = secrets.token_hex(4)  # deterministic color seed
    elif avatar_kind == "library":
        if not avatar_library_id or not re.match(r"^[a-z0-9\-]{1,32}$", avatar_library_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "avatar_library_id_invalid")
        settings = get_settings()
        avatar_url = f"{settings.blob_endpoint}{settings.blob_container_avatars}/library/{avatar_library_id}.webp"
    elif avatar_kind == "upload":
        if avatar_file is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "avatar_file_required_for_upload")
        avatar_url = await _process_and_upload_avatar(avatar_file, user_id=user.id)

    async with transaction() as conn:
        # Pre-check: onboarding is once-and-only-once. ADR-022 usernames are immutable.
        existing = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1::uuid",
            user.id,
        )
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
        if existing["username"]:
            # Already onboarded — don't let a stale client silently overwrite.
            raise HTTPException(status.HTTP_409_CONFLICT, "already_onboarded")

        # Race-safe uniqueness via the UNIQUE constraint on username (CITEXT)
        try:
            row = await conn.fetchrow(
                """UPDATE users
                      SET username = $2,
                          display_name = $3,
                          avatar_kind = $4,
                          avatar_url = $5,
                          avatar_seed = $6,
                          timezone = $7,
                          updated_at = NOW()
                    WHERE id = $1::uuid AND username IS NULL
                RETURNING id, external_id, email, username, display_name, avatar_url,
                          avatar_kind, avatar_seed, timezone, default_visibility,
                          total_analyses, current_streak, longest_streak,
                          fires_received, created_at""",
                user.id, username, display_name, avatar_kind, avatar_url, avatar_seed, timezone,
            )
        except Exception as e:
            msg = str(e).lower()
            if "unique" in msg and "username" in msg:
                raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
            raise

        if row is None:
            # Another concurrent request onboarded us between the SELECT and UPDATE.
            raise HTTPException(status.HTTP_409_CONFLICT, "already_onboarded")

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    data = dict(row)
    data["id"] = str(data["id"])
    data["joined_at"] = data.pop("created_at").isoformat()
    return {"user": data}


# ---------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------
@router.get("/me")
async def me(user: CurrentUser) -> dict[str, Any]:
    row = await fetchrow(
        """SELECT id, external_id, email, username, display_name, avatar_url,
                  avatar_kind, avatar_seed, timezone, default_visibility,
                  total_analyses, current_streak, longest_streak, fires_received,
                  created_at
             FROM users WHERE id = $1::uuid""",
        user.id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    data = dict(row)
    data["id"] = str(data["id"])
    data["joined_at"] = data.pop("created_at").isoformat()
    return {"user": data}


# ---------------------------------------------------------------------
# PATCH /me
# ---------------------------------------------------------------------
class PatchMeRequest(BaseModel):
    display_name: constr(strip_whitespace=True, min_length=1, max_length=40) | None = None
    timezone: str | None = None
    default_visibility: Literal["public", "private"] | None = None


@router.patch("/me")
async def patch_me(user: CurrentUser, req: PatchMeRequest) -> dict[str, Any]:
    updates: list[str] = []
    params: list[Any] = [user.id]
    n = 1
    if req.display_name is not None:
        n += 1
        updates.append(f"display_name = ${n}")
        params.append(req.display_name)
    if req.timezone is not None:
        n += 1
        updates.append(f"timezone = ${n}")
        params.append(req.timezone)
    if req.default_visibility is not None:
        n += 1
        updates.append(f"default_visibility = ${n}")
        params.append(req.default_visibility)
    if not updates:
        return await me(user)
    updates.append("updated_at = NOW()")
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id = $1::uuid"
    async with transaction() as conn:
        await conn.execute(sql, *params)
    return await me(user)


# ---------------------------------------------------------------------
# GET /{username} — public profile
# ---------------------------------------------------------------------
@router.get("/{username}")
async def public_profile(username: str) -> dict[str, Any]:
    row = await fetchrow(
        """SELECT username, display_name, avatar_url, avatar_kind, avatar_seed,
                  created_at, total_analyses, current_streak, longest_streak, fires_received
             FROM users WHERE username = $1""",
        username,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    data = dict(row)
    data["joined_at"] = data.pop("created_at").isoformat()
    return {"user": data}


# ---------------------------------------------------------------------
# DELETE /me — hard delete
# ---------------------------------------------------------------------
@router.delete("/me", status_code=status.HTTP_202_ACCEPTED)
async def delete_me(user: CurrentUser, response: Response, confirmation: str | None = None) -> dict[str, str]:
    if confirmation != "delete my account":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirmation_required")
    # Phase 2 M1: simple synchronous delete. M6 upgrades this to async worker w/ blob cleanup.
    async with transaction() as conn:
        # Record the hashed id in deletion_audit (table to be added in a later migration; skip if missing)
        await conn.execute("DELETE FROM users WHERE id = $1::uuid", user.id)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "deleted"}


# ---------------------------------------------------------------------
# Avatar pipeline
# ---------------------------------------------------------------------

async def _process_and_upload_avatar(file: UploadFile, *, user_id: str) -> str:
    """Validate, resize, upload an avatar — returns public URL."""
    from azure.identity.aio import DefaultAzureCredential
    from azure.storage.blob.aio import BlobServiceClient
    from PIL import Image

    settings = get_settings()

    # Size check
    MAX_SIZE = 2 * 1024 * 1024  # 2 MB
    body = await file.read()
    if len(body) > MAX_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "avatar_too_large")

    # MIME sniff via Pillow (rejects non-images)
    try:
        im = Image.open(io.BytesIO(body))
        im.verify()
        im = Image.open(io.BytesIO(body))  # reopen for processing
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "avatar_not_an_image")

    # Convert + resize
    im = im.convert("RGBA")
    im.thumbnail((512, 512), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=88)
    buf.seek(0)

    # Upload
    container = settings.blob_container_avatars
    blob_name = f"{user_id}/{secrets.token_hex(12)}.webp"
    cred = DefaultAzureCredential()
    async with BlobServiceClient(account_url=settings.blob_endpoint, credential=cred) as bsc:
        async with bsc.get_blob_client(container=container, blob=blob_name) as bc:
            await bc.upload_blob(
                buf.getvalue(),
                overwrite=True,
                content_settings={"content_type": "image/webp", "cache_control": "public, max-age=86400"},
            )
    return f"{settings.blob_endpoint}{container}/{blob_name}"
