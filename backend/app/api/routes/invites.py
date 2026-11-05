from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.schemas.conversation import ConversationDetail
from app.services.conversations import require_participant
from app.services.invites import (
    find_conversation_by_token,
    get_or_create_invite,
    join_via_invite,
    revoke_invite,
)

router = APIRouter(prefix="/invite", tags=["invites"])
conversations_router = APIRouter(prefix="/conversations", tags=["invites"])


class InviteResponse(BaseModel):
    invite_url: str
    token: str


class InvitePreview(BaseModel):
    conversation_id: str
    title: str | None = None
    participant_count: int = 0
    is_member: bool = False


def _require_group(conversation) -> None:
    if conversation.kind != "group":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only group chats can be invited"
        )


async def _invite_response(db, conversation_id: str, user_id: str) -> InviteResponse:
    conversation = await require_participant(db, conversation_id, user_id)
    _require_group(conversation)
    token = await get_or_create_invite(db, conversation)
    return InviteResponse(invite_url=f"/invite/{token}", token=token)


@conversations_router.post("/{conversation_id}/invite", response_model=InviteResponse)
async def create_invite(
    conversation_id: str, current_user: CurrentUser, db: DbSession
) -> InviteResponse:
    return await _invite_response(db, conversation_id, current_user.id)


@conversations_router.post(
    "/{conversation_id}/invite/revoke", response_model=InviteResponse
)
async def revoke_invites(
    conversation_id: str, current_user: CurrentUser, db: DbSession
) -> InviteResponse:
    conversation = await require_participant(db, conversation_id, current_user.id)
    _require_group(conversation)
    token = await revoke_invite(db, conversation)
    return InviteResponse(invite_url=f"/invite/{token}", token=token)


@router.get("/{token}", response_model=InvitePreview)
async def preview_invite(
    token: str, current_user: CurrentUser, db: DbSession
) -> InvitePreview:
    conversation = await find_conversation_by_token(db, token)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite link")
    return InvitePreview(
        conversation_id=conversation.id,
        title=conversation.title,
        participant_count=len(conversation.participants),
        is_member=any(p.user_id == current_user.id for p in conversation.participants),
    )


@router.post("/{token}/join", response_model=ConversationDetail)
async def join_invite(
    token: str, current_user: CurrentUser, db: DbSession
) -> ConversationDetail:
    from app.api.routes.conversations import serialize_conversation

    conversation = await join_via_invite(db, token, current_user.id)
    serialized = await serialize_conversation(db, conversation, current_user.id)
    return ConversationDetail.model_validate(serialized.model_dump())
