import { Button, Card, Chip } from "@heroui/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ezvizRecognize, ezvizStatus } from "../api";
import type { CameraState, CameraStatus, FaceMatch, IpRecognizeResponse } from "../types";

const STATE_LABEL: Record<CameraState, { text: string; color: "success" | "danger" | "warning" | "default" }> = {
  online: { text: "متصلة", color: "success" },
  connecting: { text: "جاري الاتصال", color: "warning" },
  reconnecting: { text: "إعادة الاتصال", color: "warning" },
  offline: { text: "غير متصلة", color: "danger" },
  authentication_failed: { text: "فشل التحقق", color: "danger" },
  stream_error: { text: "خطأ في البث", color: "danger" },
  disabled: { text: "غير مفعّلة", color: "default" },
};

type Props = {
  classroomId?: number;
  onResult: (data: IpRecognizeResponse) => void;
  onNotice: (message: string) => void;
};

function faceLines(face: FaceMatch): string[] {
  if (!face.known) return [face.name];
  const info = [face.class_name, face.section, face.student_number ? `رقم ${face.student_number}` : ""].filter(Boolean).join(" · ");
  const status = face.marked_now ? "✓ تم تسجيل الحضور" : face.already_marked ? "✓ حاضر اليوم" : "";
  return [face.name, info, status].filter(Boolean);
}

function drawBoxes(canvas: HTMLCanvasElement | null, data: IpRecognizeResponse | null, scale: number) {
  if (!canvas) return;
  if (!data) {
    canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  canvas.width = data.frame_width * scale;
  canvas.height = data.frame_height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const unit = Math.max(canvas.width / 1000, 0.8);
  const nameSize = 17 * unit;
  const infoSize = 13 * unit;
  data.faces.forEach((face: FaceMatch) => {
    const [x1, y1, x2, y2] = face.bbox.map((v) => v * scale);
    const color = face.known ? "#17c964" : face.name === "غير مؤكد" ? "#f5a524" : "#f31260";
    const w = x2 - x1;
    const h = y2 - y1;

    // target frame on the face: thin outline + thick corner brackets
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(1.5, 1.5 * unit);
    ctx.globalAlpha = 0.55;
    ctx.strokeRect(x1, y1, w, h);
    ctx.globalAlpha = 1;
    ctx.lineWidth = Math.max(3, 4 * unit);
    ctx.lineCap = "round";
    const arm = Math.min(w, h) * 0.28;
    ctx.beginPath();
    for (const [cx, cy, dx, dy] of [
      [x1, y1, 1, 1],
      [x2, y1, -1, 1],
      [x1, y2, 1, -1],
      [x2, y2, -1, -1],
    ] as const) {
      ctx.moveTo(cx + dx * arm, cy);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx, cy + dy * arm);
    }
    ctx.stroke();

    // info card above the face (below it when there is no room)
    const lines = faceLines(face);
    ctx.direction = "rtl";
    const sizes = lines.map((_, i) => (i === 0 ? nameSize : infoSize));
    const widths = lines.map((line, i) => {
      ctx.font = `${i === 0 ? 700 : 600} ${sizes[i]}px Cairo, sans-serif`;
      return ctx.measureText(line).width;
    });
    const pad = 7 * unit;
    const lineGap = 4 * unit;
    const cardW = Math.max(...widths) + pad * 2;
    const cardH = sizes.reduce((sum, size) => sum + size + lineGap, 0) + pad;
    const cardX = Math.min(Math.max(x1 + w / 2 - cardW / 2, 0), canvas.width - cardW);
    const above = y1 - cardH - 6 * unit;
    const cardY = above >= 0 ? above : Math.min(y2 + 6 * unit, canvas.height - cardH);
    ctx.fillStyle = "rgba(10,10,10,0.78)";
    ctx.beginPath();
    ctx.roundRect(cardX, cardY, cardW, cardH, 8 * unit);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.fillRect(cardX, cardY, cardW, Math.max(3, 3 * unit));
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    let ty = cardY + pad * 0.8;
    lines.forEach((line, i) => {
      ctx.font = `${i === 0 ? 700 : 600} ${sizes[i]}px Cairo, sans-serif`;
      ctx.fillStyle = i === 0 ? "#fff" : i === 2 ? color : "#d4d4d8";
      ctx.fillText(line, cardX + cardW / 2, ty);
      ty += sizes[i] + lineGap;
    });
  });
}

