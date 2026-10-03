import os
import secrets
from functools import lru_cache

from app.db import DATA_DIR

TZ_NAME = os.environ.get("SAHAL_TZ") or os.environ.get("TZ") or ""
ADMIN_PASSWORD = os.environ.get("SAHAL_ADMIN_PASSWORD", "sahal")
SESSION_HOURS = int(os.environ.get("SAHAL_SESSION_HOURS", "12"))
FACE_RECOGNITION_INTERVAL_MS = max(250, int(os.environ.get("FACE_RECOGNITION_INTERVAL_MS", "1000") or 1000))
FACE_CUES_ENABLED = os.environ.get("SAHAL_FACE_CUES", "1").strip() not in {"0", "false", "no"}


@lru_cache(maxsize=1)
def secret_key() -> str:
    env = os.environ.get("SAHAL_SECRET_KEY", "").strip()
    if env:
        return env
    path = DATA_DIR / ".secret"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value
