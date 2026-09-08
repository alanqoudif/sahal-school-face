import { Button, Card, Chip, Input, Label, Modal, TextField } from "@heroui/react";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createClassroom, listClassrooms } from "../api";
import type { Classroom } from "../types";

export function ClassesPage() {
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  async function refresh() {
    setClassrooms(await listClassrooms());
  }

  useEffect(() => {
    refresh().catch(() => setError("تعذر تحميل الصفوف"));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      await createClassroom(new FormData(event.currentTarget));
      event.currentTarget.reset();
      setOpen(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذر إنشاء الصف");
    }
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold">الصفوف والشعب</h1>
          <p className="mt-1 text-muted">كل صف له شعبة ومقاعد. الحضور حالياً يتسجل من كاميرا اللابتوب.</p>
        </div>
        <Button onPress={() => setOpen(true)}>إضافة صف / شعبة</Button>
      </section>

      {error ? <p className="text-sm font-semibold text-danger">{error}</p> : null}

      {classrooms.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {classrooms.map((classroom) => (
            <Card key={classroom.id}>
              <Card.Header>
                <Card.Title>{classroom.title}</Card.Title>
                <Card.Description>
                  {classroom.student_count} طالب · حضر اليوم {classroom.present_today}
                </Card.Description>
                <div className="mt-2 flex gap-2">
                  <Chip size="sm" color="success" variant="soft">
                    الشعبة {classroom.section}
                  </Chip>
                </div>
              </Card.Header>
              <Card.Footer>
                <Button render={(props) => <Link {...props} to={`/classes/${classroom.id}`} />}>دخول الصف</Button>
              </Card.Footer>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="px-6 py-16 text-center">
          <Card.Title>ما فيه صفوف بعد</Card.Title>
          <Card.Description>أضف الصف والشعبة، وبعدها أضف الطلاب ووزّعهم على المقاعد.</Card.Description>
        </Card>
      )}

      <Modal>
        <Modal.Backdrop isOpen={open} onOpenChange={setOpen}>
          <Modal.Container>
            <Modal.Dialog className="sm:max-w-lg">
              <Modal.CloseTrigger />
              <Modal.Header>
                <Modal.Heading>صف وشعبة جديدة</Modal.Heading>
              </Modal.Header>
              <form onSubmit={onSubmit}>
                <Modal.Body className="grid gap-4">
                  <TextField isRequired name="grade" className="w-full">
                    <Label>الصف</Label>
                    <Input fullWidth placeholder="مثال: الحادي عشر" />
                  </TextField>
                  <TextField isRequired name="section" defaultValue="الأولى" className="w-full">
                    <Label>الشعبة</Label>
                    <Input fullWidth placeholder="الأولى / الثانية / الثالثة" />
                  </TextField>
                </Modal.Body>
                <Modal.Footer>
                  <Button slot="close" variant="ghost">
                    إلغاء
                  </Button>
                  <Button type="submit">حفظ</Button>
                </Modal.Footer>
              </form>
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </div>
  );
}
