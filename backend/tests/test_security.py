import uuid

import pytest

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(user_id, org_id, "soc_analyst", ["investigation:read"])
    payload = decode_token(token, expected_type=TokenType.ACCESS)

    assert payload.user_id == str(user_id)
    assert payload.org_id == str(org_id)
    assert payload.role == "soc_analyst"
    assert payload.permissions == ["investigation:read"]


def test_refresh_token_rejected_as_access_token():
    user_id = uuid.uuid4()
    refresh = create_refresh_token(user_id)
    with pytest.raises(InvalidTokenError):
        decode_token(refresh, expected_type=TokenType.ACCESS)


def test_garbage_token_raises():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-real-token", expected_type=TokenType.ACCESS)
