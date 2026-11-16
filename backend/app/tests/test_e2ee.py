import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from httpx import AsyncClient

from app.core import e2ee_wire as wire
from app.tests.conftest import register

RAW = (Encoding.Raw, PublicFormat.Raw)


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


def pub(key) -> bytes:
    return key.public_key().public_bytes(*RAW)


class Keys:
    """Client-side key material for one account, built the way the app does."""

    def __init__(self) -> None:
        self.identity = Ed25519PrivateKey.generate()

    @property
    def identity_b64(self) -> str:
        return wire.b64encode(pub(self.identity))

    def device(self, user_id: str, device_id: str, *, ec: int = 3, kem: int = 2) -> dict:
        signing = Ed25519PrivateKey.generate()
        agreement = pub(X25519PrivateKey.generate())
        signature = self.identity.sign(
            wire.device_message(user_id, device_id, pub(signing), agreement)
        )
        return {
            "device_id": device_id,
            "label": "Test phone",
            "signing_key": wire.b64encode(pub(signing)),
            "agreement_key": wire.b64encode(agreement),
            "identity_signature": wire.b64encode(signature),
            "signed_prekey": signed_prekey(signing, device_id, 1),
            "pq_prekey": pq_prekey(signing, device_id, 1),
            "one_time_prekeys": [
                {"key_id": i, "public_key": wire.b64encode(pub(X25519PrivateKey.generate()))}
                for i in range(1, ec + 1)
            ],
            "pq_one_time_prekeys": [pq_prekey(signing, device_id, 100 + i) for i in range(kem)],
            "_signing": signing,
        }


def signed_prekey(signing: Ed25519PrivateKey, device_id: str, key_id: int) -> dict:
    public = pub(X25519PrivateKey.generate())
    message = wire.prekey_message(wire.SIGNED_PREKEY_LABEL, device_id, key_id, public)
    return {
        "key_id": key_id,
        "public_key": wire.b64encode(public),
        "signature": wire.b64encode(signing.sign(message)),
    }


def pq_prekey(signing: Ed25519PrivateKey, device_id: str, key_id: int) -> dict:
    # The server only checks length + signature; real ML-KEM keys come from the client.
    public = os.urandom(wire.MLKEM768_PUBLIC_KEY_BYTES)
    message = wire.prekey_message(wire.PQ_PREKEY_LABEL, device_id, key_id, public)
    return {
        "key_id": key_id,
        "public_key": wire.b64encode(public),
        "signature": wire.b64encode(signing.sign(message)),
    }


def body(device: dict) -> dict:
    return {k: v for k, v in device.items() if not k.startswith("_")}


async def setup_user(client: AsyncClient, name: str, device_id: str = "device-one"):
    user = await register(client, name, f"{name}@example.com")
    keys = Keys()
    response = await client.put(
        "/e2ee/identity", json={"identity_key": keys.identity_b64}, headers=auth(user)
    )
    assert response.status_code == 200, response.text
    device = keys.device(user["user"]["id"], device_id)
    response = await client.post("/e2ee/devices", json=body(device), headers=auth(user))
    assert response.status_code == 200, response.text
    return user, keys, device


# ------------------------------------------------------------------ wire format


def test_shared_wire_vector_matches_mobile_client() -> None:
    """Pinned vector; mobile/src/crypto/wire.test.ts asserts the same bytes and signature."""
    identity = Ed25519PrivateKey.from_private_bytes(bytes([1]) * 32)
    signing_pub = pub(Ed25519PrivateKey.from_private_bytes(bytes([2]) * 32))
    agreement = bytes(range(32))
    message = wire.device_message("user-1", "device-abc", signing_pub, agreement)
    assert message.hex() == (
        b"relay-e2ee-v1/device\x00user-1\x00device-abc\x00".hex()
        + signing_pub.hex()
        + agreement.hex()
    )
    assert wire.b64encode(pub(identity)) == "iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1w"
    assert wire.b64encode(identity.sign(message)) == (
        "FqLAJw0VUfiV5xmyLcjFVvlylblU97K1niafsUptGlrFKKNDuxlj3YChV_eXayJaRwbRhRk4RxiDDSR_KxBtDA"
    )
    spk = wire.prekey_message(wire.SIGNED_PREKEY_LABEL, "device-abc", 7, agreement)
    assert spk[: len(wire.SIGNED_PREKEY_LABEL)] == wire.SIGNED_PREKEY_LABEL
    assert spk[-36:-32] == (7).to_bytes(4, "big")


