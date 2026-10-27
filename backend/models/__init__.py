"""All ORM models. Importing this package registers every table on `Base.metadata`,
which Alembic compares against the real database to autogenerate migrations.
Add each new model module here, or Alembic won't see its table."""

from models.conversation import Conversation
from models.eval import EvalResult, EvalRun
from models.message import Message

__all__ = ["Conversation", "EvalResult", "EvalRun", "Message"]
