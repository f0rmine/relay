from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import hit_rate_limit
from app.services.messages import search_user_messages
from app.websocket.events import serialize_message

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/messages", response_model=list[dict])
async def search_messages(
    current_user: CurrentUser,
    db: DbSession,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[dict]:
    if not await hit_rate_limit(f"rate_limit:search:{current_user.id}", 30):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    matches = await search_user_messages(db, current_user, q.strip(), limit)
    return [
        {"conversation_id": message.conversation_id, "message": serialize_message(message)}
        for message in matches
    ]