def test_b64_rejects_padding_and_wrong_length() -> None:
    for bad in ("", "AAAA=", "A" * 42, "%%%"):
        try:
            wire.b64decode(bad, 32, "k")
        except wire.WireError:
            continue
        raise AssertionError(f"accepted {bad!r}")


# -------------------------------------------------------------- happy path


async def test_register_publish_and_claim(client: AsyncClient) -> None:
    alice, alice_keys, device = await setup_user(client, "alice")
    bob = await register(client, "bob", "bob@example.com")
    alice_id = alice["user"]["id"]

    own = await client.get("/e2ee/devices", headers=auth(alice))
    assert own.status_code == 200
    assert own.json()[0]["label"] == "Test phone"
    assert own.json()[0]["prekeys"] == {"one_time_prekeys": 3, "pq_one_time_prekeys": 2}

    directory = await client.get(f"/e2ee/users/{alice_id}", headers=auth(bob))
    assert directory.status_code == 200
    data = directory.json()
    assert data["identity_key"] == alice_keys.identity_b64
    assert data["devices"][0]["label"] is None  # labels are owner-only metadata
    assert data["devices"][0]["identity_signature"] == device["identity_signature"]

    claimed = await client.post(
        f"/e2ee/users/{alice_id}/devices/device-one/claim", headers=auth(bob)
    )
    assert claimed.status_code == 200, claimed.text
    bundle = claimed.json()
    assert bundle["one_time_prekey"]["key_id"] == 1
    assert bundle["pq_one_time_prekey"]["key_id"] == 100

    # Each one-time key is handed out exactly once, then the last-resort path.
    seen = {1}
    for _ in range(2):
        again = await client.post(
            f"/e2ee/users/{alice_id}/devices/device-one/claim", headers=auth(bob)
        )
        seen.add(again.json()["one_time_prekey"]["key_id"])
    assert seen == {1, 2, 3}
    exhausted = await client.post(
        f"/e2ee/users/{alice_id}/devices/device-one/claim", headers=auth(bob)
    )
    assert exhausted.json()["one_time_prekey"] is None
    assert exhausted.json()["pq_one_time_prekey"] is None


async def test_prekey_top_up_and_rotation(client: AsyncClient) -> None:
    alice, _keys, device = await setup_user(client, "alice")
    signing = device["_signing"]
    response = await client.put(
        "/e2ee/devices/device-one/prekeys",
        json={
            "signed_prekey": signed_prekey(signing, "device-one", 2),
            "one_time_prekeys": [
                {"key_id": 50, "public_key": wire.b64encode(pub(X25519PrivateKey.generate()))}
            ],
        },
        headers=auth(alice),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"one_time_prekeys": 4, "pq_one_time_prekeys": 2}
    own = (await client.get("/e2ee/devices", headers=auth(alice))).json()
    assert own[0]["signed_prekey"]["key_id"] == 2


async def test_reregistering_same_device_is_idempotent(client: AsyncClient) -> None:
    alice, _keys, device = await setup_user(client, "alice")
    again = await client.post("/e2ee/devices", json=body(device), headers=auth(alice))
    assert again.status_code == 200, again.text
    assert again.json()["prekeys"]["one_time_prekeys"] == 3


# ------------------------------------------------------------ forged inputs


