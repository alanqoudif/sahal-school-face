import {
  Alert,
  Avatar,
  Button,
  Card,
  Chip,
  Description,
  Input,
  Label,
  Modal,
  TextField,
} from "@heroui/react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { createStudent, deleteStudent, listClassrooms, listStudents, updateStudent } from "../api";
import type { Classroom, Student } from "../types";

export function StudentsPage() {
  const [students, setStudents] = useState<Student[]>([]);
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Student | null>(null);

  async function refresh() {
    const [nextStudents, nextClassrooms] = await Promise.all([listStudents(), listClassrooms()]);
    setStudents(nextStudents);
    setClassrooms(nextClassrooms);
  }

  useEffect(() => {
    refresh().catch(() => setError("تعذر تحميل الطلاب"));
  }, []);

  const filtered = useMemo(() => {
    const value = query.trim();
    if (!value) return students;
    return students.filter((student) =>
      `${student.name} ${student.student_number} ${student.class_name} ${student.section}`.includes(value),
    );
  }, [query, students]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      if (editing) {
        await updateStudent(editing.id, form);
      } else {
        await createStudent(form);
      }
      event.currentTarget.reset();
      setOpen(false);
      setEditing(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذر حفظ الطالب");
      setOpen(true);
    } finally {
      setSaving(false);
    }
  }

  function openCreate() {
    setEditing(null);
    setOpen(true);
  }

  function openEdit(student: Student) {
    setEditing(student);
    setOpen(true);
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold">الطلاب</h1>
          <p className="mt-1 text-muted">أضف الطالب للصف والشعبة بصورة أمامية واضحة. الصور الضعيفة ما تنقبل.</p>
        </div>
        <Button onPress={openCreate}>إضافة طالب</Button>
      </section>

      <Input fullWidth value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ابحث بالاسم أو الرقم أو الصف أو الشعبة" />

      {error ? (
        <Alert status="danger">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>تعذر الحفظ</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Content>
        </Alert>
      ) : null}

      {filtered.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((student) => (
            <Card key={student.id}>
              <div className="flex items-center gap-4 p-2">
                <Avatar className="size-16 rounded-2xl">
                  <Avatar.Image alt={student.name} src={student.photo} className="rounded-2xl object-cover" />
                  <Avatar.Fallback>{student.name.slice(0, 1)}</Avatar.Fallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <Card.Title className="truncate">{student.name}</Card.Title>
                  <Card.Description>رقم {student.student_number}</Card.Description>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Chip size="sm" color="success" variant="soft">
                      {student.classroom_title}
                    </Chip>
                    <Chip size="sm" variant="soft">
                      {student.seat_label}
                    </Chip>
                  </div>
                </div>
              </div>
              <Card.Footer className="justify-end gap-2">
                <Button size="sm" variant="secondary" onPress={() => openEdit(student)}>
                  تعديل
                </Button>
                <Button
                  size="sm"
                  variant="danger-soft"
                  onPress={async () => {
                    if (!confirm(`تحذف ${student.name}؟`)) return;
                    await deleteStudent(student.id);
                    await refresh();
                  }}
                >
                  حذف
                </Button>
              </Card.Footer>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="px-6 py-16 text-center">
          <Card.Title>ما فيه طلاب</Card.Title>
          <Card.Description>أضف الطلاب داخل الصف والشعبة عشان الكاميرا تتعرّف عليهم.</Card.Description>
        </Card>
      )}

      <Modal>
        <Modal.Backdrop
          isOpen={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) setEditing(null);
          }}
        >
          <Modal.Container>
            <Modal.Dialog className="sm:max-w-lg">
              <Modal.CloseTrigger />
              <Modal.Header>
                <Modal.Heading>{editing ? "تعديل طالب" : "طالب جديد"}</Modal.Heading>
              </Modal.Header>
              <form onSubmit={onSubmit}>
                <Modal.Body className="grid gap-4">
                  <TextField isRequired name="name" defaultValue={editing?.name || ""} className="w-full">
                    <Label>الاسم</Label>
                    <Input fullWidth placeholder="مثال: أحمد محمد" />
                  </TextField>
                  <TextField isRequired name="student_number" defaultValue={editing?.student_number || ""} className="w-full">
                    <Label>رقم الطالب</Label>
                    <Input fullWidth placeholder="مثال: 1024" />
                  </TextField>
                  <TextField isRequired name="class_name" defaultValue={editing?.class_name || ""} className="w-full">
                    <Label>الصف</Label>
                    <Input fullWidth placeholder="مثال: الحادي عشر" />
                  </TextField>
                  <TextField isRequired name="section" defaultValue={editing?.section || "الأولى"} className="w-full">
                    <Label>الشعبة</Label>
                    <Input fullWidth placeholder="الأولى / الثانية / الثالثة" />
                  </TextField>
                  {classrooms.length ? (
                    <p className="text-xs text-muted">
                      الصفوف الحالية: {classrooms.map((item) => item.title).join(" · ")}
                    </p>
                  ) : null}
                  <div className="grid gap-1">
                    <Label>صورة الوجه {editing ? "(اختياري للتغيير)" : ""}</Label>
                    <input
                      name="photo"
                      type="file"
                      accept="image/*"
                      required={!editing}
                      className="w-full rounded-2xl border border-dashed border-border px-3 py-4 text-sm"
                    />
                    <Description>صورة أمامية واضحة بإضاءة جيدة. النظام يرفض الصورة إذا الوجه صغير أو مشوّش.</Description>
                  </div>
                </Modal.Body>
                <Modal.Footer>
                  <Button slot="close" variant="ghost">
                    إلغاء
                  </Button>
                  <Button isPending={saving} type="submit">
                    حفظ
                  </Button>
                </Modal.Footer>
              </form>
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </div>
  );
}
