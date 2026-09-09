from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import cv2
import httpx

from app.crypto import decrypt_secret
from app.face import decode_image

ALLOWED_SCHEMES = {"http", "https", "rtsp"}
BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata.internal"}


def classroom_snapshot_url(classroom) -> str | None:
    if classroom.camera_url:
        return validate_camera_url(classroom.camera_url.strip())
    if classroom.camera_ip:
        ip = validate_camera_host(classroom.camera_ip.strip())
        return f"http://{ip}/cgi-bin/snapshot.cgi"
    return None


def validate_camera_host(value: str) -> str:
    host = value.strip()
    if not host or any(ch in host for ch in "/\\ @?#"):
        raise ValueError("IP أو اسم الكاميرا غير صالح.")
    if host.count(":") > 1:
        try:
            ipaddress.IPv6Address(host.strip("[]"))
            return host
        except ValueError as exc:
            raise ValueError("IP الكاميرا غير صالح.") from exc
    if ":" in host:
        name, port = host.rsplit(":", 1)
        if not port.isdigit():
            raise ValueError("منفذ الكاميرا غير صالح.")
        validate_camera_host(name)
        return host
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        if all(ch.isalnum() or ch in ".-" for ch in host) and host.replace(".", ""):
            return host
        raise ValueError("IP أو اسم الكاميرا غير صالح.")


def validate_camera_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("رابط الكاميرا لازم يكون http أو https أو rtsp.")
    host = parsed.hostname
    if not host:
        raise ValueError("رابط الكاميرا ناقص.")
    if host.lower() in BLOCKED_HOSTS:
        raise ValueError("رابط الكاميرا غير مسموح.")
    return url


def fetch_camera_frame(classroom):
    kind = (classroom.camera_kind or "snapshot").lower()
    url = classroom_snapshot_url(classroom)
    if not url:
        raise ValueError("أضف IP الكاميرا أو رابط الـ API الخاص بالصف.")

    if kind == "rtsp":
        capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        frame = None
        ok = False
        for _ in range(5):
            ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            raise ValueError("ما قدرنا نقرأ بث RTSP. تأكد من الرابط وصلاحيات الكاميرا.")
        return frame

    auth = None
    password = decrypt_secret(classroom.camera_password)
    if classroom.camera_user:
        auth = (classroom.camera_user, password)
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            response = client.get(url, auth=auth)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"الكاميرا ما ردّت على الـ API: {exc}") from exc
    return decode_image(response.content)
