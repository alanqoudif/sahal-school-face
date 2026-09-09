from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

DEFAULT_SECTION = "الأولى"
SEAT_ROWS = 4


class Classroom(Base):
    __tablename__ = "classrooms"
    __table_args__ = (UniqueConstraint("grade", "section", name="uq_classroom_grade_section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    grade: Mapped[str] = mapped_column(String(100), index=True)
    section: Mapped[str] = mapped_column(String(100), default=DEFAULT_SECTION)
    rows: Mapped[int] = mapped_column(Integer, default=SEAT_ROWS)
    camera_ip: Mapped[str | None] = mapped_column(String(200), nullable=True)
    camera_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    camera_user: Mapped[str | None] = mapped_column(String(200), nullable=True)
    camera_password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    camera_kind: Mapped[str] = mapped_column(String(20), default="snapshot")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    students: Mapped[list["Student"]] = relationship(back_populates="classroom")
    attendances: Mapped[list["Attendance"]] = relationship(back_populates="classroom")

    @property
    def title(self) -> str:
        return f"الصف {self.grade} — الشعبة {self.section}"


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    student_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    class_name: Mapped[str] = mapped_column(String(100), index=True)
    section: Mapped[str] = mapped_column(String(100), default=DEFAULT_SECTION)
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classrooms.id"), nullable=True, index=True)
    seat_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_path: Mapped[str] = mapped_column(String(500))
    embedding: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    classroom: Mapped[Classroom | None] = relationship(back_populates="students")
    attendances: Mapped[list["Attendance"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("student_id", "day", name="uq_attendance_student_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classrooms.id"), nullable=True, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expression: Mapped[str] = mapped_column(String(50), default="")
    attention: Mapped[str] = mapped_column(String(50), default="")
    quality: Mapped[str] = mapped_column(String(50), default="")
    source: Mapped[str] = mapped_column(String(20), default="camera")

    student: Mapped[Student] = relationship(back_populates="attendances")
    classroom: Mapped[Classroom | None] = relationship(back_populates="attendances")
