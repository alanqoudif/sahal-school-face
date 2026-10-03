import { Avatar, Button, Card, Chip, Label } from "@heroui/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listClassrooms, recognizeFrame } from "../api";
import { IpCameraPanel } from "./IpCameraPanel";
import { CueChips, cueLine } from "../cues";
import type { AttendanceRow, Classroom, FaceMatch, RecognizeResponse } from "../types";

type Source = "laptop" | "upload" | "ezviz";
const SOURCES: { id: Source; label: string }[] = [
  { id: "laptop", label: "كاميرا اللابتوب" },
  { id: "upload", label: "رفع صورة" },
  { id: "ezviz", label: "كاميرا EZVIZ" },
];

export function CameraPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const captureRef = useRef<HTMLCanvasElement | null>(null);
  const busyRef = useRef(false);
  const classroomIdRef = useRef<number | undefined>(undefined);
  const pauseUntilRef = useRef(0);
  const [status, setStatus] = useState("جاري تشغيل كاميرا اللابتوب...");
  const [scan, setScan] = useState("بعد ما تظهر الصورة، التعرف يشتغل تلقائياً.");
  const [needsRetry, setNeedsRetry] = useState(false);
  const [present, setPresent] = useState(0);
  const [total, setTotal] = useState(0);
  const [recent, setRecent] = useState<AttendanceRow[]>([]);
  const [lastMatch, setLastMatch] = useState<FaceMatch | null>(null);
  const [source, setSource] = useState<Source>("laptop");
  const [classrooms, setClassrooms] = useState<Classroom[]>([]);
  const [classroomId, setClassroomId] = useState(searchParams.get("classroom") || "");
  classroomIdRef.current = classroomId ? Number(classroomId) : undefined;

  const applyResult = useCallback((data: RecognizeResponse) => {
    setPresent(data.present_today);
    setTotal(data.total_students);
    setRecent(data.recent || []);
    const known = (data.faces || []).find((face) => face.known);
    if (known) setLastMatch(known);
  }, []);

  async function recognizeUpload(file: File) {
    if (!classroomIdRef.current) {
      setScan("اختر الصف والشعبة عشان نبدأ التسجيل.");
      return;
    }
    try {
      const data = await recognizeFrame(file, classroomIdRef.current);
      applyResult(data);
      const count = (data.faces || []).length;
      setScan(count ? `لقينا ${count} وجه في الصورة` : "ما فيه وجه واضح في الصورة");
    } catch (err) {
      setScan(err instanceof Error ? err.message : "صار خطأ أثناء التعرف.");
    }
  }

  function drawFaces(faces: FaceMatch[]) {
    const video = videoRef.current;
    const overlay = overlayRef.current;
    if (!video || !overlay) return;
    overlay.width = video.videoWidth || overlay.clientWidth;
    overlay.height = video.videoHeight || overlay.clientHeight;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    faces.forEach((face) => {
      const [x1, y1, x2, y2] = face.bbox;
      ctx.strokeStyle = face.known ? "#17c964" : "#f5a524";
      ctx.lineWidth = 4;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.font = "700 22px Cairo";
      const label = face.name;
      const extra = cueLine(face);
      ctx.font = extra ? "700 20px Cairo" : "700 22px Cairo";
      const nameWidth = ctx.measureText(label).width;
      ctx.font = "600 14px Cairo";
      const extraWidth = extra ? ctx.measureText(extra).width : 0;
      const width = Math.max(nameWidth, extraWidth) + 16;
      const boxH = extra ? 48 : 32;
      ctx.fillStyle = face.known ? "#17c964" : "#f5a524";
      ctx.fillRect(x1, Math.max(y1 - boxH - 2, 0), width, boxH);
      ctx.fillStyle = "#fff";
      ctx.font = "700 20px Cairo";
      ctx.fillText(label, x1 + 8, Math.max(y1 - (extra ? 24 : 10), 20));
      if (extra) {
        ctx.font = "600 14px Cairo";
        ctx.fillText(extra, x1 + 8, Math.max(y1 - 8, 36));
      }
    });
  }

  async function startCamera() {
    setNeedsRetry(false);
    setStatus("جاري تشغيل الكاميرا...");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: 1280, height: 720 },
        audio: false,
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setStatus("");
      setScan("الكاميرا شغالة. مرّر قدامها للتسجيل.");
    } catch {
      setStatus("ما قدرنا نفتح الكاميرا. اسمح للمتصفح يستخدمها ثم أعد المحاولة.");
      setNeedsRetry(true);
    }
  }

  useEffect(() => {
    listClassrooms().then(setClassrooms).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (source !== "laptop") return;
    startCamera();
    const timer = window.setInterval(async () => {
      const video = videoRef.current;
      const selectedClassroom = classroomIdRef.current;
      if (!selectedClassroom) {
        setScan("اختر الصف والشعبة عشان نبدأ التسجيل.");
        return;
      }
      if (Date.now() < pauseUntilRef.current) return;
      if (busyRef.current || !video || video.readyState < 2) return;
      busyRef.current = true;
      if (!captureRef.current) captureRef.current = document.createElement("canvas");
      const canvas = captureRef.current;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.72));
      if (!blob) {
        busyRef.current = false;
        return;
      }
      try {
        const data = await recognizeFrame(blob, selectedClassroom);
        drawFaces(data.faces || []);
        applyResult(data);
        if ((data.faces || []).some((face) => face.marked_now)) {
          pauseUntilRef.current = Date.now() + 8000;
        }
        const count = (data.faces || []).length;
        setScan(count ? `لقينا ${count} وجه في الإطار` : "ما فيه وجه واضح الآن");
      } catch (err) {
        setScan(err instanceof Error ? err.message : "صار خطأ أثناء التعرف. نعيد المحاولة...");
      } finally {
        busyRef.current = false;
      }
    }, 2000);
    return () => {
      window.clearInterval(timer);
      const stream = videoRef.current?.srcObject as MediaStream | undefined;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [source]);

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-3xl font-extrabold">التسجيل بالكاميرا</h1>
        <p className="mt-1 text-muted">اختر الصف والشعبة أولاً. التعرف يشتغل على طلاب هذا الصف فقط، ويتوقف ثواني بعد كل تسجيل ناجح.</p>
      </section>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="مصدر الصورة">
        {SOURCES.map((item) => (
          <Button
            key={item.id}
            size="sm"
            variant={source === item.id ? "primary" : "secondary"}
            onPress={() => setSource(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </div>

      <div className="grid max-w-md gap-1">
        <Label htmlFor="classroom">الصف والشعبة</Label>
        <select
          id="classroom"
          value={classroomId}
          onChange={(event) => {
            const value = event.target.value;
            setClassroomId(value);
            if (value) setSearchParams({ classroom: value });
            else setSearchParams({});
          }}
          className="input h-10 w-full rounded-xl"
        >
          <option value="">اختر الصف والشعبة</option>
          {classrooms.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.8fr)]">
        {source === "ezviz" ? (
          <div className="space-y-2">
            <IpCameraPanel classroomId={classroomId ? Number(classroomId) : undefined} onResult={applyResult} onNotice={setScan} />
            <p className="text-sm text-muted">{scan}</p>
          </div>
        ) : source === "upload" ? (
          <Card className="p-6">
            <Label htmlFor="upload-image">ارفع صورة فيها وجوه الطلاب</Label>
            <input
              id="upload-image"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="input mt-2 w-full rounded-xl p-2"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) recognizeUpload(file);
                event.target.value = "";
              }}
            />
            <p className="mt-3 text-sm text-muted">{scan}</p>
          </Card>
        ) : (
        <Card className="overflow-hidden p-3">
          <div className="relative overflow-hidden rounded-2xl bg-black">
            <video ref={videoRef} autoPlay playsInline muted className="block aspect-video w-full object-cover" />
            <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
            {status ? (
              <div className="absolute inset-x-4 bottom-4 rounded-2xl bg-black/65 px-4 py-3 text-sm font-semibold text-white">
                {status}
              </div>
            ) : null}
          </div>
          <Card.Footer className="justify-between">
            <p className="text-sm text-muted">{scan}</p>
            {needsRetry ? (
              <Button size="sm" onPress={startCamera}>
                إعادة المحاولة
              </Button>
            ) : (
              <Chip color="success" size="sm" variant="soft">
                بث مباشر
              </Chip>
            )}
          </Card.Footer>
        </Card>
        )}

        <aside className="space-y-4">
          <Card>
            <Card.Header>
              <Card.Description>حضر اليوم</Card.Description>
              <Card.Title className="text-4xl text-success">
                {present}
                <span className="text-lg text-muted"> / {total}</span>
              </Card.Title>
            </Card.Header>
          </Card>

          {lastMatch ? (
            <Card className="border-success/30 bg-success-soft">
              <Card.Header>
                <Chip color="success" size="sm">
                  {lastMatch.marked_now ? "تم تسجيل الحضور" : "مسجّل مسبقاً اليوم"}
                </Chip>
                <div className="mt-3 flex items-center gap-3">
                  <Avatar className="size-14">
                    <Avatar.Image alt={lastMatch.name} src={lastMatch.photo || ""} />
                    <Avatar.Fallback>{lastMatch.name.slice(0, 1)}</Avatar.Fallback>
                  </Avatar>
                  <div>
                    <Card.Title>{lastMatch.name}</Card.Title>
                    <Card.Description>
                      {lastMatch.class_name} {lastMatch.section ? `· ${lastMatch.section}` : ""} · رقم {lastMatch.student_number}
                    </Card.Description>
                  </div>
                </div>
                <div className="mt-3">
                  <CueChips cues={lastMatch} />
                </div>
              </Card.Header>
            </Card>
          ) : null}

          <Card>
            <Card.Header>
              <Card.Title>آخر الحضور</Card.Title>
            </Card.Header>
            <Card.Content className="space-y-3">
              {recent.length ? (
                recent.map((item) => (
                  <div key={item.id} className="flex items-center gap-3">
                    <Avatar size="sm">
                      <Avatar.Image alt={item.name} src={item.photo} />
                      <Avatar.Fallback>{item.name.slice(0, 1)}</Avatar.Fallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-bold">{item.name}</p>
                      <p className="text-xs text-muted">
                        {item.time}
                        {item.expression ? ` · ${item.expression}` : ""}
                        {item.attention ? ` · ${item.attention}` : ""}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted">ما سجّل أحد إلى الآن.</p>
              )}
            </Card.Content>
          </Card>
        </aside>
      </div>
    </div>
  );
}
