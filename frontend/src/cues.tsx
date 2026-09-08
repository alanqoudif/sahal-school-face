import { Chip } from "@heroui/react";
import type { FaceCues } from "./types";

type Tone = "success" | "warning" | "danger" | "accent" | "default";

function cueTone(kind: "expression" | "attention" | "quality", value: string): Tone {
  if (kind === "expression") {
    if (value === "سعيد") return "success";
    if (value === "متفاجئ") return "accent";
    if (value === "متعب") return "warning";
    if (value === "منزعج") return "danger";
    return "default";
  }
  if (kind === "attention") {
    if (value === "منتبه") return "success";
    return "warning";
  }
  if (value === "واضحة") return "success";
  if (value === "ضعيفة") return "danger";
  return "default";
}

export function cueLine(cues: FaceCues | null | undefined): string {
  return [cues?.expression, cues?.attention, cues?.quality].filter(Boolean).join(" · ");
}

export function CueChips({ cues, size = "sm" }: { cues: FaceCues | null | undefined; size?: "sm" | "md" }) {
  const items = [
    { kind: "expression" as const, value: cues?.expression },
    { kind: "attention" as const, value: cues?.attention },
    { kind: "quality" as const, value: cues?.quality },
  ].filter((item) => item.value);

  if (!items.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Chip key={item.kind} size={size} color={cueTone(item.kind, item.value || "")} variant="soft">
          {item.value}
        </Chip>
      ))}
    </div>
  );
}
