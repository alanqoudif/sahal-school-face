from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app.settings import secret_key

_PREFIX = "v1:"


def _fernet_material() -> bytes:
    return hashlib.sha256(secret_key().encode("utf-8")).digest()


def encrypt_secret(plain: str | None) -> str | None:
    if not plain:
        return None
    raw = plain.encode("utf-8")
    key = _fernet_material()
    iv = os.urandom(16)
    keystream = _keystream(key, iv, len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, keystream))
    mac = hmac.new(key, iv + cipher, hashlib.sha256).digest()
    blob = base64.urlsafe_b64encode(iv + mac + cipher).decode("ascii")
    return f"{_PREFIX}{blob}"


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value
    try:
        blob = base64.urlsafe_b64decode(value[len(_PREFIX) :].encode("ascii"))
        iv, mac, cipher = blob[:16], blob[16:48], blob[48:]
        key = _fernet_material()
        expected = hmac.new(key, iv + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            return ""
        keystream = _keystream(key, iv, len(cipher))
        return bytes(a ^ b for a, b in zip(cipher, keystream)).decode("utf-8")
    except Exception:
        return ""


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, iv + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])
