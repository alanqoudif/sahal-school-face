import numpy as np

from app.matching import MATCH_THRESHOLD, rank_match


def _vec(values):
    arr = np.asarray(values, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def test_below_threshold_is_rejected():
    catalog = [("a", _vec([1, 0, 0])), ("b", _vec([0, 1, 0]))]
    item, score, status = rank_match(_vec([0, 0, 1]), catalog)
    assert item is None
    assert status == "below"
    assert score < MATCH_THRESHOLD


def test_ambiguous_when_two_faces_too_close():
    query = _vec([1.0, 0.0, 0.0])
    first = _vec([0.98, 0.199, 0.0])
    second = _vec([0.975, 0.222, 0.0])
    item, _, status = rank_match(query, [("first", first), ("second", second)])
    assert status == "ambiguous"
    assert item is None


def test_clear_winner_matches():
    query = _vec([1.0, 0.0, 0.0])
    catalog = [("win", _vec([0.999, 0.04, 0.0])), ("other", _vec([0.0, 1.0, 0.0]))]
    item, score, status = rank_match(query, catalog)
    assert status == "matched"
    assert item == "win"
    assert score >= MATCH_THRESHOLD
