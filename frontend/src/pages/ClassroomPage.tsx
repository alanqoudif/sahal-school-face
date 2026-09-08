import { Avatar, Button, Card, Chip, Modal } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { assignSeat, clearSeat, getClassroom } from "../api";
import type { Classroom, Seat, Student } from "../types";

export function ClassroomPage() {
  const { id } = useParams();
  const classroomId = Number(id);
  const [classroom, setClassroom] = useState<Classroom | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [error, setError] = useState("");
  const [selectedSeat, setSelectedSeat] = useState<Seat | null>(null);

  async function refresh() {
    const data = await getClassroom(classroomId);
    setClassroom(data.classroom);
    setStudents(data.students);
  }

  useEffect(() => {
    refresh().catch(() => setError("تعذر فتح الصف"));
  }, [classroomId]);

  async function onAssign(studentId: number) {
    if (!selectedSeat) return;
    const next = await assignSeat(classroomId, selectedSeat.code, studentId);
    setClassroom(next);
    setSelectedSeat(null);
    await refresh();
  }

  async function onClear() {
    if (!selectedSeat) return;
    const next = await clearSeat(classroomId, selectedSeat.code);
    setClassroom(next);
    setSelectedSeat(null);
  }

  const unseated = useMemo(() => students.filter((student) => !student.seat_code), [students]);

  if (!classroom) {
    return <p className="text-muted">{error || "جاري فتح الصف..."}</p>;
  }

  const rows = Array.from(new Set(classroom.seats.map((seat) => seat.row)));

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Button size="sm" variant="ghost" render={(props) => <Link {...props} to="/classes" />}>
            رجوع للصفوف
          </Button>
          <h1 className="mt-2 text-3xl font-extrabold">{classroom.title}</h1>
          <p className="text-muted">
            حضر اليوم {classroom.present_today} من {classroom.student_count}. اضغط مقعد عشان تشوف أو تسند الطالب.
          </p>
        </div>
        <Button render={(props) => <Link {...props} to={`/camera?classroom=${classroom.id}`} />}>
          تسجيل حضور من اللابتوب
        </Button>
      </section>

      {error ? <p className="text-sm font-semibold text-danger">{error}</p> : null}

      <Card className="p-4">
        <p className="mb-4 text-center text-sm font-bold text-muted">مقدمة الفصل / الباب</p>
        <div className="space-y-3">
          {rows.map((row) => (
            <div key={row} className="grid grid-cols-[auto_1fr_auto] items-center gap-3">
              <SeatGroup seats={classroom.seats.filter((seat) => seat.row === row && seat.zone === "R")} onPick={setSelectedSeat} />
              <SeatGroup seats={classroom.seats.filter((seat) => seat.row === row && seat.zone === "M")} onPick={setSelectedSeat} />
              <SeatGroup seats={classroom.seats.filter((seat) => seat.row === row && seat.zone === "L")} onPick={setSelectedSeat} />
            </div>
          ))}
        </div>
        <div className="mt-4 flex justify-between text-xs text-muted">
          <span>يمين</span>
          <span>وسط (4 مقاعد)</span>
          <span>يسار</span>
        </div>
      </Card>

      <Modal>
        <Modal.Backdrop isOpen={Boolean(selectedSeat)} onOpenChange={(open) => !open && setSelectedSeat(null)}>
          <Modal.Container>
            <Modal.Dialog className="sm:max-w-lg">
              <Modal.CloseTrigger />
              <Modal.Header>
                <Modal.Heading>{selectedSeat?.label}</Modal.Heading>
              </Modal.Header>
              <Modal.Body className="space-y-3">
                {selectedSeat?.student ? (
                  <div className="flex items-center gap-3">
                    <Avatar className="size-14">
                      <Avatar.Image alt={selectedSeat.student.name} src={selectedSeat.student.photo} />
                      <Avatar.Fallback>{selectedSeat.student.name.slice(0, 1)}</Avatar.Fallback>
                    </Avatar>
                    <div>
                      <p className="font-extrabold">{selectedSeat.student.name}</p>
                      <p className="text-sm text-muted">رقم {selectedSeat.student.student_number}</p>
                      <Chip size="sm" color={selectedSeat.present ? "success" : "warning"} className="mt-1">
                        {selectedSeat.present ? "حاضر اليوم" : "ما حضر بعد"}
                      </Chip>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted">المقعد فاضي. اختر طالب من هذا الصف.</p>
                )}
                <div className="grid gap-2">
                  {(selectedSeat?.student ? students : unseated).map((student) => (
                    <Button key={student.id} variant="tertiary" onPress={() => onAssign(student.id)}>
                      {student.name} — رقم {student.student_number}
                    </Button>
                  ))}
                </div>
              </Modal.Body>
              <Modal.Footer>
                {selectedSeat?.student ? (
                  <Button variant="danger-soft" onPress={onClear}>
                    إفراغ المقعد
                  </Button>
                ) : null}
                <Button variant="ghost" onPress={() => setSelectedSeat(null)}>
                  إغلاق
                </Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </div>
  );
}

function SeatGroup({ seats, onPick }: { seats: Seat[]; onPick: (seat: Seat) => void }) {
  return (
    <div className="flex gap-2">
      {seats.map((seat) => (
        <button
          key={seat.code}
          type="button"
          onClick={() => onPick(seat)}
          className={`grid h-16 w-14 place-items-center rounded-xl border text-[10px] font-bold ${
            seat.student
              ? seat.present
                ? "border-success bg-success-soft text-success"
                : "border-warning bg-warning-soft text-warning"
              : "border-dashed border-border bg-surface text-muted"
          }`}
          title={seat.label}
        >
          {seat.student ? seat.student.name.split(" ")[0] : seat.col}
        </button>
      ))}
    </div>
  );
}
