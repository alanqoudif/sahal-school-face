import { Avatar, Button, Card, Chip, Input, Label } from "@heroui/react";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { exportUrl, fetchAttendance, markAttendance } from "../api";
import { CueChips } from "../cues";
import type { AttendanceResponse, FaceCues } from "../types";

export function AttendancePage() {
  const [day, setDay] = useState("");
  const [classroomId, setClassroomId] = useState("");
  const [data, setData] = useState<AttendanceResponse | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load(nextDay = day, nextClassroom = classroomId) {
    setError("");
    try {
      const payload = await fetchAttendance(nextDay, nextClassroom);
      setData(payload);
      if (!nextDay) setDay(payload.selected_day);
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذر تحميل الحضور");
    }
  }

  useEffect(() => {
    load();
  }, []);

  function onFilter(event: FormEvent) {
    event.preventDefault();
    load(day, classroomId);
  }

  async function onMark(studentId: number, present: boolean) {
    setBusyId(studentId);
    setError("");
    try {
      await markAttendance(studentId, present, day);
      await load(day, classroomId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذر تعديل الحضور");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold">حضور الإدارة</h1>
          <p className="mt-1 text-muted">الحاضر والغائب لكل صف وشعبة. تقدر تسجّل أو تلغي يدوياً إذا الكاميرا ما اشتغلت. التعبير والانتباه تقدير فقط وما ينزلان في الإكسل.</p>
        </div>
        <Button render={(props) => <a {...props} href={exportUrl(day)} />}>تصدير إكسل</Button>
      </section>

      <Card>
        <form onSubmit={onFilter} className="grid gap-4 p-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <div className="grid gap-1">
            <Label htmlFor="day">التاريخ</Label>
            <Input id="day" type="date" value={day} onChange={(event) => setDay(event.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="classroom">الصف والشعبة</Label>
            <select
              id="classroom"
              value={classroomId}
              onChange={(event) => setClassroomId(event.target.value)}
              className="input h-10 w-full rounded-xl"
            >
              <option value="">كل الصفوف</option>
              {(data?.classrooms || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" variant="secondary">
            تصفية
          </Button>
        </form>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <Card.Header>
            <Card.Description>حاضر</Card.Description>
            <Card.Title className="text-3xl text-success">{data?.present_count ?? 0}</Card.Title>
          </Card.Header>
        </Card>
        <Card>
          <Card.Header>
            <Card.Description>غائب</Card.Description>
            <Card.Title className="text-3xl text-warning">{data?.absent_count ?? 0}</Card.Title>
          </Card.Header>
        </Card>
        <Card>
          <Card.Header>
            <Card.Description>إجمالي الطلاب</Card.Description>
            <Card.Title className="text-3xl">{data?.total_students ?? 0}</Card.Title>
          </Card.Header>
        </Card>
      </div>

      {error ? <p className="text-sm font-semibold text-danger">{error}</p> : null}

      <Card className="overflow-hidden">
        <Card.Header>
          <Card.Title>الحاضرون</Card.Title>
        </Card.Header>
        {data?.records.length ? (
          <StudentTable
            rows={data.records.map((record) => ({
              id: record.student_id || record.id,
              name: record.name,
              student_number: record.student_number,
              title: record.classroom_title || `${record.class_name} — ${record.section}`,
              extra: record.source === "manual" ? `${record.time} · يدوي` : record.time,
              photo: record.photo,
              chip: "حاضر",
              success: true,
              cues: {
                expression: record.expression,
                attention: record.attention,
                quality: record.quality,
              },
              actionLabel: "تعيين غائب",
              onAction: () => onMark(record.student_id || 0, false),
              busy: busyId === (record.student_id || record.id),
            }))}
          />
        ) : (
          <p className="px-4 pb-4 text-sm text-muted">ما فيه حضور لهذا اليوم.</p>
        )}
      </Card>

      <Card className="overflow-hidden">
        <Card.Header>
          <Card.Title>الغائبون</Card.Title>
        </Card.Header>
        {data?.absent.length ? (
          <StudentTable
            rows={data.absent.map((student) => ({
              id: student.id,
              name: student.name,
              student_number: student.student_number,
              title: student.classroom_title,
              extra: student.seat_label,
              photo: student.photo,
              chip: "غائب",
              success: false,
              actionLabel: "تسجيل حاضر",
              onAction: () => onMark(student.id, true),
              busy: busyId === student.id,
            }))}
          />
        ) : (
          <p className="px-4 pb-4 text-sm text-muted">ما فيه غياب في التصفية الحالية.</p>
        )}
      </Card>

      <Button variant="secondary" render={(props) => <Link {...props} to="/camera" />}>
        فتح كاميرا اللابتوب
      </Button>
    </div>
  );
}

function StudentTable({
  rows,
}: {
  rows: {
    id: number;
    name: string;
    student_number: string;
    title: string;
    extra: string;
    photo: string;
    chip: string;
    success: boolean;
    cues?: FaceCues;
    actionLabel?: string;
    onAction?: () => void;
    busy?: boolean;
  }[];
}) {
  const showCues = rows.some((row) => row.cues);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-right">
        <thead className="bg-surface-secondary text-sm text-muted">
          <tr>
            <th className="px-4 py-3 font-semibold">الطالب</th>
            <th className="px-4 py-3 font-semibold">الرقم</th>
            <th className="px-4 py-3 font-semibold">الصف والشعبة</th>
            <th className="px-4 py-3 font-semibold">التفاصيل</th>
            {showCues ? <th className="px-4 py-3 font-semibold">عند الدخول</th> : null}
            <th className="px-4 py-3 font-semibold">الحالة</th>
            <th className="px-4 py-3 font-semibold">تعديل</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border/70">
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <Avatar size="sm">
                    <Avatar.Image alt={row.name} src={row.photo} />
                    <Avatar.Fallback>{row.name.slice(0, 1)}</Avatar.Fallback>
                  </Avatar>
                  <span className="font-bold">{row.name}</span>
                </div>
              </td>
              <td className="px-4 py-3 text-muted">{row.student_number}</td>
              <td className="px-4 py-3">{row.title}</td>
              <td className="px-4 py-3 font-semibold">{row.extra}</td>
              {showCues ? (
                <td className="px-4 py-3">
                  <CueChips cues={row.cues} />
                </td>
              ) : null}
              <td className="px-4 py-3">
                <Chip size="sm" color={row.success ? "success" : "warning"} variant="soft">
                  {row.chip}
                </Chip>
              </td>
              <td className="px-4 py-3">
                {row.onAction ? (
                  <Button size="sm" variant="secondary" isPending={row.busy} onPress={row.onAction}>
                    {row.actionLabel}
                  </Button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
