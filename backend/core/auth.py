"""Passwords and session tokens (Phase 7). No auth library: each piece is a few lines, and
seeing them is the point.

Password hashing. Never store a password, store `scrypt(password, salt)`. scrypt is slow and
memory-hungry *on purpose*: checking one guess takes ~50 ms, so an attacker with a leaked
database can try thousands of guesses per second instead of billions (a plain SHA-256 would
allow billions). The random salt makes identical passwords hash differently, so one guess
can't be checked against every user at once.

Session tokens. After login the browser holds a JWT (JSON Web Token): a small JSON payload
("user 42, expires 18:00") plus an HMAC signature made with AUTH_SECRET. The server trusts it
without a database lookup, because nobody without the secret can make a valid signature.
It lives in an httpOnly cookie: page JavaScript can't read it, so an XSS bug can't steal it.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel

SCRYPT = {"n": 2**14, "r": 8, "p": 1}  # ~16 MB of memory per check: hard to parallelise on GPUs
TOKEN_ALGORITHM = "HS256"
COOKIE_NAME = "atlas_session"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=_unb64(salt), **SCRYPT)
    # compare_digest takes the same time however many bytes match, so response timing can't
    # reveal how close a guess was.
    return hmac.compare_digest(candidate, _unb64(digest))


class TokenClaims(BaseModel):
    user_id: uuid.UUID
    expires_at: datetime


def create_token(user_id: uuid.UUID, secret: str, hours: float) -> str:
    expires = datetime.now(UTC) + timedelta(hours=hours)
    payload = {"sub": str(user_id), "exp": expires, "iat": datetime.now(UTC)}
    return jwt.encode(payload, secret, algorithm=TOKEN_ALGORITHM)


def read_token(token: str, secret: str) -> TokenClaims | None:
    """The token's claims, or None if it's forged, tampered with, expired or malformed."""
    try:
        # `algorithms` is a list we choose: never let the token pick ("alg": "none" attacks).
        payload = jwt.decode(token, secret, algorithms=[TOKEN_ALGORITHM])
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
