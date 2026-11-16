"""All ORM models. Importing this package registers every table on `Base.metadata`,
which Alembic compares against the real database to autogenerate migrations.
Add each new model module here, or Alembic won't see its table."""

from models.conversation import Conversation
from models.document import TEXT_SEARCH_CONFIG, ChunkRecord, DocumentRecord, search_vector
from models.eval import EvalResult, EvalRun
from models.memory import MemoryRecord
from models.message import Message, MessageImage
from models.simulated import SimSlackMessage, SimTicket
from models.user import User

__all__ = [
    "TEXT_SEARCH_CONFIG",
    "ChunkRecord",
    "Conversation",
    "DocumentRecord",
    "EvalResult",
    "EvalRun",
    "MemoryRecord",
    "Message",
    "MessageImage",
    "SimSlackMessage",
    "SimTicket",
    "User",
    "search_vector",
]
