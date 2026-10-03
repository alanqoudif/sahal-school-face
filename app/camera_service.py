"""Persistent RTSP camera service (EZVIZ and other RTSP cameras).

One background thread per camera keeps a single RTSP connection open, decodes
frames, and stores only the latest one in memory. HTTP handlers never touch RTSP;
they read the cached frame. Credentials live only in this module's config and are
never logged, serialized, or returned by any API.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

# Must be set before OpenCV opens its first FFmpeg capture. TCP avoids the packet
# loss UDP shows on Wi-Fi/busy LANs; the log level is silenced so FFmpeg never
# prints connection details.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

logger = logging.getLogger("sahal.camera")

BACKOFF_SECONDS = (1, 2, 5, 10, 30)
OPEN_TIMEOUT_MS = 8000
READ_TIMEOUT_MS = 6000
MAX_GRAB_FAILURES = 3


@dataclass(frozen=True)
class CameraConfig:
    key: str
    camera_id: str
    name: str
    host: str
    port: int
    username: str
    password: str
    stream_path: str
    max_fps: float = 10.0
    frame_max_age: float = 10.0

    @property
    def configured(self) -> bool:
        return bool(self.host)

    def rtsp_url(self) -> str:
        """Built on demand and only ever handed to OpenCV. Never log or return it."""
        path = self.stream_path if self.stream_path.startswith("/") else f"/{self.stream_path}"
        auth = ""
        if self.username:
            auth = f"{quote(self.username, safe='')}:{quote(self.password, safe='')}@"
        return f"rtsp://{auth}{self.host}:{self.port}{path}"

    def redact(self, text: str) -> str:
        for secret in (self.password, quote(self.password, safe="")):
            if secret:
                text = text.replace(secret, "***")
        return re.sub(r"rtsp://[^@/\s]*@", "rtsp://***@", text)


def load_ezviz_config() -> CameraConfig:
    env = os.environ.get
    try:
        port = int(env("CAMERA_PORT", "554") or 554)
    except ValueError:
        port = 554
    try:
        max_fps = float(env("CAMERA_MAX_FPS", "10") or 10)
    except ValueError:
        max_fps = 10.0
    return CameraConfig(
        key="ezviz",
        camera_id=env("CAMERA_ID", "ezviz_ty1").strip() or "ezviz_ty1",
        name=env("CAMERA_NAME", "EZVIZ TY1").strip() or "EZVIZ TY1",
        host=env("CAMERA_HOST", "").strip(),
        port=port,
        username=env("CAMERA_USERNAME", "admin").strip(),
        password=env("CAMERA_PASSWORD", ""),
        stream_path=env("CAMERA_STREAM_PATH", "/ch1/main").strip() or "/ch1/main",
        max_fps=max(1.0, max_fps),
    )


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()  # noqa: S324 - RTSP digest auth mandates MD5


def probe_rtsp_auth(cfg: CameraConfig, timeout: float = 4.0) -> str:
    """Send RTSP DESCRIBE (Digest/Basic) to classify a failed open.

    Returns "ok", "unauthorized", "not_found" or "unknown". Credentials go only to
    the camera socket.
    """
    uri = f"rtsp://{cfg.host}:{cfg.port}{cfg.stream_path if cfg.stream_path.startswith('/') else '/' + cfg.stream_path}"

    def exchange(sock, cseq: int, auth_header: str | None):
        lines = [f"DESCRIBE {uri} RTSP/1.0", f"CSeq: {cseq}", "Accept: application/sdp"]
        if auth_header:
            lines.append(f"Authorization: {auth_header}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 16384:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        head = data.decode("latin-1", "replace")
        match = re.match(r"RTSP/1\.\d\s+(\d{3})", head)
        return (int(match.group(1)) if match else 0), head

    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            status, head = exchange(sock, 1, None)
            if status == 200:
                return "ok"
            if status == 404:
                return "not_found"
            if status != 401:
                return "unknown"
            digest = re.search(r"WWW-Authenticate:\s*Digest\s+(.*)", head, re.I)
            if digest:
                params = dict(re.findall(r'(\w+)="?([^",\r\n]*)"?', digest.group(1)))
                realm, nonce = params.get("realm", ""), params.get("nonce", "")
                ha1 = _md5(f"{cfg.username}:{realm}:{cfg.password}")
                ha2 = _md5(f"DESCRIBE:{uri}")
                if "auth" in params.get("qop", ""):
                    cnonce, nc = os.urandom(8).hex(), "00000001"
                    response = _md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}")
                    extra = f', qop=auth, nc={nc}, cnonce="{cnonce}"'
                else:
                    response = _md5(f"{ha1}:{nonce}:{ha2}")
                    extra = ""
                header = (
                    f'Digest username="{cfg.username}", realm="{realm}", nonce="{nonce}", '
                    f'uri="{uri}", response="{response}"{extra}'
                )
            elif re.search(r"WWW-Authenticate:\s*Basic", head, re.I):
                token = base64.b64encode(f"{cfg.username}:{cfg.password}".encode()).decode()
                header = f"Basic {token}"
            else:
                return "unknown"
            status, _ = exchange(sock, 2, header)
            if status == 200:
                return "ok"
            if status == 401:
                return "unauthorized"
            if status == 404:
                return "not_found"
            return "unknown"
    except (OSError, ValueError):
        return "unknown"


class CameraService:
    def __init__(self, config: CameraConfig):
        self.config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._seq = 0
        self._frame_ts: float | None = None
        self._jpeg_cache: dict[tuple[int, int, int], bytes] = {}
        self._status = "disabled" if not config.configured else "connecting"
        self._message = "" if config.configured else "الكاميرا غير مضبوطة (CAMERA_HOST)."
        self._last_connected: float | None = None
        self._reconnects = 0
        self._fps = 0.0
        self._size: tuple[int, int] | None = None
        self._capture: cv2.VideoCapture | None = None

    @property
    def enabled(self) -> bool:
        return self.config.configured

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """startFrameLoop(): launch the background connect/decode/reconnect thread."""
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"camera-{self.config.key}", daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._stop.set()
        capture = self._capture
        if capture is not None:
            try:
                capture.release()
            except Exception:  # noqa: BLE001
                pass
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        if self.enabled:
            self._set_status("offline", "تم إيقاف الخدمة.")

    def connect(self) -> None:
        self.start()

    def reconnect(self) -> None:
        self.disconnect()
        self._reconnects = 0
        self.start()

    # ---- public reads (never touch the camera) ---------------------------

    def get_status(self) -> dict:
        cfg = self.config
        with self._lock:
            age = None if self._frame_ts is None else time.time() - self._frame_ts
            status = self._status
            # a stalled loop that hasn't flagged itself yet should not read as online
            if status == "online" and age is not None and age > cfg.frame_max_age:
                status = "stream_error"
            return {
                "status": status,
                "message": self._message,
                "camera": cfg.name,
                "cameraId": cfg.camera_id,
                "ip": cfg.host,
                "lastFrameAt": _iso(self._frame_ts),
                "lastConnectedAt": _iso(self._last_connected),
                "reconnectAttempts": self._reconnects,
                "width": self._size[0] if self._size else None,
                "height": self._size[1] if self._size else None,
                "fps": round(self._fps, 1) if self._fps else None,
            }

    def get_latest_frame(self) -> tuple[np.ndarray, int, float] | None:
        """Return (frame, sequence, unix_ts) or None if absent/stale."""
        with self._lock:
            if self._frame is None or self._frame_ts is None:
                return None
            if time.time() - self._frame_ts > self.config.frame_max_age:
                return None
            return self._frame, self._seq, self._frame_ts

    def get_jpeg(self, max_width: int = 0, quality: int = 85, after_seq: int = -1):
        """Return (jpeg_bytes, seq, ts) for the latest frame, or None.

        Encoded once per (frame, size) and shared by all viewers. With `after_seq`,
        returns None unless a newer frame exists.
        """
        latest = self.get_latest_frame()
        if latest is None:
            return None
        frame, seq, ts = latest
        if seq <= after_seq:
            return None
        key = (seq, max_width, quality)
        with self._lock:
            cached = self._jpeg_cache.get(key)
        if cached is None:
            image = frame
            if max_width and image.shape[1] > max_width:
                scale = max_width / image.shape[1]
                image = cv2.resize(image, (max_width, int(image.shape[0] * scale)), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                return None
            cached = buf.tobytes()
            with self._lock:
                if len(self._jpeg_cache) > 6:
                    self._jpeg_cache.clear()
                self._jpeg_cache[key] = cached
        return cached, seq, ts

    # ---- internals -------------------------------------------------------

    def _set_status(self, status: str, message: str = "") -> None:
        with self._lock:
            self._status = status
            self._message = message

    def _run(self) -> None:
        cfg = self.config
        attempt = 0
        logger.info("[Camera] Connecting to %s", cfg.name)
        while not self._stop.is_set():
            self._set_status("connecting" if attempt == 0 else "reconnecting")
            got_frames = False
            try:
                got_frames = self._session()
            except Exception as exc:  # noqa: BLE001 - the loop must never die
                logger.error("[Camera] Frame decoding error: %s", cfg.redact(f"{type(exc).__name__}: {exc}"))
                self._set_status("stream_error", "خطأ في فك ترميز البث.")
            if self._stop.is_set():
                break
            attempt = 0 if got_frames else attempt + 1
            delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            with self._lock:
                self._reconnects += 1
            logger.info("[Camera] Reconnecting in %ss...", delay)
            self._stop.wait(delay)

    def _session(self) -> bool:
        """One connection lifetime. Returns True if at least one frame was received."""
        cfg = self.config
        capture = cv2.VideoCapture(
            cfg.rtsp_url(),
            cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS],
        )
        self._capture = capture
        try:
            if not capture.isOpened():
                self._diagnose_open_failure()
                return False
            logger.info("[Camera] RTSP connection established")
            return self._read_loop(capture)
        finally:
            self._capture = None
            capture.release()

    def _diagnose_open_failure(self) -> None:
        cfg = self.config
        try:
            socket.create_connection((cfg.host, cfg.port), timeout=3).close()
        except OSError:
            logger.warning("[Camera] Camera unreachable (%s:%s)", cfg.host, cfg.port)
            self._set_status("offline", "الكاميرا غير متصلة بالشبكة.")
            return
        verdict = probe_rtsp_auth(cfg)
        if verdict == "unauthorized":
            logger.error("[Camera] Authentication failed")
            self._set_status("authentication_failed", "اسم المستخدم أو رمز التحقق غير صحيح.")
        elif verdict == "not_found":
            logger.error("[Camera] Stream path not found")
            self._set_status("stream_error", "مسار البث غير صحيح (CAMERA_STREAM_PATH).")
        else:
            logger.error("[Camera] Could not open RTSP stream")
            self._set_status("stream_error", "تعذر فتح بث RTSP.")

    def _read_loop(self, capture: cv2.VideoCapture) -> bool:
        cfg = self.config
        min_gap = 1.0 / cfg.max_fps
        last_store = 0.0
        failures = 0
        got_any = False
        window_start, window_frames = time.time(), 0
        while not self._stop.is_set():
            # grab() drains the stream at camera rate (keeps latency low);
            # retrieve() converts only as often as max_fps needs.
            if not capture.grab():
                failures += 1
                if failures >= MAX_GRAB_FAILURES:
                    logger.warning("[Camera] Stream disconnected")
                    self._set_status("offline", "انقطع البث.")
                    return got_any
                time.sleep(0.2)
                continue
            failures = 0
            window_frames += 1
            tick = time.time()
            if tick - window_start >= 2.0:
                with self._lock:
                    self._fps = window_frames / (tick - window_start)
                window_start, window_frames = tick, 0
            if tick - last_store < min_gap:
                continue
            ok, frame = capture.retrieve()
            if not ok or frame is None:
                logger.warning("[Camera] Frame decoding error")
                continue
            last_store = tick
            with self._lock:
                self._frame = frame
                self._seq += 1
                self._frame_ts = tick
                self._size = (frame.shape[1], frame.shape[0])
                self._status = "online"
                self._message = ""
                self._last_connected = tick
            if not got_any:
                got_any = True
                logger.info("[Camera] First frame received (%dx%d)", frame.shape[1], frame.shape[0])
        return got_any


_services: dict[str, CameraService] = {}


def init_camera_services() -> None:
    cfg = load_ezviz_config()
    service = CameraService(cfg)
    _services[cfg.key] = service
    if service.enabled:
        service.start()
    else:
        logger.info("[Camera] CAMERA_HOST not set; EZVIZ camera disabled")


def shutdown_camera_services() -> None:
    for service in _services.values():
        service.disconnect()


def get_camera_service(key: str = "ezviz") -> CameraService | None:
    return _services.get(key)
