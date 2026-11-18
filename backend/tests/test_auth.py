"""Phase 7 checkpoint C: login, per-user data, permission-aware retrieval, rate limits."""

import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from api.deps import get_current_user, get_rate_limiter, get_settings
from core.access import all_access, reader_tags, set_reader_tags
from core.auth import COOKIE_NAME, create_token, hash_password, read_token, verify_password
from core.auth_config import RateLimits
from core.db import get_session_factory
from core.rate_limit import RateLimiter, RateLimitExceeded
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.markdown_dir import AcmeDocsSource
from main import app
from models import Conversation, User
from retrieval.vector import VectorRetriever
from tests.conftest import FakeEmbedder
from tests.test_retrieval import CHUNKING, ingest

SECRET = "test-secret-that-is-long-enough-for-hs256"
PASSWORD = "correct horse battery"

# ---------------------------------------------------------------------- passwords + tokens


def test_passwords_are_salted_hashes_checked_in_constant_time():
    stored = hash_password(PASSWORD)
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert stored != hash_password(PASSWORD)  # a fresh salt every time
    assert verify_password(PASSWORD, stored)
    assert not verify_password("wrong", stored)
    assert not verify_password(PASSWORD, "garbage")


def test_tokens_are_signed_and_expire():
    user_id = uuid.uuid4()
    claims = read_token(create_token(user_id, SECRET, hours=1), SECRET)
    assert claims is not None and claims.user_id == user_id
    assert (
        read_token(
            create_token(user_id, SECRET, hours=1), "another-secret-of-at-least-thirty-two-bytes"
        )
        is None
    )
    assert read_token(create_token(user_id, SECRET, hours=-1), SECRET) is None  # expired
    unsigned = jwt.encode({"sub": str(user_id), "exp": time.time() + 60}, None, algorithm="none")
    assert read_token(unsigned, SECRET) is None  # "alg: none" is refused


# ---------------------------------------------------------------------- the HTTP flow


async def add_user(email: str, access: list[str]) -> uuid.UUID:
    async with get_session_factory()() as session:
        user = User(email=email, name=email.split("@")[0], password_hash=hash_password(PASSWORD),
                    access_tags=access)  # fmt: skip
        session.add(user)
        await session.commit()
        return user.id