export function IpCameraPanel({ classroomId, onResult, onNotice }: Props) {
  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [auto, setAuto] = useState(true);
  const [captured, setCaptured] = useState<{ src: string; data: IpRecognizeResponse } | null>(null);
  const [lastRun, setLastRun] = useState<IpRecognizeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const clearTimer = useRef<number | undefined>(undefined);
  const classroomRef = useRef(classroomId);
  classroomRef.current = classroomId;

  useEffect(() => {
    let alive = true;
    const poll = () => ezvizStatus().then((s) => alive && setStatus(s)).catch(() => undefined);
    poll();
    const timer = window.setInterval(poll, 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const run = useCallback(
    async (manual: boolean) => {
      const selected = classroomRef.current;
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      try {
        const data = await ezvizRecognize(selected, manual);
        onResult(data);
        setLastRun(data);
        if (manual && data.frame_jpeg) {
          setCaptured({ src: `data:image/jpeg;base64,${data.frame_jpeg}`, data });
          window.setTimeout(() => drawBoxes(overlayRef.current, data, data.frame_scale ?? 1), 0);
        } else if (!manual) {
          drawBoxes(overlayRef.current, data, 1);
          if (clearTimer.current) window.clearTimeout(clearTimer.current);
          clearTimer.current = window.setTimeout(() => drawBoxes(overlayRef.current, null, 1), 2500);
        }
        const count = data.faces.length;
        onNotice(count ? `لقينا ${count} وجه في الإطار` : "ما فيه وجه واضح الآن");
      } catch (err) {
        onNotice(err instanceof Error ? err.message : "صار خطأ أثناء التعرف.");
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [onNotice, onResult],
  );

  useEffect(() => {
    if (!auto) return;
    const timer = window.setInterval(() => run(false), status?.intervalMs ?? 1000);
    return () => window.clearInterval(timer);
  }, [auto, run, status?.intervalMs]);

  const state = status?.status ?? "connecting";
  const label = STATE_LABEL[state];
  const online = state === "online";
  const aspect = status?.width && status?.height ? `${status.width} / ${status.height}` : "16 / 9";

  return (
    <Card className="overflow-hidden p-3">
      <div className="relative overflow-hidden rounded-2xl bg-black" style={{ aspectRatio: aspect }}>
        {captured ? (
          <>
            <img src={captured.src} alt="لقطة من الكاميرا" className="block h-full w-full object-contain" />
            <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
          </>
        ) : online ? (
          <>
            <img src="/api/cameras/ezviz/stream" alt="بث كاميرا EZVIZ" className="block h-full w-full object-contain" />
            <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
          </>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm font-semibold text-white">
            {status?.message || label.text}
          </div>
        )}
      </div>
      <Card.Footer className="flex-wrap justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <Chip color={label.color} size="sm" variant="soft">
            {label.text}
          </Chip>
          {status?.fps ? <span>{status.fps} إطار/ث</span> : null}
          {status?.width ? (
            <span>
              {status.width}×{status.height}
            </span>
          ) : null}
          {status?.lastFrameAt ? <span>آخر إطار {new Date(status.lastFrameAt).toLocaleTimeString()}</span> : null}
          {lastRun ? <span>آخر تعرّف {new Date(lastRun.timestamp).toLocaleTimeString()}</span> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {captured ? (
            <Button size="sm" variant="secondary" onPress={() => setCaptured(null)}>
              رجوع للبث
            </Button>
          ) : null}
          <Button size="sm" isDisabled={!online || busy} onPress={() => run(true)}>
            التقاط والتعرف من كاميرا EZVIZ
          </Button>
          <Button
            size="sm"
            variant={auto ? "danger" : "secondary"}
            isDisabled={!online}
            onPress={() => {
              setCaptured(null);
              setAuto((value) => !value);
            }}
          >
            {auto ? "إيقاف التعرف التلقائي" : "بدء التعرف التلقائي"}
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
}
