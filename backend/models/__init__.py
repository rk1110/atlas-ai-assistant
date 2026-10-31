"""All ORM models. Importing this package registers every table on `Base.metadata`,
which Alembic compares against the real database to autogenerate migrations.
Add each new model module here, or Alembic won't see its table."""

from models.conversation import Conversation
from models.document import TEXT_SEARCH_CONFIG, ChunkRecord, DocumentRecord, search_vector
from models.eval import EvalResult, EvalRun
from models.message import Message
from models.simulated import SimSlackMessage, SimTicket

__all__ = [
    "TEXT_SEARCH_CONFIG",
    "ChunkRecord",
    "Conversation",
    "DocumentRecord",
    "EvalResult",
    "EvalRun",
    "Message",
    "SimSlackMessage",
    "SimTicket",
    "search_vector",
]
