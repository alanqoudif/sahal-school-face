from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.face import embedding_from_json
from app.models import Student

_embeddings: dict[int, np.ndarray] = {}


def invalidate_student(student_id: int | None) -> None:
    if student_id is not None:
        _embeddings.pop(student_id, None)


def classroom_catalog(db: Session, classroom_id: int) -> list[tuple[Student, np.ndarray]]:
    students = db.scalars(select(Student).where(Student.classroom_id == classroom_id)).all()
    catalog: list[tuple[Student, np.ndarray]] = []
    for student in students:
        stored = _embeddings.get(student.id)
        if stored is None and student.embedding:
            stored = embedding_from_json(student.embedding)
            _embeddings[student.id] = stored
        if stored is not None:
            catalog.append((student, stored))
    return catalog
