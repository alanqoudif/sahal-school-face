import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Classroom, Student


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


def test_api_requires_login(client: TestClient):
    response = client.get("/api/students")
    assert response.status_code == 401


def test_login_and_manual_attendance(client: TestClient):
    bad = client.post("/api/login", data={"password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/login", data={"password": "test-admin"})
    assert ok.status_code == 200
    assert client.get("/api/session").json()["authenticated"] is True

    created = client.post("/api/classrooms", data={"grade": "عاشر", "section": "الأولى"})
    assert created.status_code == 200
    classroom_id = created.json()["classroom"]["id"]

    db = SessionLocal()
    try:
        classroom = db.get(Classroom, classroom_id)
        student = Student(
            name="أحمد",
            student_number="9001",
            class_name="عاشر",
            section="الأولى",
            classroom_id=classroom.id,
            photo_path="/tmp/none.jpg",
            embedding="[]",
        )
        db.add(student)
        db.commit()
        db.refresh(student)
        student_id = student.id
    finally:
        db.close()

    listed = client.get("/api/attendance")
    assert listed.status_code == 200
    assert listed.json()["absent_count"] >= 1

    mark = client.post("/api/attendance/mark", data={"student_id": student_id, "present": "1"})
    assert mark.status_code == 200
    after = client.get("/api/attendance").json()
    assert any(row["student_id"] == student_id for row in after["records"])

    unmark = client.post("/api/attendance/mark", data={"student_id": student_id, "present": "0"})
    assert unmark.status_code == 200


def test_photos_not_public_static(client: TestClient):
    response = client.get("/photos/anything.jpg", follow_redirects=False)
    assert response.status_code in {401, 404, 307, 303}
    photo = client.get("/api/students/1/photo", follow_redirects=False)
    assert photo.status_code == 401
