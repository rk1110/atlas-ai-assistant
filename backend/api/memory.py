"""The Memory API (Phase 4): see and delete what Atlas remembers about you.

    GET    /api/memories          every stored fact, newest first
    DELETE /api/memories/{id}     forget one

Users must be able to see and remove what an assistant remembers about them: it is their
data, and a wrong "fact" would otherwise quietly shape every future answer.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, MemoryDep
from services.memory import MemoryItem

router = APIRouter(prefix="/api/memories", tags=["memory"])


@router.get("")
async def list_memories(memory: MemoryDep, user: CurrentUserDep) -> list[MemoryItem]:
    return await memory.all(user.id)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget(memory_id: uuid.UUID, memory: MemoryDep, user: CurrentUserDep) -> None:
    if not await memory.forget(memory_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
