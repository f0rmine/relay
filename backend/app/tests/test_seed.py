import pytest

from app.scripts_seed import get_seed_password


def test_seed_password_must_be_explicit_and_long_enough(monkeypatch) -> None:
    monkeypatch.delenv("RELAY_SEED_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="at least 8 characters"):
        get_seed_password()

    monkeypatch.setenv("RELAY_SEED_PASSWORD", "demo-password")
    assert get_seed_password() == "demo-password"
