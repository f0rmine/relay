#!/usr/bin/env python3
import asyncio
from dataclasses import dataclass
import json
import sys
import urllib.error
import urllib.request
from uuid import uuid4

import websockets


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://100.106.107.54:8000"
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
PASSWORD = "password123"
SMOKE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00"
    b"\x1c\xd2\xbd\x89"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass(frozen=True)
class DummyUser:
    username: str
    email: str
    display_name: str


DUMMY_USERS = [
    DummyUser("olena", "olena@example.com", "Олена"),
    DummyUser("taras", "taras@example.com", "Тарас"),
    DummyUser("oksana", "oksana@example.com", "Оксана"),
    DummyUser("mykola", "mykola@example.com", "Микола"),
]


def request_json(path: str, method: str = "GET", data: dict | None = None, token: str | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def request_bytes(path: str, token: str | None = None) -> bytes:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE_URL + path, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read()


def upload_png(token: str, conversation_id: str) -> dict:
    boundary = f"----relay-smoke-{uuid4().hex}"
    fields = [
        (
            "conversation_id",
            None,
            "text/plain",
            conversation_id.encode(),
        ),
        (
            "file",
            "smoke.png",
            "image/png",
            SMOKE_PNG,
        ),
    ]
    body = bytearray()
    for field_name, filename, content_type, value in fields:
        body.extend(f"--{boundary}\r\n".encode())
        disposition = f'Content-Disposition: form-data; name="{field_name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        body.extend(f"{disposition}\r\n".encode())
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(value)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        BASE_URL + "/attachments/upload",
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def login(username: str) -> dict:
    return request_json("/auth/login", "POST", {"login": username, "password": PASSWORD})


def register_or_login(user: DummyUser) -> dict:
    try:
        return request_json(
            "/auth/register",
            "POST",
            {
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "password": PASSWORD,
            },
        )
    except urllib.error.HTTPError as error:
        if error.code not in {400, 409}:
            raise
        return login(user.username)


async def send_and_wait(
    sender: dict,
    conversation_id: str,
    text: str | None,
    attachment_ids: list[str] | None = None,
) -> dict:
    attachment_ids = attachment_ids or []
    async with websockets.connect(
        WS_URL,
        open_timeout=10,
    ) as websocket:
        await websocket.send(json.dumps({"type": "auth", "payload": {"token": sender["access_token"]}}))
        auth_raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        auth_event = json.loads(auth_raw)
        if auth_event.get("type") != "auth:ok":
            raise RuntimeError(f"websocket auth failed: {auth_event}")
        await websocket.send(
            json.dumps({"type": "conversation:join", "payload": {"conversation_id": conversation_id}})
        )
        await asyncio.wait_for(websocket.recv(), timeout=10)
        await websocket.send(
            json.dumps(
                {
                    "type": "message:send",
                    "payload": {
                        "conversation_id": conversation_id,
                        "text": text,
                        "attachment_ids": attachment_ids,
                    },
                }
            )
        )
        for _ in range(5):
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            event = json.loads(raw)
            if event.get("type") != "message:new":
                continue
            payload = event["payload"]
            payload_attachment_ids = {attachment["id"] for attachment in payload.get("attachments", [])}
            if payload.get("text") == text and set(attachment_ids).issubset(payload_attachment_ids):
                return payload
        raise RuntimeError(f"message:new was not received for: {text}")


async def main() -> None:
    accounts = {user.username: register_or_login(user) for user in DUMMY_USERS}
    sent_messages: list[tuple[str, str, str, str, str]] = []
    conversation_reader: dict[str, str] = {}

    for sender_user in DUMMY_USERS:
        sender = accounts[sender_user.username]
        for receiver_user in DUMMY_USERS:
            if sender_user.username == receiver_user.username:
                continue

            receiver = accounts[receiver_user.username]
            conversation = request_json(
                "/conversations",
                "POST",
                {"participant_id": receiver["user"]["id"]},
                sender["access_token"],
            )
            conversation_id = conversation["id"]
            text = f"Hi {receiver_user.display_name} from {sender_user.display_name}!"
            message = await send_and_wait(sender, conversation_id, text)
            sent_messages.append(
                (conversation_id, message["id"], sender_user.username, sender_user.display_name, text)
            )
            conversation_reader.setdefault(conversation_id, sender_user.username)

    olena = accounts["olena"]
    taras = accounts["taras"]
    attachment_conversation = request_json(
        "/conversations",
        "POST",
        {"participant_id": taras["user"]["id"]},
        olena["access_token"],
    )
    attachment = upload_png(olena["access_token"], attachment_conversation["id"])
    attachment_message_text = "Smoke image attachment"
    attachment_message = await send_and_wait(
        olena,
        attachment_conversation["id"],
        attachment_message_text,
        [attachment["id"]],
    )
    downloaded = request_bytes(f"/attachments/{attachment['id']}/download", taras["access_token"])
    if downloaded != SMOKE_PNG:
        raise RuntimeError("downloaded attachment bytes did not match uploaded bytes")
    attachment_history = request_json(
        f"/conversations/{attachment_conversation['id']}/messages?limit=20",
        token=taras["access_token"],
    )
    attachment_history_message = next(
        (
            item
            for item in attachment_history["items"]
            if item["id"] == attachment_message["id"]
        ),
        None,
    )
    if attachment_history_message is None:
        raise RuntimeError("attachment message was not found in REST history")
    if not any(item["id"] == attachment["id"] for item in attachment_history_message["attachments"]):
        raise RuntimeError("attachment metadata was not found in REST history")

    checked_conversations: set[str] = set()
    for conversation_id, _, _, _, _ in sent_messages:
        if conversation_id in checked_conversations:
            continue
        checked_conversations.add(conversation_id)
        history = request_json(
            f"/conversations/{conversation_id}/messages?limit=100",
            token=accounts[conversation_reader[conversation_id]]["access_token"],
        )
        history_texts = {item.get("text") for item in history["items"]}
        expected_texts = {
            text
            for sent_conversation_id, _, _, _, text in sent_messages
            if sent_conversation_id == conversation_id
        }
        if not expected_texts.issubset(history_texts):
            missing = sorted(expected_texts - history_texts)
            raise RuntimeError(f"messages were sent but not found in REST history: {missing}")

    print("Smoke messages passed")
    print(f"Backend: {BASE_URL}")
    print(f"Dummy users: {', '.join(user.display_name for user in DUMMY_USERS)}")
    print(f"Conversations checked: {len(checked_conversations)}")
    print(f"Messages sent: {len(sent_messages)}")
    print(f"Attachment message: {attachment_message['id']} ({attachment['original_filename']})")
    for conversation_id, message_id, _, sender_name, text in sent_messages:
        print(f"- {sender_name}: {text} ({message_id}, conversation {conversation_id})")


if __name__ == "__main__":
    asyncio.run(main())
