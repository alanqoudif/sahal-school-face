import cv2
import httpx

from app.face import decode_image


def classroom_snapshot_url(classroom) -> str | None:
    if classroom.camera_url:
        return classroom.camera_url.strip()
    if classroom.camera_ip:
        ip = classroom.camera_ip.strip()
        return f"http://{ip}/cgi-bin/snapshot.cgi"
    return None


def fetch_camera_frame(classroom):
    kind = (classroom.camera_kind or "snapshot").lower()
    url = classroom_snapshot_url(classroom)
    if not url:
        raise ValueError("أضف IP الكاميرا أو رابط الـ API الخاص بالصف.")

    if kind == "rtsp":
        capture = cv2.VideoCapture(url)
        ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            raise ValueError("ما قدرنا نقرأ بث RTSP. تأكد من الرابط وصلاحيات الكاميرا.")
        return frame

    auth = None
    if classroom.camera_user:
        auth = (classroom.camera_user, classroom.camera_password or "")
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            response = client.get(url, auth=auth)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"الكاميرا ما ردّت على الـ API: {exc}") from exc
    return decode_image(response.content)
