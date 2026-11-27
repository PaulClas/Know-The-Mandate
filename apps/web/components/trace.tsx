"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import type { RiskAssessment, TraceItem } from "@/lib/types";
import { OutcomeIcon } from "./common";

export function TraceChecklist({ trace }: { trace: TraceItem[] }) {
  if (!trace?.length) return <div className="p-4 text-[13px] text-muted">No trace available.</div>;
  const counts = trace.reduce<Record<string, number>>((a, t) => ((a[t.outcome] = (a[t.outcome] ?? 0) + 1), a), {});
  return (
    <div data-testid="trace">
      <div className="flex flex-wrap gap-1.5 border-b border-border px-3 py-2 text-xs">
        {Object.entries(counts).map(([k, v]) => (
          <Badge key={k} tone={k === "PASS" ? "ok" : k === "FAIL" ? "bad" : k === "SKIP" ? "neutral" : k === "INFO" ? "info" : "warn"}>{v} {k}</Badge>
        ))}
      </div>
      <ul className="divide-y divide-border">
        {trace.map((t, i) => (
          <li key={`${t.id}-${i}`} className="flex items-start gap-2 px-3 py-1.5 text-[13px]" data-outcome={t.outcome}>
            <span className="mt-0.5"><OutcomeIcon outcome={t.outcome} /></span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2">
                <span className={t.outcome === "FAIL" ? "font-medium text-bad" : "font-medium"}>{t.name}</span>
                {t.reason_code && t.outcome !== "PASS" && <Badge tone="bad" className="mono">{t.reason_code}</Badge>}
                {t.rule && <span className="mono text-[11px] text-muted">rule: {t.rule}</span>}
              </div>
              <div className="text-xs text-muted">{t.detail}</div>
            </div>
            <span className="mono shrink-0 text-[10px] text-muted">{t.outcome}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RiskPanel({ risk }: { risk?: RiskAssessment | null }) {
  if (!risk) return null;
  const tone = risk.level === "LOW" ? "ok" : risk.level === "MEDIUM" ? "warn" : "bad";
  return (
    <Card data-testid="risk-panel">
      <CardHeader title="Risk signals" description="Synthetic rules-based screening; independent of the mandate decision." actions={<><Badge tone={tone}>{risk.level}</Badge><span className="text-lg font-semibold tabular-nums">{risk.score}</span></>} />
      <ul className="divide-y divide-border">
        {(risk.signals ?? []).map((s, i) => (
          <li key={s.id ?? i} className="flex items-start gap-2 px-3 py-1.5 text-[13px]">
            <span className={s.triggered ? "text-warn" : "text-muted"}>{s.triggered ? "▲" : "○"}</span>
            <div className="min-w-0 flex-1">
              <span className="mono text-xs">{s.id}</span>
              <div className="text-xs text-muted">{s.detail}</div>
            </div>
            <span className="mono text-xs tabular-nums">{s.triggered ? `+${s.points}` : "0"}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
