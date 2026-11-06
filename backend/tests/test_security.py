from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify():
    hashed = hash_password("password")
    assert hashed != "password"
    assert verify_password("password", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_access_and_refresh_types():
    access = create_access_token("user-1", "admin@docchat.com")
    refresh = create_refresh_token("user-1")
    access_payload = decode_token(access)
    refresh_payload = decode_token(refresh)
    assert access_payload["type"] == "access"
    assert access_payload["sub"] == "user-1"
    assert access_payload["email"] == "admin@docchat.com"
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload["jti"] != access_payload["jti"]
