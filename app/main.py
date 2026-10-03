import asyncio
import base64
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import is_authenticated, is_public_path, login_user, logout_user, password_matches, unauthorized
from app.camera_service import get_camera_service, init_camera_services, shutdown_camera_services
from app.cameras import fetch_camera_frame, validate_camera_host, validate_camera_url
from app.catalog import classroom_catalog, invalidate_student
from app.clock import now, today
from app.crypto import encrypt_secret
from app.cues import analyze_cues, empty_cues
from app.db import BASE_DIR, PHOTOS_DIR, get_db, init_db
from app.excel_export import attendance_workbook
from app.face import decode_image, detect_faces, embedding_to_json, extract_embedding
from app.matching import rank_match
from app.models import DEFAULT_SECTION, Attendance, Classroom, Student
from app.seats import classroom_seats, seat_label
from app.settings import FACE_CUES_ENABLED, FACE_RECOGNITION_INTERVAL_MS, SESSION_HOURS, secret_key

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
logger = logging.getLogger("sahal")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("SAHAL_ADMIN_PASSWORD"):
        logger.warning("SAHAL_ADMIN_PASSWORD غير معيّن. استخدم كلمة الدخول الافتراضية من ملف البيئة.")
    init_camera_services()
    yield
    shutdown_camera_services()


app = FastAPI(title="سهل", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def require_login(request: Request, call_next):
    if is_public_path(request.url.path):
        return await call_next(request)
    if is_authenticated(request):
        return await call_next(request)
    return unauthorized(request, uses_spa())


app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key(),
    session_cookie="sahal_session",
    same_site="lax",
    https_only=False,
    max_age=SESSION_HOURS * 3600,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def uses_spa() -> bool:
    return (FRONTEND_DIST / "index.html").exists()


def spa_page():
    return FileResponse(FRONTEND_DIST / "index.html")


def render(request: Request, name: str, **context):
    return templates.TemplateResponse(request, name, context)


def page_or_spa(request: Request, name: str, **context):
    if uses_spa():
        return spa_page()
    return render(request, name, **context)


def photo_url(student: Student) -> str:
    return f"/api/students/{student.id}/photo"


def count_students(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Student)) or 0


def count_present(db: Session, day: date, classroom_id: int | None = None) -> int:
    return len(present_student_ids(db, day, classroom_id))


def save_photo(image, student_number: str) -> str:
    filename = f"{student_number}_{uuid.uuid4().hex[:8]}.jpg"
    path = PHOTOS_DIR / filename
    cv2.imwrite(str(path), image)
    return str(path)


def get_or_create_classroom(db: Session, grade: str, section: str) -> Classroom:
    grade = grade.strip()
    section = (section or DEFAULT_SECTION).strip() or DEFAULT_SECTION
    classroom = db.scalar(select(Classroom).where(Classroom.grade == grade, Classroom.section == section))
    if classroom is None:
        classroom = Classroom(grade=grade, section=section)
        db.add(classroom)
        db.flush()
    return classroom


def student_payload(student: Student) -> dict:
    classroom = student.classroom
    return {
        "id": student.id,
        "name": student.name,
        "student_number": student.student_number,
        "class_name": student.class_name,
        "section": student.section or DEFAULT_SECTION,
        "classroom_id": student.classroom_id,
        "classroom_title": classroom.title if classroom else f"الصف {student.class_name} — الشعبة {student.section or DEFAULT_SECTION}",
        "seat_code": student.seat_code,
        "seat_label": seat_label(student.seat_code),
        "photo": photo_url(student),
    }


def present_student_ids(db: Session, day: date, classroom_id: int | None = None) -> set[int]:
    query = select(Attendance.student_id).where(Attendance.day == day)
    if classroom_id:
        query = query.join(Student).where(
            or_(Attendance.classroom_id == classroom_id, Student.classroom_id == classroom_id)
        )
    return set(db.scalars(query).all())


