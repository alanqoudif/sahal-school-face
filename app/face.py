import json
import os

import cv2
import numpy as np

# Larger detector input keeps small faces at the back of a classroom detectable.
DET_SIZE = int(os.environ.get("SAHAL_DET_SIZE", "1024") or 1024)

_analyzer = None


def get_analyzer():
    global _analyzer
    if _analyzer is None:
        from insightface.app import FaceAnalysis

        analyzer = FaceAnalysis(
            name="buffalo_s",
            providers=["CPUExecutionProvider"],
        )
        analyzer.prepare(ctx_id=-1, det_size=(DET_SIZE, DET_SIZE))
        _analyzer = analyzer
    return _analyzer


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("تعذر قراءة الصورة. جرّب صورة JPG أو PNG واضحة.")
    return image


def _largest_face(faces):
    if not faces:
        return None
    return max(faces, key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]))


def extract_embedding(image: np.ndarray, require_quality: bool = True) -> np.ndarray:
    faces = get_analyzer().get(image)
    face = _largest_face(faces)
    if face is None:
        raise ValueError("ما لقينا وجه واضح في الصورة. استخدم صورة أمامية للطالب.")
    if require_quality:
        from app.cues import analyze_cues

        quality = analyze_cues(image, face).get("quality")
        if quality == "ضعيفة":
            raise ValueError("الصورة غير واضحة كفاية. قرّب الوجه وحسّن الإضاءة ثم أعد الرفع.")
    return np.asarray(face.normed_embedding, dtype=np.float32)


def detect_faces(image: np.ndarray):
    return get_analyzer().get(image)


def embedding_to_json(embedding: np.ndarray) -> str:
    return json.dumps(embedding.astype(float).tolist())


def embedding_from_json(raw: str) -> np.ndarray:
    return np.asarray(json.loads(raw), dtype=np.float32)


