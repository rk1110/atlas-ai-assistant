"""Create or update the demo users from config/auth.yaml (Phase 7).

    docker compose exec backend python -m scripts.seed_users

Safe to re-run: existing users keep their id (and so their chats); name, role, access tags
and password are refreshed. The password is DEMO_PASSWORD from .env (never printed).
Conversations and memories from before login existed are given to the user marked
`owns_existing_data`, so nothing becomes invisible.
"""

import asyncio

from sqlalchemy import select, update

from core.auth import hash_password
from core.auth_config import get_auth_config
from core.config import get_settings
from core.db import get_session_factory
from models import Conversation, MemoryRecord, User


async def seed() -> int:
    password = get_settings().demo_password
    if password is None or len(password.get_secret_value()) < 8:
        print("Set DEMO_PASSWORD in .env (8+ characters), then restart the backend.")
        return 1
    config = get_auth_config()
    async with get_session_factory()() as session:
        for demo in config.users:
            email = demo.email.lower()
            user = await session.scalar(select(User).where(User.email == email))
            created = user is None
            if user is None:
                user = User(email=email)
                session.add(user)
            user.name = demo.name
            user.role = demo.role
            user.access_tags = demo.access
            user.password_hash = hash_password(password.get_secret_value())
            await session.flush()
            print(f"  {'created' if created else 'updated'} {email:24} access {demo.access}")
            if demo.owns_existing_data:
                chats = await session.execute(
                    update(Conversation)
                    .where(Conversation.user_id.is_(None))
                    .values(user_id=user.id)
                )
                facts = await session.execute(
                    update(MemoryRecord)
                    .where(MemoryRecord.user_id.is_(None))
                    .values(user_id=user.id)
                )
                moved = (chats.rowcount, facts.rowcount)  # type: ignore[attr-defined]
                print(f"    gave them {moved[0]} older conversations and {moved[1]} memories")
        await session.commit()
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(seed()))


if __name__ == "__main__":
    main()
