"""GET /api/images/{id}: an image attached to a chat message (Phase 6).

Served separately from the message JSON, so opening a conversation doesn't pull megabytes
of base64, and the browser can cache each image.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response

from api.deps import SessionDep
from models import MessageImage

router = APIRouter(prefix="/api/images", tags=["images"])


@router.get("/{image_id}")
async def get_image(image_id: uuid.UUID, session: SessionDep) -> Response:
    image = await session.get(MessageImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=image.data,
        media_type=image.media_type,  # sniffed from the bytes on upload, never the client's word
        headers={
            # An image never changes once saved: let the browser keep it.
            "Cache-Control": "private, max-age=86400, immutable",
            # Never let a browser guess a different type (e.g. run an "image" as HTML).
            "X-Content-Type-Options": "nosniff",
        },
    )
