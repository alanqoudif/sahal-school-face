import os
from pathlib import Path

import cv2
import numpy as np

from app.db import DATA_DIR

FER_LABELS = (
    "neutral",
    "happiness",
    "surprise",
    "sadness",
    "anger",
    "disgust",
    "fear",
    "contempt",
)

MODEL_PATH = DATA_DIR / "models" / "emotion-ferplus-8.onnx"
_fer_session = None
_fer_failed = False


def empty_cues() -> dict:
    return {"expression": "", "attention": "", "quality": ""}


def analyze_cues(image: np.ndarray, face) -> dict:
    bbox = _bbox(face)
    crop = _safe_crop(image, bbox, pad=0.18)
    quality = _quality_label(image, face, crop)
    yaw, eye_open, smile, mouth_open = _geometry(image, face, crop)
    expression = _expression_label(crop, smile, mouth_open, eye_open)
    attention = _attention_label(yaw, eye_open)
    return {
        "expression": expression,
        "attention": attention,
        "quality": quality,
    }


def _bbox(face):
    box = np.asarray(face.bbox, dtype=float)
    return [int(v) for v in box[:4]]


def _safe_crop(image: np.ndarray, bbox, pad: float = 0.15) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    px, py = int(bw * pad), int(bh * pad)
    x1 = max(0, x1 - px)
    y1 = max(0, y1 - py)
    x2 = min(w, x2 + px)
    y2 = min(h, y2 + py)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return image
    return crop


def _quality_label(image: np.ndarray, face, crop: np.ndarray) -> str:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = _bbox(face)
    area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / max(1, w * h)
    det = float(getattr(face, "det_score", 0) or 0)
    blur = 0.0
    if crop.size:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur < 35 or area_ratio < 0.012 or det < 0.35:
        return "ضعيفة"
    if blur < 85 or area_ratio < 0.035 or det < 0.52:
        return "مقبولة"
    return "واضحة"


def _kps(face):
    kps = getattr(face, "kps", None)
    if kps is None:
        return None
    points = np.asarray(kps, dtype=float)
    if points.shape != (5, 2):
        return None
    return points


def _geometry(image: np.ndarray, face, crop: np.ndarray):
    kps = _kps(face)
    yaw = 0.0
    smile = 0.0
    mouth_open = 0.0
    eye_open = _eye_openness_from_crop(crop)
    if kps is None:
        return yaw, eye_open, smile, mouth_open

    left_eye, right_eye, nose, left_mouth, right_mouth = kps
    mid = (left_eye + right_eye) / 2
    iod = float(np.linalg.norm(right_eye - left_eye)) + 1e-6
    yaw = float((nose[0] - mid[0]) / iod)
    mouth_width = float(np.linalg.norm(right_mouth - left_mouth)) / iod
    mouth_center = (left_mouth + right_mouth) / 2
    nose_to_mouth = float((mouth_center[1] - nose[1]) / iod)
    smile = max(0.0, mouth_width - 0.92)
    mouth_open = max(0.0, nose_to_mouth - 0.78)
    eye_open = max(eye_open, _eye_openness_from_kps(image, kps))
    return abs(yaw), eye_open, smile, mouth_open


def _eye_openness_from_crop(crop: np.ndarray) -> float:
    if crop.size == 0:
        return 0.55
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape[:2]
    band = gray[int(h * 0.22) : int(h * 0.48), int(w * 0.12) : int(w * 0.88)]
    if band.size == 0:
        return 0.55
    edges = cv2.Sobel(band, cv2.CV_64F, 0, 1, ksize=3)
    energy = float(np.mean(np.abs(edges)))
    # Open eyes produce stronger horizontal eyelid edges.
    return float(np.clip(energy / 28.0, 0.0, 1.4))


def _eye_openness_from_kps(image: np.ndarray, kps: np.ndarray) -> float:
    values = []
    h, w = image.shape[:2]
    iod = float(np.linalg.norm(kps[1] - kps[0])) + 1e-6
    radius = max(4, int(iod * 0.28))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    for point in kps[:2]:
        cx, cy = int(point[0]), int(point[1])
        x1, y1 = max(0, cx - radius), max(0, cy - radius)
        x2, y2 = min(w, cx + radius), min(h, cy + int(radius * 0.75))
        patch = gray[y1:y2, x1:x2]
        if patch.size == 0:
            continue
        values.append(float(cv2.Laplacian(patch, cv2.CV_64F).var()) / 180.0)
    if not values:
        return 0.55
    return float(np.clip(np.mean(values), 0.0, 1.4))


def _attention_label(yaw: float, eye_open: float) -> str:
    if eye_open < 0.28:
        return "يبدو نعسان"
    if yaw > 0.34:
        return "شارد"
    return "منتبه"


def _expression_label(crop: np.ndarray, smile: float, mouth_open: float, eye_open: float) -> str:
    scores = _fer_scores(crop)
    if scores:
        label = _expression_from_fer(scores)
        if eye_open < 0.26 and label in {"محايد", "متعب", "منزعج"}:
            return "متعب"
        return label
    if eye_open < 0.26:
        return "متعب"
    if mouth_open > 0.22 and eye_open > 0.7:
        return "متفاجئ"
    if smile > 0.18:
        return "سعيد"
    if smile < 0.04 and mouth_open < 0.06 and eye_open > 0.45:
        return "منزعج" if smile < 0.01 and mouth_open < 0.03 else "محايد"
    return "محايد"


def _expression_from_fer(scores: dict[str, float]) -> str:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top, top_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score < 0.28:
        return "محايد"
    mapping = {
        "happiness": "سعيد",
        "surprise": "متفاجئ",
        "sadness": "متعب",
        "anger": "منزعج",
        "disgust": "منزعج",
        "contempt": "منزعج",
        "fear": "متفاجئ" if top_score - second > 0.08 else "محايد",
        "neutral": "محايد",
    }
    return mapping.get(top, "محايد")


def _fer_scores(crop: np.ndarray) -> dict[str, float] | None:
    session = _get_fer_session()
    if session is None or crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    face = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
    blob = face.astype(np.float32).reshape(1, 1, 64, 64)
    input_name = session.get_inputs()[0].name
    raw = session.run(None, {input_name: blob})[0].reshape(-1)
    probs = _softmax(raw.astype(np.float64))
    return {name: float(probs[i]) for i, name in enumerate(FER_LABELS[: len(probs)])}


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def _get_fer_session():
    global _fer_session, _fer_failed
    if _fer_session is not None or _fer_failed:
        return _fer_session
    path = Path(os.environ.get("SAHAL_FER_MODEL", MODEL_PATH))
    if not path.exists():
        _fer_failed = True
        return None
    try:
        import onnxruntime

        _fer_session = onnxruntime.InferenceSession(
            str(path),
            providers=["CPUExecutionProvider"],
        )
    except Exception:
        _fer_failed = True
        _fer_session = None
    return _fer_session
