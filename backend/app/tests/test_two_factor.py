import pyotp
import pytest
from httpx import AsyncClient

from app.tests.conftest import register


def _auth_headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _totp_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _wrong_totp(secret: str) -> str:
    code = _totp_code(secret)
    # pick a code that is definitely wrong (different in every digit ideally)
    return "000000" if code != "000000" else "111111"


async def _setup_and_enable(client: AsyncClient, tokens: dict) -> tuple[str, list[str]]:
    headers = _auth_headers(tokens)
    setup = await client.post("/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    otpauth_url = setup.json()["otpauth_url"]
    assert secret
    assert otpauth_url.startswith("otpauth://totp/")
    enable = await client.post(
        "/auth/2fa/enable", headers=headers, json={"code": _totp_code(secret)}
    )
    assert enable.status_code == 200, enable.text
    recovery_codes = enable.json()["recovery_codes"]
    assert len(recovery_codes) == 10
    for code in recovery_codes:
        assert len(code) == 9  # XXXX-XXXX
        assert code[4] == "-"
    return secret, recovery_codes


@pytest.mark.asyncio
async def test_setup_enable_login_verify_flow(client: AsyncClient) -> None:
    tokens = await register(client, "twofa_user", "twofa@example.com")
    headers = _auth_headers(tokens)
    secret, _ = await _setup_and_enable(client, tokens)

    # Login now returns 202 challenge instead of tokens
    login = await client.post(
        "/auth/login", json={"login": "twofa_user", "password": "password123"}
    )
    assert login.status_code == 202, login.text
    body = login.json()
    assert body["requires_2fa"] is True
    assert body["challenge_token"]

    # Wrong code -> 401
    wrong = await client.post(
        "/auth/login/verify",
        json={"challenge_token": body["challenge_token"], "code": _wrong_totp(secret)},
    )
    assert wrong.status_code == 401, wrong.text

    # Correct code -> tokens
    verified = await client.post(
        "/auth/login/verify",
        json={"challenge_token": body["challenge_token"], "code": _totp_code(secret)},
    )
    assert verified.status_code == 200, verified.text
    data = verified.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["username"] == "twofa_user"

    # Token works
    me = await client.get("/auth/me", headers=_auth_headers(data))
    assert me.status_code == 200, me.text

    assert headers  # keep linter happy


@pytest.mark.asyncio
async def test_recovery_code_single_use(client: AsyncClient) -> None:
    tokens = await register(client, "twofa_rec", "rec@example.com")
    _, recovery_codes = await _setup_and_enable(client, tokens)
    code = recovery_codes[0]

    login = await client.post(
        "/auth/login", json={"login": "twofa_rec", "password": "password123"}
    )
    assert login.status_code == 202, login.text
    challenge = login.json()["challenge_token"]

    ok = await client.post(
        "/auth/login/verify", json={"challenge_token": challenge, "code": code}
    )
    assert ok.status_code == 200, ok.text

    # Reuse must fail
    login2 = await client.post(
        "/auth/login", json={"login": "twofa_rec", "password": "password123"}
    )
    assert login2.status_code == 202, login2.text
    challenge2 = login2.json()["challenge_token"]
    reuse = await client.post(
        "/auth/login/verify", json={"challenge_token": challenge2, "code": code}
    )
    assert reuse.status_code == 401, reuse.text


@pytest.mark.asyncio
async def test_disable_with_totp_and_login_without_2fa(client: AsyncClient) -> None:
    tokens = await register(client, "twofa_dis", "dis@example.com")
    headers = _auth_headers(tokens)
    secret, _ = await _setup_and_enable(client, tokens)

    disabled = await client.post(
        "/auth/2fa/disable", headers=headers, json={"code": _totp_code(secret)}
    )
    assert disabled.status_code == 204, disabled.text

    # Login returns tokens directly again
    login = await client.post(
        "/auth/login", json={"login": "twofa_dis", "password": "password123"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


@pytest.mark.asyncio
async def test_login_without_2fa_unchanged(client: AsyncClient) -> None:
    await register(client, "plain_user", "plain@example.com")
    login = await client.post(
        "/auth/login", json={"login": "plain_user", "password": "password123"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]
    assert login.json()["refresh_token"]


@pytest.mark.asyncio
async def test_setup_rejects_when_already_enabled(client: AsyncClient) -> None:
    tokens = await register(client, "twofa_dup", "dup@example.com")
    await _setup_and_enable(client, tokens)
    headers = _auth_headers(tokens)
    again = await client.post("/auth/2fa/setup", headers=headers)
    assert again.status_code == 400, again.text


@pytest.mark.asyncio
async def test_enable_wrong_code_fails(client: AsyncClient) -> None:
    tokens = await register(client, "twofa_wrong", "wrong@example.com")
    headers = _auth_headers(tokens)
    setup = await client.post("/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    bad = await client.post(
        "/auth/2fa/enable", headers=headers, json={"code": _wrong_totp(secret)}
    )
    assert bad.status_code == 401, bad.text


@pytest.mark.asyncio
async def test_disable_with_recovery_code(client: AsyncClient) -> None:
    tokens = await register(client, "twofa_dis_rec", "disrec@example.com")
    headers = _auth_headers(tokens)
    _, recovery_codes = await _setup_and_enable(client, tokens)
    disabled = await client.post(
        "/auth/2fa/disable",
        headers=headers,
        json={"recovery_code": recovery_codes[1]},
    )
    assert disabled.status_code == 204, disabled.text
    login = await client.post(
        "/auth/login", json={"login": "twofa_dis_rec", "password": "password123"}
    )
    assert login.status_code == 200, login.text
