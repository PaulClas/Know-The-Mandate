import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "ok" | "warn" | "risk" | "bad" | "info" | "accent";
const tones: Record<Tone, string> = {
  neutral: "bg-surface2 text-muted border-border",
  ok: "bg-okbg text-ok border-ok/25",
  warn: "bg-warnbg text-warn border-warn/25",
  risk: "bg-riskbg text-risk border-risk/25",
  bad: "bg-badbg text-bad border-bad/25",
  info: "bg-infobg text-info border-info/25",
  accent: "bg-accent/10 text-accent border-accent/30",
};

export function Badge({ tone = "neutral", className, ...p }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap", tones[tone], className)}
      {...p}
    />
  );
}
