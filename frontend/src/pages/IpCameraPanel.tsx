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

function drawBoxes(canvas: HTMLCanvasElement | null, data: IpRecognizeResponse, scale: number) {
  if (!canvas) return;
  canvas.width = data.frame_width * scale;
  canvas.height = data.frame_height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  data.faces.forEach((face: FaceMatch) => {
    const [x1, y1, x2, y2] = face.bbox.map((v) => v * scale);
    const color = face.known ? "#17c964" : "#f5a524";
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(3, canvas.width / 400);
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const size = Math.max(16, canvas.width / 60);
    ctx.font = `700 ${size}px Cairo`;
    const width = ctx.measureText(face.name).width + 16;
    ctx.fillStyle = color;
    ctx.fillRect(x1, Math.max(y1 - size - 14, 0), width, size + 12);
    ctx.fillStyle = "#fff";
    ctx.fillText(face.name, x1 + 8, Math.max(y1 - 10, size));
  });
}

export function IpCameraPanel({ classroomId, onResult, onNotice }: Props) {
  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [auto, setAuto] = useState(false);
  const [captured, setCaptured] = useState<{ src: string; data: IpRecognizeResponse } | null>(null);
  const [lastRun, setLastRun] = useState<IpRecognizeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const overlayRef = useRef<HTMLCanvasElement>(null);
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
      if (!selected) {
        onNotice("اختر الصف والشعبة عشان نبدأ التسجيل.");
        return;
      }
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
          <img src="/api/cameras/ezviz/stream" alt="بث كاميرا EZVIZ" className="block h-full w-full object-contain" />
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
          <Button size="sm" isDisabled={!online || busy || !classroomId} onPress={() => run(true)}>
            التقاط والتعرف من كاميرا EZVIZ
          </Button>
          <Button
            size="sm"
            variant={auto ? "danger" : "secondary"}
            isDisabled={!online || !classroomId}
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
