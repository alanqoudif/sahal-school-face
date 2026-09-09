import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SAHAL_DATA_DIR", BASE_DIR / "data")).resolve()
PHOTOS_DIR = DATA_DIR / "photos"
BACKUPS_DIR = DATA_DIR / "backups"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "sahal.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=FULL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _table_columns(table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
    return {row[1] for row in rows}


def _add_column(table: str, definition: str):
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {definition}"))


def migrate_schema():
    if "students" in _sqlite_tables() and "section" not in _table_columns("students"):
        _add_column("students", "section VARCHAR(100) DEFAULT 'الأولى'")
    if "students" in _sqlite_tables() and "classroom_id" not in _table_columns("students"):
        _add_column("students", "classroom_id INTEGER")
    if "students" in _sqlite_tables() and "seat_code" not in _table_columns("students"):
        _add_column("students", "seat_code VARCHAR(20)")
    if "attendances" in _sqlite_tables() and "classroom_id" not in _table_columns("attendances"):
        _add_column("attendances", "classroom_id INTEGER")
    if "attendances" in _sqlite_tables() and "expression" not in _table_columns("attendances"):
        _add_column("attendances", "expression VARCHAR(50) DEFAULT ''")
    if "attendances" in _sqlite_tables() and "attention" not in _table_columns("attendances"):
        _add_column("attendances", "attention VARCHAR(50) DEFAULT ''")
    if "attendances" in _sqlite_tables() and "quality" not in _table_columns("attendances"):
        _add_column("attendances", "quality VARCHAR(50) DEFAULT ''")
    if "attendances" in _sqlite_tables() and "source" not in _table_columns("attendances"):
        _add_column("attendances", "source VARCHAR(20) DEFAULT 'camera'")
    _ensure_seat_unique_index()


def _ensure_seat_unique_index():
    if "students" not in _sqlite_tables():
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_students_classroom_seat "
                    "ON students(classroom_id, seat_code) "
                    "WHERE seat_code IS NOT NULL AND seat_code != ''"
                )
            )
    except Exception:
        pass


def _sqlite_tables() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all()
    return {row[0] for row in rows}


def seed_classrooms():
    from app.models import Classroom, Student

    db = SessionLocal()
    try:
        students = db.query(Student).all()
        for student in students:
            grade = (student.class_name or "").strip()
            section = (getattr(student, "section", None) or "الأولى").strip() or "الأولى"
            student.section = section
            if not grade:
                continue
            classroom = db.query(Classroom).filter_by(grade=grade, section=section).one_or_none()
            if classroom is None:
                classroom = Classroom(grade=grade, section=section)
                db.add(classroom)
                db.flush()
            student.classroom_id = classroom.id
        db.commit()
    finally:
        db.close()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    from app.models import Attendance, Classroom, Student  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
    seed_classrooms()
