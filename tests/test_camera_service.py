import hashlib
import socket
import threading
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import camera_service as cs
from app.camera_service import CameraConfig, CameraService, probe_rtsp_auth


def make_config(**overrides) -> CameraConfig:
    base = dict(
        key="ezviz", camera_id="ezviz_ty1", name="EZVIZ TY1", host="127.0.0.1", port=1,
        username="admin", password="p@ss/word", stream_path="/ch1/main",
    )
    base.update(overrides)
    return CameraConfig(**base)


def wait_for(predicate, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_url_is_built_server_side_and_redacted():
    cfg = make_config()
    assert cfg.rtsp_url() == "rtsp://admin:p%40ss%2Fword@127.0.0.1:1/ch1/main"
    redacted = cfg.redact(f"failed {cfg.rtsp_url()} pw=p@ss/word")
    assert "p%40ss" not in redacted and "p@ss/word" not in redacted and "admin:" not in redacted


def fake_rtsp_server(password: str):
    """Minimal RTSP server that demands Digest auth on DESCRIBE."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(4)

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                while True:
                    data = conn.recv(4096).decode("latin-1")
                    if not data:
                        break
                    uri = data.split()[1]
                    if "Authorization: Digest" in data:
                        ha1 = hashlib.md5(f"admin:cam:{password}".encode()).hexdigest()
                        ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
                        expect = hashlib.md5(f"{ha1}:abc123:{ha2}".encode()).hexdigest()
                        code = "200 OK" if f'response="{expect}"' in data else "401 Unauthorized"
                        conn.sendall(f"RTSP/1.0 {code}\r\nCSeq: 2\r\n\r\n".encode())
                    else:
                        conn.sendall(
                            b'RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\nWWW-Authenticate: Digest realm="cam", nonce="abc123"\r\n\r\n'
                        )

    threading.Thread(target=serve, daemon=True).start()
    return server


def test_probe_distinguishes_good_and_bad_password():
    server = fake_rtsp_server("right")
    port = server.getsockname()[1]
    try:
        assert probe_rtsp_auth(make_config(port=port, password="right")) == "ok"
        assert probe_rtsp_auth(make_config(port=port, password="wrong")) == "unauthorized"
    finally:
        server.close()


def test_unreachable_camera_goes_offline_without_crashing():
    service = CameraService(make_config())
    service.start()
    try:
        assert wait_for(lambda: service.get_status()["status"] == "offline")
        assert service.get_latest_frame() is None
        assert service.get_jpeg() is None
        assert wait_for(lambda: service.get_status()["reconnectAttempts"] >= 1)
    finally:
        service.disconnect()


def test_wrong_password_reports_authentication_failed(monkeypatch):
    server = fake_rtsp_server("right")
    port = server.getsockname()[1]
    monkeypatch.setattr(CameraConfig, "rtsp_url", lambda self: "rtsp://127.0.0.1:%d/none" % port)
    service = CameraService(make_config(port=port, password="wrong"))
    service.start()
    try:
        assert wait_for(lambda: service.get_status()["status"] == "authentication_failed", 30)
    finally:
        service.disconnect()
        server.close()


@pytest.fixture
def video_file(tmp_path):
    path = str(tmp_path / "cam.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 15, (640, 360))
    for i in range(150):
        frame = np.full((360, 640, 3), i % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def test_service_decodes_frames_and_serves_jpeg(monkeypatch, video_file):
    monkeypatch.setattr(CameraConfig, "rtsp_url", lambda self: video_file)
    service = CameraService(make_config())
    service.start()
    try:
        assert wait_for(lambda: service.get_status()["status"] == "online")
        status = service.get_status()
        assert (status["width"], status["height"]) == (640, 360)
        assert "password" not in str(status).lower() and "rtsp://" not in str(status)
        jpeg, seq, _ = service.get_jpeg(max_width=320)
        decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 320
        assert service.get_jpeg(after_seq=10**9) is None
    finally:
        service.disconnect()


def test_camera_endpoints(monkeypatch, video_file):
    from app.db import init_db
    from app.main import app

    monkeypatch.setattr(CameraConfig, "rtsp_url", lambda self: video_file)
    init_db()
    service = CameraService(make_config())
    cs._services["ezviz"] = service
    service.start()
    try:
        client = TestClient(app)
        assert client.get("/api/cameras/ezviz/status").status_code == 401
        assert client.get("/api/cameras/ezviz/frame").status_code == 401
        client.post("/api/login", data={"password": "test-admin"})
        assert wait_for(lambda: client.get("/api/cameras/ezviz/status").json()["status"] == "online")
        status = client.get("/api/cameras/ezviz/status")
        assert "p@ss" not in status.text and "rtsp" not in status.text
        frame = client.get("/api/cameras/ezviz/frame")
        assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"
        classroom = client.post("/api/classrooms", data={"grade": "camtest", "section": "A"}).json()["classroom"]
        monkeypatch.setattr("app.main.detect_faces", lambda image: [])
        result = client.post(f"/api/cameras/ezviz/recognize?classroom_id={classroom['id']}&include_frame=1")
        body = result.json()
        assert result.status_code == 200
        assert body["recognized"] is False and body["faces"] == []
        assert body["camera"] == "ezviz_ty1" and body["frame_width"] == 640 and body["frame_jpeg"]
        assert client.post("/api/cameras/ezviz/recognize?classroom_id=99999").status_code == 404
    finally:
        service.disconnect()
        cs._services.clear()


def test_endpoints_when_camera_not_configured():
    from app.db import init_db
    from app.main import app

    init_db()
    cs._services["ezviz"] = CameraService(make_config(host=""))
    client = TestClient(app)
    client.post("/api/login", data={"password": "test-admin"})
    assert client.get("/api/cameras/ezviz/status").json()["status"] == "disabled"
    assert client.get("/api/cameras/ezviz/frame").status_code == 503
    cs._services.clear()
