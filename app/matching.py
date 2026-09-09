from __future__ import annotations

import os

import numpy as np

MATCH_THRESHOLD = float(os.environ.get("SAHAL_MATCH_THRESHOLD", "0.52"))
MATCH_MARGIN = float(os.environ.get("SAHAL_MATCH_MARGIN", "0.08"))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def rank_match(embedding: np.ndarray, catalog: list[tuple[object, np.ndarray]]):
    """Return (item, score, status) where status is matched | below | ambiguous | empty."""
    if not catalog:
        return None, 0.0, "empty"
    scored = [(item, cosine_similarity(embedding, stored)) for item, stored in catalog]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    best_item, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else -1.0
    if best_score < MATCH_THRESHOLD:
        return None, best_score, "below"
    if second_score >= 0 and (best_score - second_score) < MATCH_MARGIN:
        return None, best_score, "ambiguous"
    return best_item, best_score, "matched"
