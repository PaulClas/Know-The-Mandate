"use client";

import { AlertTriangle, Check, CheckCircle2, Circle, Copy, Info, Loader2, MinusCircle, ShieldAlert, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { cn, short } from "@/lib/utils";
import { Badge, type Tone } from "./ui/badge";
import { Card } from "./ui/card";

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-0.5 max-w-3xl text-[13px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Notice({ tone = "info", title, children, className }: { tone?: "info" | "warn" | "bad" | "ok"; title?: ReactNode; children?: ReactNode; className?: string }) {
  const map = { info: "bg-infobg text-info border-info/25", warn: "bg-warnbg text-warn border-warn/25", bad: "bg-badbg text-bad border-bad/25", ok: "bg-okbg text-ok border-ok/25" };
  const Icon = tone === "bad" ? XCircle : tone === "warn" ? AlertTriangle : tone === "ok" ? CheckCircle2 : Info;
  return (
    <div className={cn("flex gap-2 rounded-md border px-3 py-2 text-[13px]", map[tone], className)}>
      <Icon size={15} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className={cn(title && "opacity-90")}>{children}</div>}
      </div>
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-[13px] text-muted">
      <Loader2 size={15} className="animate-spin" /> {label}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-6 text-center text-[13px] text-muted">{children}</div>;
}

/** Renders loading / error / "backend pending" states for a query; never a blank screen. */
export function Async<T>({ q, what, children }: { q: UseQueryResult<T, ApiError>; what: string; children: (data: T) => ReactNode }) {
  if (q.isLoading || (q.isFetching && !q.data && !q.error)) return <Spinner label={`Loading ${what}…`} />;
  if (q.error) return <ErrorState error={q.error} what={what} onRetry={() => q.refetch()} />;
  if (q.data === undefined) return <Empty>No data.</Empty>;
  return <>{children(q.data)}</>;
}

export function ErrorState({ error, what, onRetry }: { error: ApiError | Error; what: string; onRetry?: () => void }) {
  const status = error instanceof ApiError ? error.status : 0;
  if (error instanceof ApiError && error.pending)
    return (
      <Card className="m-0 p-6 text-center">
        <ShieldAlert className="mx-auto mb-2 text-warn" size={22} />
        <div className="font-medium">Backend endpoint pending</div>
        <p className="mx-auto mt-1 max-w-md text-[13px] text-muted">
          {what} is not available yet (HTTP {status}). This page is built against the API contract and will light up once the endpoint lands.
        </p>
        {onRetry && (
          <button onClick={onRetry} className="mt-3 cursor-pointer text-[13px] text-accent hover:underline">
            Retry
          </button>
        )}
      </Card>
    );
  return (
    <Notice tone="bad" title={`Could not load ${what}`}>
      <span>{error.message}</span>
      {onRetry && (
        <button onClick={onRetry} className="ml-2 cursor-pointer underline">
          Retry
        </button>
      )}
    </Notice>
  );
}

export function CopyButton({ value, className }: { value: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      title="Copy"
      aria-label="Copy"
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(value);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
      className={cn("inline-flex cursor-pointer items-center text-muted hover:text-foreground", className)}
    >
      {done ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
    </button>
  );
}

/** Truncated monospace identifier/hash with copy. */
export function Hash({ value, head = 8, tail = 6, full = false }: { value: string | null | undefined; head?: number; tail?: number; full?: boolean }) {
  if (!value) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-1" title={value}>
      <span className="mono break-all">{full ? value : short(value, head, tail)}</span>
      <CopyButton value={value} />
    </span>
  );
}

export function JsonView({ data, maxH = "max-h-80", className }: { data: unknown; maxH?: string; className?: string }) {
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return (
    <div className={cn("relative rounded-md border border-border bg-surface2/50", className)}>
      <div className="absolute right-2 top-2">
        <CopyButton value={text} />
      </div>
      <pre className={cn("mono overflow-auto p-3 pr-8 text-[12px] leading-relaxed", maxH)}>{text}</pre>
    </div>
  );
}

// ---- status & decision chips

const MANDATE_TONE: Record<string, Tone> = {
  ACTIVE: "ok", PENDING_CUSTOMER_APPROVAL: "warn", VALIDATED: "info", DRAFT: "neutral", PENDING_VALIDATION: "neutral",
  SUSPENDED: "warn", REVOKED: "bad", EXPIRED: "neutral", SUPERSEDED: "neutral", REJECTED: "bad",
};
const AGENT_TONE: Record<string, Tone> = { VERIFIED: "ok", PENDING_VERIFICATION: "warn", RESTRICTED: "risk", SUSPENDED: "bad", REVOKED: "bad", UNREGISTERED: "neutral" };
const TX_TONE: Record<string, Tone> = {
  EXECUTED: "ok", COMPLETED: "ok", DENIED: "bad", PENDING_APPROVAL: "warn", RISK_REVIEW: "risk", CANCELLED: "neutral", FAILED: "bad", AUTHORIZED: "info", REVIEW_CLEARED: "info",
};

export function StatusBadge({ status, kind }: { status: string | null | undefined; kind: "mandate" | "agent" | "tx" }) {
  if (!status) return <Badge>—</Badge>;
  const map = kind === "mandate" ? MANDATE_TONE : kind === "agent" ? AGENT_TONE : TX_TONE;
  return <Badge tone={map[status] ?? "neutral"}>{status.replace(/_/g, " ")}</Badge>;
}

const DECISION: Record<string, { tone: Tone; label: string }> = {
  ALLOW: { tone: "ok", label: "ALLOW" },
  DENY: { tone: "bad", label: "DENY" },
  REQUIRE_HUMAN_APPROVAL: { tone: "warn", label: "REQUIRE HUMAN APPROVAL" },
  REFER_TO_RISK_REVIEW: { tone: "risk", label: "REFER TO RISK REVIEW" },
};
export function DecisionBadge({ decision, className }: { decision: string | null | undefined; className?: string }) {
  if (!decision) return <Badge className={className}>—</Badge>;
  const d = DECISION[decision] ?? { tone: "neutral" as Tone, label: decision };
  return <Badge tone={d.tone} className={className}>{d.label}</Badge>;
}

export function DecisionPill({ decision }: { decision: string }) {
  const d = DECISION[decision] ?? { tone: "neutral" as Tone, label: decision };
  const cls: Record<Tone, string> = {
    ok: "bg-ok text-white dark:text-black", bad: "bg-bad text-white dark:text-black", warn: "bg-warn text-white dark:text-black", risk: "bg-risk text-white dark:text-black",
    neutral: "bg-muted text-white", info: "bg-info text-white", accent: "bg-accent text-accentfg",
  };
  return <span data-testid="decision-pill" data-decision={decision} className={cn("inline-flex items-center rounded-md px-3 py-1.5 text-sm font-semibold tracking-wide", cls[d.tone])}>{d.label}</span>;
}

export function OutcomeIcon({ outcome, size = 15 }: { outcome: string; size?: number }) {
  switch (outcome) {
    case "PASS":
      return <CheckCircle2 size={size} className="text-ok" />;
    case "FAIL":
      return <XCircle size={size} className="text-bad" />;
    case "SKIP":
      return <MinusCircle size={size} className="text-muted" />;
    case "REFER":
      return <AlertTriangle size={size} className="text-risk" />;
    case "REQUIRE_APPROVAL":
      return <AlertTriangle size={size} className="text-warn" />;
    default:
      return <Info size={size} className="text-info" />;
  }
}

export function ReasonCodes({ codes }: { codes?: string[] | null }) {
  if (!codes?.length) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {codes.map((c) => (
        <Badge key={c} tone="neutral" className="mono">
          {c}
        </Badge>
      ))}
    </span>
  );
}

export function KV({ label, children, mono }: { label: ReactNode; children: ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-2 py-1 text-[13px]">
      <div className="text-muted">{label}</div>
      <div className={cn("min-w-0 break-words", mono && "mono")}>{children ?? "—"}</div>
    </div>
  );
}

export function Dot() {
  return <Circle size={6} className="fill-current" />;
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone }) {
  const color = tone === "bad" ? "text-bad" : tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "";
  return (
    <Card className="p-3.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={cn("mt-1 text-2xl font-semibold tabular-nums tracking-tight", color)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </Card>
  );
}
