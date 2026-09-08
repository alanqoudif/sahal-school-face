export type Student = {
  id: number;
  name: string;
  student_number: string;
  class_name: string;
  section: string;
  classroom_id: number | null;
  classroom_title: string;
  seat_code: string | null;
  seat_label: string;
  photo: string;
};

export type Seat = {
  code: string;
  zone: "L" | "M" | "R";
  zone_label: string;
  row: number;
  col: number;
  label: string;
  student: Student | null;
  present: boolean;
};

export type Classroom = {
  id: number;
  grade: string;
  section: string;
  title: string;
  rows: number;
  camera_ip: string;
  camera_url: string;
  camera_user: string;
  camera_kind: "snapshot" | "rtsp";
  has_camera: boolean;
  student_count: number;
  present_today: number;
  seats: Seat[];
};

export type FaceCues = {
  expression?: string;
  attention?: string;
  quality?: string;
};

export type AttendanceRow = {
  id: number;
  name: string;
  class_name: string;
  section: string;
  student_number: string;
  time: string;
  photo: string;
  date?: string;
  seat_label?: string;
  classroom_title?: string;
} & FaceCues;

export type FaceMatch = {
  bbox: [number, number, number, number];
  known: boolean;
  name: string;
  student_id: number | null;
  student_number: string | null;
  class_name: string | null;
  section: string | null;
  confidence: number;
  already_marked: boolean;
  marked_now: boolean;
  photo: string | null;
  seat_label: string | null;
} & FaceCues;

export type RecognizeResponse = {
  faces: FaceMatch[];
  present_today: number;
  total_students: number;
  recent: AttendanceRow[];
  classroom_id?: number | null;
};

export type AttendanceResponse = {
  selected_day: string;
  classroom_id: number | null;
  classrooms: { id: number; title: string }[];
  present_count: number;
  absent_count: number;
  total_students: number;
  records: AttendanceRow[];
  absent: Student[];
};