@pytest.fixture
async def real_login(db: None) -> AsyncIterator[AsyncClient]:
    """A client with the real get_current_user (no test override)."""
    app.dependency_overrides.pop(get_current_user)
    settings = get_settings().model_copy(update={"auth_secret": SecretStr(SECRET)})
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def log_in(client: AsyncClient, email: str, password: str = PASSWORD):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def test_login_sets_an_httponly_cookie_and_logout_clears_it(real_login: AsyncClient):
    await add_user("sam@acme.example", ["public"])
    assert (await real_login.get("/api/conversations")).status_code == 401  # not logged in

    response = await log_in(real_login, "SAM@acme.example ")  # case and spaces don't matter
    assert response.status_code == 200 and response.json()["name"] == "sam"
    cookie = response.headers["set-cookie"]
    assert (
        cookie.startswith(f"{COOKIE_NAME}=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    )
    assert (await real_login.get("/api/auth/me")).json()["email"] == "sam@acme.example"
    assert (await real_login.get("/api/conversations")).status_code == 200

    await real_login.post("/api/auth/logout")
    assert (await real_login.get("/api/auth/me")).status_code == 401


async def test_wrong_password_and_unknown_email_look_the_same(real_login: AsyncClient):
    await add_user("sam@acme.example", ["public"])
    wrong = await log_in(real_login, "sam@acme.example", "nope")
    unknown = await log_in(real_login, "nobody@acme.example")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # doesn't reveal which emails have accounts


async def test_a_forged_cookie_is_rejected(real_login: AsyncClient):
    user_id = await add_user("sam@acme.example", ["public"])
    real_login.cookies.set(
        COOKIE_NAME, create_token(user_id, "attacker-secret-of-at-least-thirty-two-bytes", hours=1)
    )
    assert (await real_login.get("/api/auth/me")).status_code == 401


async def test_users_never_see_each_others_conversations(real_login: AsyncClient):
    await add_user("sam@acme.example", ["public"])
    grace = await add_user("grace@acme.example", ["public", "hr"])
    theirs = uuid.uuid4()
    async with get_session_factory()() as session:
        session.add(Conversation(id=theirs, title="Grace's chat", user_id=grace))
        await session.commit()

    await log_in(real_login, "sam@acme.example")
    assert (await real_login.get("/api/conversations")).json() == []
    assert (await real_login.get(f"/api/conversations/{theirs}/messages")).status_code == 404
    assert (await real_login.delete(f"/api/conversations/{theirs}")).status_code == 404
    hijack = {"conversation_id": str(theirs), "message": "continue this chat"}
    assert (await real_login.post("/api/chat", json=hijack)).status_code == 404


# ---------------------------------------------------------------------- permissions


async def test_restricted_documents_only_reach_their_readers(
    db: None, tmp_path: Path, fake_embedder: FakeEmbedder
):
    await ingest(tmp_path / "docs", "acme-docs", {"leave.md": "Parental leave is 16 weeks."},
                 fake_embedder)  # fmt: skip
    folder = tmp_path / "hr"
    folder.mkdir()
    (folder / "salaries.md").write_text(
        "---\ntitle: Salaries\naccess: [hr]\n---\n# Salaries\n\nSenior salary is 80k euros.\n"
    )
    pipeline = IngestionPipeline(fake_embedder, CHUNKING, get_session_factory())
    await pipeline.ingest_source(AcmeDocsSource(folder, name="hr-docs"))
    retriever = VectorRetriever(fake_embedder, get_session_factory())

    async def found(tags: list[str] | None) -> set[str]:
        set_reader_tags(tags)
        return {c.title for c in await retriever.retrieve("senior salary euros", top_k=5)}

    assert "Salaries" not in await found(["public"])
    assert "Salaries" in await found(["public", "hr"])
    set_reader_tags(["public"])
    assert reader_tags() == ["public"]  # the safe default for scripts
    with all_access():
        assert "Salaries" in await found(reader_tags())
    set_reader_tags(["public"])


# ---------------------------------------------------------------------- rate limits


class MemoryCounters:
    def __init__(self, fail: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.fail = fail

    async def increment(self, key: str, ttl_seconds: int) -> int:
        if self.fail:
            raise ConnectionError("redis is down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


async def test_rate_limits_count_per_user_and_fail_open():
    limiter = RateLimiter(MemoryCounters(), RateLimits(per_minute=2, per_day=100))
    sam, grace = uuid.uuid4(), uuid.uuid4()
    await limiter.check(sam)
    await limiter.check(sam)
    with pytest.raises(RateLimitExceeded, match="at most 2 messages a minute") as exc:
        await limiter.check(sam)
    assert 0 < exc.value.retry_after <= 60
    await limiter.check(grace)  # someone else's count is separate
    await RateLimiter(MemoryCounters(fail=True), RateLimits(per_minute=1)).check(sam)  # allowed


async def test_over_the_limit_is_a_429_with_retry_after(client: AsyncClient):
    limiter = RateLimiter(MemoryCounters(), RateLimits(per_minute=1, per_day=100))
    app.dependency_overrides[get_rate_limiter] = lambda: limiter  # one limiter, shared counts
    body = {"conversation_id": str(uuid.uuid4()), "message": "Hello"}
    assert (await client.post("/api/chat", json=body)).status_code == 200
    second = await client.post("/api/chat", json=body)
    assert second.status_code == 429 and int(second.headers["retry-after"]) <= 60


def test_deployment_can_force_secure_cookies(monkeypatch):
    """Phase 7D: docker-compose.prod.yml sets AUTH_SECURE_COOKIE=true; the repo's auth.yaml
    keeps false for http://localhost."""
    from core.auth_config import get_auth_config

    get_auth_config.cache_clear()
    monkeypatch.setenv("AUTH_SECURE_COOKIE", "true")
    try:
        assert get_auth_config().session.secure_cookie is True
    finally:
        get_auth_config.cache_clear()
