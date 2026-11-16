"""Login (Phase 7): demo email/password accounts, a signed session cookie.

    POST /api/auth/login    {email, password} -> sets the atlas_session cookie
    POST /api/auth/logout   clears it
    GET  /api/auth/me       who is logged in (401 if nobody)

The cookie is httpOnly (page JavaScript can't read it, so an XSS bug can't steal it) and
SameSite=Lax (other sites can't make your browser send it with a POST, which blocks CSRF:
cross-site request forgery). The API at :8000 and the app at :3000 are the same *site*
(localhost), so the browser sends it on the app's fetches with `credentials: "include"`.
"""

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.deps import CurrentUser, CurrentUserDep, SessionDep, SettingsDep
from core.auth import COOKIE_NAME, create_token, hash_password, verify_password
from core.auth_config import get_auth_config
from models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Checked when the email is unknown, so a wrong email takes as long as a wrong password:
# otherwise response timing would reveal which emails have accounts.
_DUMMY_HASH = hash_password("not-a-real-password")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
async def login(
    body: LoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> CurrentUser:
    if settings.auth_secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Login isn't configured.")
    user = await session.scalar(select(User).where(User.email == body.email.strip().lower()))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        # One message for both cases: don't confirm which emails exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.")
    config = get_auth_config().session
    token = create_token(user.id, settings.auth_secret.get_secret_value(), config.hours)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(config.hours * 3600),
        httponly=True,
        samesite="lax",
        secure=config.secure_cookie,
        path="/",
    )
    return CurrentUser(
        id=user.id, email=user.email, name=user.name, role=user.role,
        access_tags=list(user.access_tags),
    )  # fmt: skip


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    # A JWT can't be "revoked" without a server-side list; deleting the cookie ends this
    # browser's session, and every token expires within session.hours anyway.
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me")
async def me(user: CurrentUserDep) -> CurrentUser:
    return user