def classroom_payload(classroom: Classroom, db: Session, day: date | None = None) -> dict:
    day = day or today()
    students = list(classroom.students)
    present_ids = present_student_ids(db, day, classroom.id)
    occupied = {student.seat_code: student_payload(student) for student in students if student.seat_code}
    return {
        "id": classroom.id,
        "grade": classroom.grade,
        "section": classroom.section,
        "title": classroom.title,
        "rows": classroom.rows or 4,
        "camera_ip": classroom.camera_ip or "",
        "camera_url": classroom.camera_url or "",
        "camera_user": classroom.camera_user or "",
        "camera_kind": classroom.camera_kind or "snapshot",
        "has_camera": bool(classroom.camera_url or classroom.camera_ip),
        "student_count": len(students),
        "present_today": len(present_ids),
        "seats": [
            {
                **seat,
                "student": occupied.get(seat["code"]),
                "present": occupied[seat["code"]]["id"] in present_ids if seat["code"] in occupied else False,
            }
            for seat in classroom_seats(classroom.rows or 4)
        ],
    }


def _attendance_payload(record: Attendance) -> dict:
    student = record.student
    classroom = record.classroom or student.classroom
    return {
        "id": record.id,
        "student_id": student.id,
        "name": student.name,
        "class_name": student.class_name,
        "section": student.section or DEFAULT_SECTION,
        "student_number": student.student_number,
        "time": record.checked_in_at.strftime("%H:%M"),
        "photo": photo_url(student),
        "seat_label": seat_label(student.seat_code),
        "classroom_id": record.classroom_id,
        "classroom_title": classroom.title if classroom else student.class_name,
        "expression": record.expression or "",
        "attention": record.attention or "",
        "quality": record.quality or "",
        "source": record.source or "camera",
    }


def recognize_image(frame, db: Session, classroom: Classroom | None) -> dict:
    """classroom=None matches against every student in the school."""
    classroom_id = classroom.id if classroom else None
    catalog = classroom_catalog(db, classroom_id)
    day = today()
    stamped = now()
    marked_ids: set[int] = set()
    faces_payload = []
    total_query = select(func.count()).select_from(Student)
    if classroom_id is not None:
        total_query = total_query.where(Student.classroom_id == classroom_id)
    total_students = db.scalar(total_query) or 0

    for face in detect_faces(frame):
        embedding = np.asarray(face.normed_embedding, dtype=np.float32)
        match, score, status = rank_match(embedding, catalog)
        cues = analyze_cues(frame, face) if FACE_CUES_ENABLED else empty_cues()
        item = {
            "bbox": [int(v) for v in face.bbox.tolist()],
            "known": False,
            "name": "غير معروف",
            "student_id": None,
            "student_number": None,
            "class_name": None,
            "section": None,
            "confidence": round(score, 3) if score > 0 else 0,
            "already_marked": False,
            "marked_now": False,
            "photo": None,
            "seat_label": None,
            **cues,
        }
        if status == "ambiguous":
            item["name"] = "غير مؤكد"
        if match and status == "matched":
            existing = db.scalar(
                select(Attendance).where(Attendance.student_id == match.id, Attendance.day == day)
            )
            marked_now = False
            if existing is None and match.id not in marked_ids:
                db.add(
                    Attendance(
                        student_id=match.id,
                        classroom_id=classroom_id or match.classroom_id,
                        day=day,
                        checked_in_at=stamped,
                        expression=cues["expression"],
                        attention=cues["attention"],
                        quality=cues["quality"],
                        source="camera",
                    )
                )
                marked_now = True
                marked_ids.add(match.id)
            elif existing is not None and not (existing.expression or existing.attention or existing.quality):
                existing.expression = cues["expression"]
                existing.attention = cues["attention"]
                existing.quality = cues["quality"]
            item.update(
                {
                    "known": True,
                    "name": match.name,
                    "student_id": match.id,
                    "student_number": match.student_number,
                    "class_name": match.class_name,
                    "section": match.section,
                    "confidence": round(score, 3),
                    "already_marked": existing is not None or marked_now,
                    "marked_now": marked_now,
                    "photo": photo_url(match),
                    "seat_label": seat_label(match.seat_code),
                }
            )
        faces_payload.append(item)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    recent_query = select(Attendance).where(Attendance.day == day).order_by(Attendance.checked_in_at.desc())
    if classroom_id is not None:
        recent_query = recent_query.where(Attendance.classroom_id == classroom_id)
    return {
        "faces": faces_payload,
        "present_today": count_present(db, day, classroom_id),
        "total_students": total_students,
        "recent": [_attendance_payload(record) for record in db.scalars(recent_query).all()[:8]],
        "classroom_id": classroom_id,
    }