async def test_device_not_signed_by_identity_is_rejected(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    keys = Keys()
    await client.put("/e2ee/identity", json={"identity_key": keys.identity_b64}, headers=auth(alice))
    # A device vouched for by some *other* identity key (e.g. a malicious server's).
    forged = Keys().device(alice["user"]["id"], "device-evil")
    response = await client.post("/e2ee/devices", json=body(forged), headers=auth(alice))
    assert response.status_code == 400
    assert "identity_signature" in response.json()["detail"]


async def test_device_signature_is_bound_to_user(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    keys = Keys()
    await client.put("/e2ee/identity", json={"identity_key": keys.identity_b64}, headers=auth(alice))
    replayed = keys.device("someone-else", "device-one")
    response = await client.post("/e2ee/devices", json=body(replayed), headers=auth(alice))
    assert response.status_code == 400


async def test_bad_prekey_signature_is_rejected(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    keys = Keys()
    await client.put("/e2ee/identity", json={"identity_key": keys.identity_b64}, headers=auth(alice))
    device = keys.device(alice["user"]["id"], "device-one")
    device["signed_prekey"] = signed_prekey(Ed25519PrivateKey.generate(), "device-one", 1)
    response = await client.post("/e2ee/devices", json=body(device), headers=auth(alice))
    assert response.status_code == 400
    assert "signed_prekey" in response.json()["detail"]


async def test_device_requires_identity(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    device = Keys().device(alice["user"]["id"], "device-one")
    response = await client.post("/e2ee/devices", json=body(device), headers=auth(alice))
    assert response.status_code == 409


async def test_device_id_cannot_be_rebound_to_new_keys(client: AsyncClient) -> None:
    alice, keys, _device = await setup_user(client, "alice")
    other = keys.device(alice["user"]["id"], "device-one")
    response = await client.post("/e2ee/devices", json=body(other), headers=auth(alice))
    assert response.status_code == 409


# ------------------------------------------------------------ identity reset


async def test_identity_replace_needs_password_and_revokes_devices(client: AsyncClient) -> None:
    alice, _keys, _device = await setup_user(client, "alice")
    new = Keys()
    no_flag = await client.put(
        "/e2ee/identity", json={"identity_key": new.identity_b64}, headers=auth(alice)
    )
    assert no_flag.status_code == 409
    wrong = await client.put(
        "/e2ee/identity",
        json={"identity_key": new.identity_b64, "replace": True, "password": "nope"},
        headers=auth(alice),
    )
    assert wrong.status_code == 403
    ok = await client.put(
        "/e2ee/identity",
        json={"identity_key": new.identity_b64, "replace": True, "password": "password123"},
        headers=auth(alice),
    )
    assert ok.status_code == 200
    assert ok.json()["revoked_devices"] == 1
    assert (await client.get("/e2ee/devices", headers=auth(alice))).json() == []


async def test_revoked_device_disappears_and_cannot_return(client: AsyncClient) -> None:
    alice, _keys, device = await setup_user(client, "alice")
    assert (await client.delete("/e2ee/devices/device-one", headers=auth(alice))).status_code == 204
    directory = await client.get(f"/e2ee/users/{alice['user']['id']}", headers=auth(alice))
    assert directory.json()["devices"] == []
    again = await client.post("/e2ee/devices", json=body(device), headers=auth(alice))
    assert again.status_code == 409


# -------------------------------------------------------------- visibility


async def test_blocked_users_cannot_fetch_or_claim(client: AsyncClient) -> None:
    alice, _keys, _device = await setup_user(client, "alice")
    bob = await register(client, "bob", "bob@example.com")
    alice_id = alice["user"]["id"]
    blocked = await client.post(f"/users/{bob['user']['id']}/block", headers=auth(alice))
    assert blocked.status_code in (200, 201, 204), blocked.text
    assert (await client.get(f"/e2ee/users/{alice_id}", headers=auth(bob))).status_code == 404
    claim = await client.post(
        f"/e2ee/users/{alice_id}/devices/device-one/claim", headers=auth(bob)
    )
    assert claim.status_code == 404


async def test_deleted_account_keys_are_removed(client: AsyncClient) -> None:
    alice, _keys, _device = await setup_user(client, "alice")
    bob = await register(client, "bob", "bob@example.com")
    deleted = await client.request(
        "DELETE", "/users/me", json={"confirmation": "DELETE"}, headers=auth(alice)
    )
    assert deleted.status_code in (200, 204), deleted.text
    response = await client.get(f"/e2ee/users/{alice['user']['id']}", headers=auth(bob))
    assert response.status_code == 404
