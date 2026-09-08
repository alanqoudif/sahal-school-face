import type { AttendanceResponse, Classroom, RecognizeResponse, Student } from "./types";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "تعذر تنفيذ الطلب");
  }
  return response.json();
}

export async function listStudents(): Promise<Student[]> {
  const data = await readJson<{ students: Student[] }>(await fetch("/api/students"));
  return data.students;
}

export async function createStudent(form: FormData): Promise<Student> {
  const response = await fetch("/api/students", { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر إضافة الطالب");
  return data.student as Student;
}

export async function updateStudent(id: number, form: FormData): Promise<Student> {
  const response = await fetch(`/api/students/${id}`, { method: "PUT", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر تعديل الطالب");
  return data.student as Student;
}

export async function deleteStudent(id: number): Promise<void> {
  await readJson(await fetch(`/api/students/${id}`, { method: "DELETE" }));
}

export async function listClassrooms(): Promise<Classroom[]> {
  const data = await readJson<{ classrooms: Classroom[] }>(await fetch("/api/classrooms"));
  return data.classrooms;
}

export async function createClassroom(form: FormData): Promise<Classroom> {
  const response = await fetch("/api/classrooms", { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر إنشاء الصف");
  return data.classroom as Classroom;
}

export async function getClassroom(id: number): Promise<{ classroom: Classroom; students: Student[] }> {
  return readJson(await fetch(`/api/classrooms/${id}`));
}

export async function updateClassroom(id: number, form: FormData): Promise<Classroom> {
  const response = await fetch(`/api/classrooms/${id}`, { method: "PUT", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر حفظ الكاميرا");
  return data.classroom as Classroom;
}

export async function assignSeat(classroomId: number, seatCode: string, studentId: number): Promise<Classroom> {
  const body = new FormData();
  body.append("student_id", String(studentId));
  const data = await readJson<{ classroom: Classroom }>(
    await fetch(`/api/classrooms/${classroomId}/seats/${seatCode}`, { method: "POST", body }),
  );
  return data.classroom;
}

export async function clearSeat(classroomId: number, seatCode: string): Promise<Classroom> {
  const data = await readJson<{ classroom: Classroom }>(
    await fetch(`/api/classrooms/${classroomId}/seats/${seatCode}`, { method: "DELETE" }),
  );
  return data.classroom;
}

export async function recognizeFrame(blob: Blob, classroomId?: number): Promise<RecognizeResponse> {
  const body = new FormData();
  body.append("image", blob, "frame.jpg");
  if (classroomId) body.append("classroom_id", String(classroomId));
  return readJson<RecognizeResponse>(
    await fetch("/api/recognize", { method: "POST", body }),
  );
}

export function classroomSnapshotUrl(id: number): string {
  return `/api/classrooms/${id}/snapshot?t=${Date.now()}`;
}

export async function fetchAttendance(day: string, classroomId: string): Promise<AttendanceResponse> {
  const params = new URLSearchParams({ day });
  if (classroomId) params.set("classroom_id", classroomId);
  return readJson<AttendanceResponse>(await fetch(`/api/attendance?${params}`));
}

export function exportUrl(day: string): string {
  return `/attendance/export?day=${day}`;
}
