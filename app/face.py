import json
import cv2
import numpy as np

MATCH_THRESHOLD = 0.45

_analyzer = None


def get_analyzer():
    global _analyzer
    if _analyzer is None:
        from insightface.app import FaceAnalysis

        analyzer = FaceAnalysis(
            name="buffalo_s",
            providers=["CPUExecutionProvider"],
        )
        analyzer.prepare(ctx_id=-1, det_size=(640, 640))
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


def extract_embedding(image: np.ndarray) -> np.ndarray:
    faces = get_analyzer().get(image)
    face = _largest_face(faces)
    if face is None:
        raise ValueError("ما لقينا وجه واضح في الصورة. استخدم صورة أمامية للطالب.")
    return np.asarray(face.normed_embedding, dtype=np.float32)


def detect_faces(image: np.ndarray):
    return get_analyzer().get(image)


def embedding_to_json(embedding: np.ndarray) -> str:
    return json.dumps(embedding.astype(float).tolist())


def embedding_from_json(raw: str) -> np.ndarray:
    return np.asarray(json.loads(raw), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
