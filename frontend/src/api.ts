import type { AttendanceResponse, CameraStatus, Classroom, IpRecognizeResponse, RecognizeResponse, Student } from "./types";

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (response.status === 401 && !path.startsWith("/api/login") && !path.startsWith("/api/session")) {
    window.dispatchEvent(new Event("sahal:unauthorized"));
  }
  return response;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "تعذر تنفيذ الطلب");
  }
  return response.json();
}

export async function sessionStatus(): Promise<{ authenticated: boolean; today: string }> {
  return readJson<{ authenticated: boolean; today: string }>(await request("/api/session"));
}

export async function login(password: string): Promise<void> {
  const body = new FormData();
  body.append("password", password);
  const response = await request("/api/login", { method: "POST", body });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر تسجيل الدخول");
}

export async function logout(): Promise<void> {
  await request("/api/logout", { method: "POST" });
}

export async function listStudents(): Promise<Student[]> {
  const data = await readJson<{ students: Student[] }>(await request("/api/students"));
  return data.students;
}

export async function createStudent(form: FormData): Promise<Student> {
  const response = await request("/api/students", { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر إضافة الطالب");
  return data.student as Student;
}

export async function updateStudent(id: number, form: FormData): Promise<Student> {
  const response = await request(`/api/students/${id}`, { method: "PUT", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر تعديل الطالب");
  return data.student as Student;
}

export async function deleteStudent(id: number): Promise<void> {
  await readJson(await request(`/api/students/${id}`, { method: "DELETE" }));
}

export async function listClassrooms(): Promise<Classroom[]> {
  const data = await readJson<{ classrooms: Classroom[] }>(await request("/api/classrooms"));
  return data.classrooms;
}

export async function createClassroom(form: FormData): Promise<Classroom> {
  const response = await request("/api/classrooms", { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر إنشاء الصف");
  return data.classroom as Classroom;
}

export async function getClassroom(id: number): Promise<{ classroom: Classroom; students: Student[] }> {
  return readJson(await request(`/api/classrooms/${id}`));
}

export async function updateClassroom(id: number, form: FormData): Promise<Classroom> {
  const response = await request(`/api/classrooms/${id}`, { method: "PUT", body: form });
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || "تعذر حفظ الكاميرا");
  return data.classroom as Classroom;
}

export async function assignSeat(classroomId: number, seatCode: string, studentId: number): Promise<Classroom> {
  const body = new FormData();
  body.append("student_id", String(studentId));
  const data = await readJson<{ classroom: Classroom }>(
    await request(`/api/classrooms/${classroomId}/seats/${seatCode}`, { method: "POST", body }),
  );
  return data.classroom;
}

export async function clearSeat(classroomId: number, seatCode: string): Promise<Classroom> {
  const data = await readJson<{ classroom: Classroom }>(
    await request(`/api/classrooms/${classroomId}/seats/${seatCode}`, { method: "DELETE" }),
  );
  return data.classroom;
}

export async function recognizeFrame(blob: Blob, classroomId: number): Promise<RecognizeResponse> {
  const body = new FormData();
  body.append("image", blob, "frame.jpg");
  body.append("classroom_id", String(classroomId));
  return readJson<RecognizeResponse>(await request("/api/recognize", { method: "POST", body }));
}

export function classroomSnapshotUrl(id: number): string {
  return `/api/classrooms/${id}/snapshot?t=${Date.now()}`;
}

export async function fetchAttendance(day: string, classroomId: string): Promise<AttendanceResponse> {
  const params = new URLSearchParams();
  if (day) params.set("day", day);
  if (classroomId) params.set("classroom_id", classroomId);
  const query = params.toString();
  return readJson<AttendanceResponse>(await request(`/api/attendance${query ? `?${query}` : ""}`));
}

export async function markAttendance(studentId: number, present: boolean, day: string): Promise<void> {
  const body = new FormData();
  body.append("student_id", String(studentId));
  body.append("present", present ? "1" : "0");
  body.append("day", day);
  await readJson(await request("/api/attendance/mark", { method: "POST", body }));
}

export function exportUrl(day: string): string {
  return `/attendance/export?day=${day}`;
}

export async function ezvizStatus(): Promise<CameraStatus> {
  return readJson<CameraStatus>(await request("/api/cameras/ezviz/status"));
}

export async function ezvizRecognize(classroomId: number, includeFrame: boolean): Promise<IpRecognizeResponse> {
  const params = new URLSearchParams({ classroom_id: String(classroomId) });
  if (includeFrame) params.set("include_frame", "1");
  return readJson<IpRecognizeResponse>(await request(`/api/cameras/ezviz/recognize?${params}`, { method: "POST" }));
}
