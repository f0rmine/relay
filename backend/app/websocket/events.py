from fastapi.encoders import jsonable_encoder

from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.attachment import AttachmentOut
from app.services.messages import DecryptionError, plaintext_message_text


def serialize_message(message: Message) -> dict:
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
            }
        )
    try:
        text = plaintext_message_text(message)
    except DecryptionError:
        text = None
    return jsonable_encoder(
        {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "sender_id": message.sender_id,
            "client_message_id": message.client_message_id,
            "text": text,
            "undecryptable": text is None and message.text_ciphertext is not None,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "edited_at": message.edited_at,
            "deleted_at": message.deleted_at,
            "deleted_by_id": message.deleted_by_id,
            "attachments": [AttachmentOut.model_validate(item) for item in message.attachments],
            "read_by": [read.user_id for read in message.reads],
        }
    )


async def conversation_participant_ids(conversation: Conversation) -> list[str]:
    return [participant.user_id for participant in conversation.participants]
