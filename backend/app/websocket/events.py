from fastapi.encoders import jsonable_encoder

from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.attachment import AttachmentOut
from app.services.messages import DecryptionError, parse_mentions, plaintext_message_text


def _safe_text(message: Message) -> str | None:
    try:
        return plaintext_message_text(message)
    except DecryptionError:
        return None


def _reactions_aggregate(message: Message) -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for reaction in message.reactions:
        grouped.setdefault(reaction.emoji, []).append(reaction.user_id)
    return [
        {"emoji": emoji, "user_ids": user_ids}
        for emoji, user_ids in sorted(grouped.items(), key=lambda item: item[0])
    ]


def _reply_to_snapshot(message: Message) -> dict | None:
    target = message.reply_to if message.reply_to_id else None
    if target is None or target.id != message.reply_to_id:
        return None
    return {
        "id": target.id,
        "text": _safe_text(target) if target.deleted_at is None else None,
        "sender_id": target.sender_id,
        "undecryptable": (
            target.deleted_at is None
            and target.text_ciphertext is not None
            and _safe_text(target) is None
        ),
    }


def serialize_message(message: Message) -> dict:
    link_preview = getattr(message, "_link_preview", None)
    if message.deleted_at is not None:
        return jsonable_encoder(
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "sender_id": message.sender_id,
                "client_message_id": message.client_message_id,
                "text": None,
                "undecryptable": False,
                "created_at": message.created_at,
                "updated_at": message.updated_at,
                "edited_at": message.edited_at,
                "deleted_at": message.deleted_at,
                "deleted_by_id": message.deleted_by_id,
                "attachments": [],
                "read_by": [read.user_id for read in message.reads],
                "reactions": [],
                "reply_to": None,
                "scheduled_at": message.scheduled_at,
                "mentions": [],
                "link_preview": None,
            }
        )
    text = _safe_text(message)
    undecryptable = text is None and message.text_ciphertext is not None
    return jsonable_encoder(
        {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "sender_id": message.sender_id,
            "client_message_id": message.client_message_id,
            "text": text,
            "undecryptable": undecryptable,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "edited_at": message.edited_at,
            "deleted_at": message.deleted_at,
            "deleted_by_id": message.deleted_by_id,
            "attachments": [AttachmentOut.model_validate(item) for item in message.attachments],
            "read_by": [read.user_id for read in message.reads],
            "reactions": _reactions_aggregate(message),
            "reply_to": _reply_to_snapshot(message),
            "scheduled_at": message.scheduled_at,
            "mentions": parse_mentions(message),
            "link_preview": link_preview,
        }
    )


async def conversation_participant_ids(conversation: Conversation) -> list[str]:
    return [participant.user_id for participant in conversation.participants]