def _parse_day(value: str | None) -> date:
    if not value:
        return today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return today()


def _students_error(message: str) -> RedirectResponse:
    return RedirectResponse(f"/students?error={quote(message)}", status_code=303)


@app.get("/assets/{asset_path:path}", include_in_schema=False)
def frontend_asset(asset_path: str):
    file_path = (FRONTEND_DIST / "assets" / asset_path).resolve()
    assets_root = (FRONTEND_DIST / "assets").resolve()
    if file_path.exists() and file_path.is_relative_to(assets_root):
        return FileResponse(file_path)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


@app.get("/api/session")
def api_session(request: Request):
    return {"authenticated": is_authenticated(request), "today": today().isoformat()}


@app.post("/api/login")
async def api_login(request: Request, password: str = Form(...)):
    if not password_matches(password):
        return JSONResponse({"ok": False, "error": "كلمة المرور غير صحيحة"}, status_code=401)
    login_user(request)
    return {"ok": True}


@app.post("/api/logout")
async def api_logout(request: Request):
    logout_user(request)
    return {"ok": True}


@app.get("/", include_in_schema=False)
def home():
    if uses_spa():
        return spa_page()
    return RedirectResponse("/students", status_code=303)


@app.get("/students", response_class=HTMLResponse)
@app.get("/camera", response_class=HTMLResponse)
@app.get("/attendance", response_class=HTMLResponse)
@app.get("/classes", response_class=HTMLResponse)
@app.get("/classes/{classroom_id}", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def spa_routes(request: Request, classroom_id: int | None = None):
    return page_or_spa(request, "students.html", active="students")


@app.get("/api/classrooms")
def api_classrooms(db: Session = Depends(get_db)):
    classrooms = db.scalars(select(Classroom).order_by(Classroom.grade, Classroom.section)).all()
    return {"classrooms": [classroom_payload(item, db) for item in classrooms]}


@app.post("/api/classrooms")
def api_create_classroom(
    grade: str = Form(...),
    section: str = Form(DEFAULT_SECTION),
    db: Session = Depends(get_db),
):
    grade = grade.strip()
    section = (section or DEFAULT_SECTION).strip() or DEFAULT_SECTION
    if not grade:
        return JSONResponse({"ok": False, "error": "اكتب اسم الصف"}, status_code=400)
    existing = db.scalar(select(Classroom).where(Classroom.grade == grade, Classroom.section == section))
    if existing:
        return JSONResponse({"ok": False, "error": "هذا الصف والشعبة موجودين"}, status_code=400)
    classroom = Classroom(grade=grade, section=section)
    db.add(classroom)
    db.commit()
    db.refresh(classroom)
    return {"ok": True, "classroom": classroom_payload(classroom, db)}


@app.get("/api/classrooms/{classroom_id}")
def api_classroom(classroom_id: int, db: Session = Depends(get_db)):
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        return JSONResponse({"error": "الصف غير موجود"}, status_code=404)
    students = db.scalars(select(Student).where(Student.classroom_id == classroom_id).order_by(Student.name)).all()
    return {
        "classroom": classroom_payload(classroom, db),
        "students": [student_payload(student) for student in students],
    }


@app.put("/api/classrooms/{classroom_id}")
def api_update_classroom(
    classroom_id: int,
    camera_ip: str = Form(""),
    camera_url: str = Form(""),
    camera_user: str = Form(""),
    camera_password: str = Form(""),
    camera_kind: str = Form("snapshot"),
    db: Session = Depends(get_db),
):
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        return JSONResponse({"ok": False, "error": "الصف غير موجود"}, status_code=404)
    try:
        if camera_ip.strip():
            camera_ip = validate_camera_host(camera_ip.strip())
        if camera_url.strip():
            camera_url = validate_camera_url(camera_url.strip())
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    classroom.camera_ip = camera_ip.strip() or None
    classroom.camera_url = camera_url.strip() or None
    classroom.camera_user = camera_user.strip() or None
    if camera_password.strip():
        classroom.camera_password = encrypt_secret(camera_password.strip())
    classroom.camera_kind = camera_kind if camera_kind in {"snapshot", "rtsp"} else "snapshot"
    db.commit()
    db.refresh(classroom)
    return {"ok": True, "classroom": classroom_payload(classroom, db)}


@app.post("/api/classrooms/{classroom_id}/seats/{seat_code}")
def api_assign_seat(
    classroom_id: int,
    seat_code: str,
    student_id: int = Form(...),
    db: Session = Depends(get_db),
):
    classroom = db.get(Classroom, classroom_id)
    student = db.get(Student, student_id)
    if not classroom or not student or student.classroom_id != classroom_id:
        return JSONResponse({"ok": False, "error": "الطالب مو من هذا الصف"}, status_code=400)
    taken = db.scalar(
        select(Student).where(
            Student.classroom_id == classroom_id,
            Student.seat_code == seat_code,
            Student.id != student_id,
        )
    )
    if taken:
        return JSONResponse({"ok": False, "error": f"المقعد محجوز لـ {taken.name}"}, status_code=400)
    student.seat_code = seat_code
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return JSONResponse({"ok": False, "error": "المقعد محجوز"}, status_code=400)
    return {"ok": True, "classroom": classroom_payload(classroom, db), "student": student_payload(student)}


@app.delete("/api/classrooms/{classroom_id}/seats/{seat_code}")
def api_clear_seat(classroom_id: int, seat_code: str, db: Session = Depends(get_db)):
    student = db.scalar(
        select(Student).where(Student.classroom_id == classroom_id, Student.seat_code == seat_code)
    )
    if student:
        student.seat_code = None
        db.commit()
    classroom = db.get(Classroom, classroom_id)
    return {"ok": True, "classroom": classroom_payload(classroom, db) if classroom else None}


@app.get("/api/classrooms/{classroom_id}/snapshot")
def api_classroom_snapshot(classroom_id: int, db: Session = Depends(get_db)):
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        return JSONResponse({"error": "الصف غير موجود"}, status_code=404)
    try:
        frame = fetch_camera_frame(classroom)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        return JSONResponse({"error": "تعذر تجهيز صورة الكاميرا"}, status_code=500)
    return StreamingResponse(iter([encoded.tobytes()]), media_type="image/jpeg")


@app.post("/api/classrooms/{classroom_id}/recognize")
async def api_classroom_recognize(
    classroom_id: int,
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        return JSONResponse({"error": "الصف غير موجود"}, status_code=404)
    if image and image.filename:
        data = await image.read()
        try:
            frame = decode_image(data)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    else:
        try:
            frame = fetch_camera_frame(classroom)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return recognize_image(frame, db, classroom)


MAX_CAMERA_STREAMS = 4
_stream_slots = threading.BoundedSemaphore(MAX_CAMERA_STREAMS)
_camera_recognize_lock = threading.Lock()


def _ezviz_or_error():
    service = get_camera_service("ezviz")
    if service is None or not service.enabled:
        return None, JSONResponse({"error": "كاميرا EZVIZ غير مفعّلة على السيرفر."}, status_code=503)
    return service, None


@app.get("/api/cameras/ezviz/status")
def api_ezviz_status():
    service, error = _ezviz_or_error()
    if error:
        return {"status": "disabled", "camera": "EZVIZ", "intervalMs": FACE_RECOGNITION_INTERVAL_MS}
    return {**service.get_status(), "intervalMs": FACE_RECOGNITION_INTERVAL_MS}


@app.get("/api/cameras/ezviz/frame")
def api_ezviz_frame(max_width: int = 0):
    """Latest cached frame. Never opens a connection to the camera."""
    service, error = _ezviz_or_error()
    if error:
        return error
    result = service.get_jpeg(max_width=max(0, min(max_width, 4096)), quality=90)
    if result is None:
        return JSONResponse({"error": "لا توجد صورة حديثة من الكاميرا.", "status": service.get_status()["status"]}, status_code=503)
    jpeg, seq, ts = result
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Frame-Seq": str(seq)})


@app.get("/api/cameras/ezviz/stream")
async def api_ezviz_stream(request: Request, fps: int = 8):
    """MJPEG preview (multipart/x-mixed-replace) built from the cached frames."""
    service, error = _ezviz_or_error()
    if error:
        return error
    if not _stream_slots.acquire(blocking=False):
        return JSONResponse({"error": "عدد المشاهدين المتزامنين وصل الحد."}, status_code=429)
    interval = 1.0 / max(1, min(fps, 15))

    async def frames():
        last_seq = -1
        try:
            while not await request.is_disconnected():
                result = await run_in_threadpool(service.get_jpeg, 960, 70, last_seq)
                if result is not None:
                    jpeg, last_seq, _ = result
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                await asyncio.sleep(interval)
        finally:
            _stream_slots.release()

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/cameras/ezviz/recognize")
def api_ezviz_recognize(classroom_id: int | None = None, include_frame: bool = False, db: Session = Depends(get_db)):
    """Feed the latest EZVIZ frame into the same recognize_image() used by upload/webcam."""
    service, error = _ezviz_or_error()
    if error:
        return error
    classroom = db.get(Classroom, classroom_id) if classroom_id else None
    if classroom_id and not classroom:
        return JSONResponse({"error": "الصف غير موجود"}, status_code=404)
    latest = service.get_latest_frame()
    if latest is None:
        return JSONResponse({"error": "لا توجد صورة حديثة من الكاميرا.", "status": service.get_status()["status"]}, status_code=503)
    if not _camera_recognize_lock.acquire(blocking=False):
        return JSONResponse({"error": "التعرف جارٍ على إطار سابق. حاول بعد لحظة."}, status_code=429)
    try:
        frame, seq, frame_ts = latest
        result = recognize_image(frame, db, classroom)
    finally:
        _camera_recognize_lock.release()
    result.update(
        {
            "recognized": any(face["known"] for face in result["faces"]),
            "camera": service.config.camera_id,
            "camera_name": service.config.name,
            "timestamp": now().isoformat(),
            "frame_seq": seq,
            "frame_width": int(frame.shape[1]),
            "frame_height": int(frame.shape[0]),
        }
    )
    if include_frame:
        shot = service.get_jpeg(max_width=1280, quality=85)
        if shot is not None and shot[1] == seq:
            result["frame_jpeg"] = base64.b64encode(shot[0]).decode()
            result["frame_scale"] = min(1.0, 1280 / frame.shape[1])
    return result


@app.get("/api/students")
def api_students(db: Session = Depends(get_db)):
    students = db.scalars(select(Student).order_by(Student.class_name, Student.section, Student.name)).all()
    return {"students": [student_payload(student) for student in students]}


@app.get("/api/students/{student_id}/photo")
def api_student_photo(student_id: int, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse({"error": "الطالب غير موجود"}, status_code=404)
    path = Path(student.photo_path)
    if not path.exists() or not path.is_file():
        return JSONResponse({"error": "الصورة غير موجودة"}, status_code=404)
    return FileResponse(path)


@app.post("/api/students")
async def api_create_student(
    name: str = Form(...),
    student_number: str = Form(...),
    class_name: str = Form(...),
    section: str = Form(DEFAULT_SECTION),
    classroom_id: str = Form(""),
    seat_code: str = Form(""),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    name = name.strip()
    student_number = student_number.strip()
    class_name = class_name.strip()
    section = (section or DEFAULT_SECTION).strip() or DEFAULT_SECTION
    if not name or not student_number or (not class_name and not classroom_id):
        return JSONResponse({"ok": False, "error": "أكمل كل الحقول المطلوبة"}, status_code=400)
    if photo is None or not photo.filename:
        return JSONResponse({"ok": False, "error": "ارفع صورة للطالب"}, status_code=400)
    suffix = Path(photo.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return JSONResponse({"ok": False, "error": "الصورة لازم تكون JPG أو PNG"}, status_code=400)
    data = await photo.read()
    if not data:
        return JSONResponse({"ok": False, "error": "ارفع صورة للطالب"}, status_code=400)
    try:
        image = decode_image(data)
        embedding = extract_embedding(image)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    if classroom_id:
        classroom = db.get(Classroom, int(classroom_id))
        if not classroom:
            return JSONResponse({"ok": False, "error": "الصف غير موجود"}, status_code=400)
    else:
        classroom = get_or_create_classroom(db, class_name, section)

    photo_path = save_photo(image, student_number)
    student = Student(
        name=name,
        student_number=student_number,
        class_name=classroom.grade,
        section=classroom.section,
        classroom_id=classroom.id,
        seat_code=seat_code or None,
        photo_path=photo_path,
        embedding=embedding_to_json(embedding),
    )
    db.add(student)
    try:
        db.commit()
        db.refresh(student)
    except IntegrityError:
        db.rollback()
        Path(photo_path).unlink(missing_ok=True)
        return JSONResponse({"ok": False, "error": "رقم الطالب مستخدم من قبل"}, status_code=400)
    invalidate_student(student.id)
    return {"ok": True, "student": student_payload(student)}


@app.put("/api/students/{student_id}")
async def api_update_student(
    student_id: int,
    name: str = Form(...),
    student_number: str = Form(...),
    class_name: str = Form(...),
    section: str = Form(DEFAULT_SECTION),
    seat_code: str = Form(""),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse({"ok": False, "error": "الطالب غير موجود"}, status_code=404)
    name = name.strip()
    student_number = student_number.strip()
    class_name = class_name.strip()
    section = (section or DEFAULT_SECTION).strip() or DEFAULT_SECTION
    if not name or not student_number or not class_name:
        return JSONResponse({"ok": False, "error": "أكمل كل الحقول المطلوبة"}, status_code=400)

    if photo and photo.filename:
        suffix = Path(photo.filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            return JSONResponse({"ok": False, "error": "الصورة لازم تكون JPG أو PNG"}, status_code=400)
        data = await photo.read()
        try:
            image = decode_image(data)
            embedding = extract_embedding(image)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        Path(student.photo_path).unlink(missing_ok=True)
        student.photo_path = save_photo(image, student_number)
        student.embedding = embedding_to_json(embedding)
        invalidate_student(student.id)

    classroom = get_or_create_classroom(db, class_name, section)
    if student.classroom_id != classroom.id:
        student.seat_code = seat_code or None
    elif seat_code:
        student.seat_code = seat_code
    student.name = name
    student.student_number = student_number
    student.class_name = classroom.grade
    student.section = classroom.section
    student.classroom_id = classroom.id
    try:
        db.commit()
        db.refresh(student)
    except IntegrityError:
        db.rollback()
        return JSONResponse({"ok": False, "error": "رقم الطالب مستخدم من قبل"}, status_code=400)
    return {"ok": True, "student": student_payload(student)}


@app.delete("/api/students/{student_id}")
def api_delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student:
        Path(student.photo_path).unlink(missing_ok=True)
        invalidate_student(student.id)
        db.delete(student)
        db.commit()
    return {"ok": True}


@app.get("/api/attendance")
def api_attendance(
    day: str | None = None,
    classroom_id: int | None = None,
    class_name: str | None = None,
    db: Session = Depends(get_db),
):
    selected_day = _parse_day(day)
    classrooms = db.scalars(select(Classroom).order_by(Classroom.grade, Classroom.section)).all()
    students_query = select(Student)
    records_query = (
        select(Attendance)
        .join(Student)
        .where(Attendance.day == selected_day)
        .order_by(Attendance.checked_in_at.desc())
    )
    if classroom_id:
        students_query = students_query.where(Student.classroom_id == classroom_id)
        records_query = records_query.where(
            or_(Attendance.classroom_id == classroom_id, Student.classroom_id == classroom_id)
        )
    elif class_name:
        students_query = students_query.where(Student.class_name == class_name)
        records_query = records_query.where(Student.class_name == class_name)

    students = db.scalars(students_query).all()
    records = db.scalars(records_query).all()
    present_ids = {record.student_id for record in records}
    absent = [student_payload(student) for student in students if student.id not in present_ids]
    return {
        "selected_day": selected_day.isoformat(),
        "classroom_id": classroom_id,
        "classrooms": [{"id": item.id, "title": item.title} for item in classrooms],
        "present_count": len(records),
        "absent_count": len(absent),
        "total_students": len(students),
        "records": [{**_attendance_payload(record), "date": record.day.isoformat()} for record in records],
        "absent": absent,
    }


@app.post("/api/attendance/mark")
def api_mark_attendance(
    student_id: int = Form(...),
    present: str = Form("1"),
    day: str | None = Form(None),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse({"ok": False, "error": "الطالب غير موجود"}, status_code=404)
    selected_day = _parse_day(day)
    existing = db.scalar(select(Attendance).where(Attendance.student_id == student.id, Attendance.day == selected_day))
    want_present = present.strip() not in {"0", "false", "no", "غائب"}
    if want_present and existing is None:
        db.add(
            Attendance(
                student_id=student.id,
                classroom_id=student.classroom_id,
                day=selected_day,
                checked_in_at=now(),
                expression="",
                attention="",
                quality="",
                source="manual",
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    elif not want_present and existing is not None:
        db.delete(existing)
        db.commit()
    return {"ok": True}


@app.get("/attendance/export")
def export_attendance(day: str | None = None, db: Session = Depends(get_db)):
    selected_day = _parse_day(day)
    classrooms = db.scalars(select(Classroom).order_by(Classroom.grade, Classroom.section)).all()
    records = db.scalars(select(Attendance).where(Attendance.day == selected_day)).all()
    present_by_student = {record.student_id: record for record in records}
    output = attendance_workbook(selected_day, classrooms, present_by_student)
    filename = f"attendance-{selected_day.isoformat()}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    day = today()
    records = db.scalars(
        select(Attendance).where(Attendance.day == day).order_by(Attendance.checked_in_at.desc())
    ).all()
    return {
        "present_today": len(records),
        "total_students": count_students(db),
        "recent": [_attendance_payload(record) for record in records[:8]],
    }


@app.post("/api/recognize")
async def recognize(
    image: UploadFile = File(...),
    classroom_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    if not classroom_id:
        return JSONResponse({"ok": False, "error": "اختر الصف والشعبة قبل التسجيل"}, status_code=400)
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        return JSONResponse({"ok": False, "error": "الصف غير موجود"}, status_code=404)
    data = await image.read()
    if not data:
        return {
            "faces": [],
            "present_today": count_present(db, today(), classroom.id),
            "total_students": db.scalar(select(func.count()).select_from(Student).where(Student.classroom_id == classroom.id))
            or 0,
        }
    try:
        frame = decode_image(data)
    except ValueError:
        return {"faces": [], "error": "تعذر قراءة الإطار"}
    return recognize_image(frame, db, classroom)


@app.post("/students")
async def create_student_form(
    name: str = Form(...),
    student_number: str = Form(...),
    class_name: str = Form(...),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    result = await api_create_student(name, student_number, class_name, DEFAULT_SECTION, "", "", photo, db)
    if isinstance(result, JSONResponse):
        return _students_error("تعذر إضافة الطالب")
    return RedirectResponse("/students", status_code=303)
