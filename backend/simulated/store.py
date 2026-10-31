"""Write and read the simulated Jira and Slack. The write tools and the Outbox page use this.

Phase 5 wraps these same functions in MCP servers; the tools then talk MCP instead of
calling this module directly, exactly as they would with a real Jira or Slack.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models import SimSlackMessage, SimTicket

FIRST_TICKET_NUMBER = 1001


class SimulatedJira:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def create_ticket(
        self, project: str, summary: str, description: str, priority: str
    ) -> SimTicket:
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count()).select_from(SimTicket).where(SimTicket.project == project)
            )
            ticket = SimTicket(
                key=f"{project}-{FIRST_TICKET_NUMBER + (count or 0)}",
                project=project,
                summary=summary,
                description=description,
                priority=priority,
                status="Open",
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            return ticket

    async def list_tickets(self) -> list[SimTicket]:
        async with self._session_factory() as session:
            rows = await session.scalars(select(SimTicket).order_by(SimTicket.created_at.desc()))
            return list(rows)


class SimulatedSlack:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def post_message(self, channel: str, text: str) -> SimSlackMessage:
        async with self._session_factory() as session:
            message = SimSlackMessage(channel=channel, text=text)
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def list_messages(self) -> list[SimSlackMessage]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(SimSlackMessage).order_by(SimSlackMessage.created_at.desc())
            )
            return list(rows)
