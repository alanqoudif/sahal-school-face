from __future__ import annotations

import hashlib
import hmac

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.settings import ADMIN_PASSWORD

PUBLIC_EXACT = {"/login", "/api/login", "/api/session"}
PUBLIC_PREFIXES = ("/assets/", "/static/")


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("auth"))


def password_matches(given: str) -> bool:
    given_digest = hashlib.sha256(given.encode("utf-8")).digest()
    expected = hashlib.sha256(ADMIN_PASSWORD.encode("utf-8")).digest()
    return hmac.compare_digest(given_digest, expected)


def login_user(request: Request) -> None:
    request.session["auth"] = True


def logout_user(request: Request) -> None:
    request.session.clear()


def unauthorized(request: Request, spa: bool):
    if request.url.path.startswith("/api") or request.url.path.startswith("/attendance/export"):
        return JSONResponse({"ok": False, "error": "يلزم تسجيل الدخول"}, status_code=401)
    if spa:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/login", status_code=303)
