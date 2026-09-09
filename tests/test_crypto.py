import os

from app.crypto import decrypt_secret, encrypt_secret


def test_roundtrip_secret():
    os.environ.setdefault("SAHAL_SECRET_KEY", "test-secret-key")
    token = encrypt_secret("cam-pass")
    assert token
    assert token.startswith("v1:")
    assert decrypt_secret(token) == "cam-pass"


def test_legacy_plaintext_passthrough():
    assert decrypt_secret("old-plain") == "old-plain"
