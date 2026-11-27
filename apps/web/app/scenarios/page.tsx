"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Play, RotateCcw, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Async, JsonView, Notice, PageHeader, ReasonCodes, Spinner } from "@/components/common";
import { useQ, useSession } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { isScenarioC, scenarioLetter } from "@/lib/scenarios";
import type { ScenarioMeta, ScenarioRun } from "@/lib/types";
import { DecisionBadge } from "@/components/common";

export default function ScenariosPage() {
  const { user } = useSession();
  const isAdmin = user?.role === "admin";
  const q = useQ(["scenarios"], api.scenarios);
  const qc = useQueryClient();
  const [runs, setRuns] = useState<Record<string, ScenarioRun>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const auto = useRef(false);

  const run = async (id: string) => {
    setRunning(id);
    setError(null);
    try {
      const r = await api.runScenario(id);
      setRuns((x) => ({ ...x, [id]: r }));
      qc.invalidateQueries({ predicate: (qq) => !(qq.queryKey as string[]).includes("scenarios") });
    } catch (e) {
      setError(`Scenario ${id}: ${(e as Error).message}`);
    } finally {
      setRunning(null);
    }
  };

  const reset = useMutation({
    mutationFn: api.resetDemo,
    onSuccess: () => {
      setRuns({});
      qc.invalidateQueries();
    },
  });

  useEffect(() => {
    const want = new URLSearchParams(window.location.search).get("run");
    if (want && isAdmin && q.data && !auto.current) {
      auto.current = true;
      run(want);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data, isAdmin]);

  return (
    <>
      <PageHeader
        title="Scenarios A–M"
        description="One-click demonstrations that drive the real OAuth server, gateway, policy engine and ledger — and check the outcome against what is expected."
        actions={
          <Button variant="outline" disabled={!isAdmin || reset.isPending} onClick={() => reset.mutate()} data-testid="reset-demo" title={isAdmin ? "" : "Bank operator only"}>
            <RotateCcw size={14} /> Reset demo
          </Button>
        }
      />
      {!isAdmin && <Notice tone="warn" className="mb-4" title="Running scenarios and resetting the demo require the bank operator">Switch to “Meridian Bank Operator” in the header.</Notice>}
      {reset.error && <Notice tone="bad" className="mb-4">{reset.error.message}</Notice>}
      {error && <Notice tone="bad" className="mb-4">{error}</Notice>}
      <Async q={q} what="scenarios">
        {(list) => {
          const featured = list.filter(isScenarioC);
          const rest = list.filter((s) => !isScenarioC(s));
          return (
            <div className="space-y-4">
              {featured.map((s) => <ScenarioCard key={s.id} s={s} run={runs[s.id]} busy={running === s.id} canRun={isAdmin && !running} onRun={() => run(s.id)} featured />)}
              <div className="grid gap-4 lg:grid-cols-2">
                {rest.map((s) => <ScenarioCard key={s.id} s={s} run={runs[s.id]} busy={running === s.id} canRun={isAdmin && !running} onRun={() => run(s.id)} />)}
              </div>
            </div>
          );
        }}
      </Async>
    </>
  );
}

function ScenarioCard({ s, run, busy, canRun, onRun, featured }: { s: ScenarioMeta; run?: ScenarioRun; busy: boolean; canRun: boolean; onRun: () => void; featured?: boolean }) {
  const letter = scenarioLetter(s) ?? s.id;
  return (
    <Card className={featured ? "border-2 border-accent/50" : ""} data-testid={`scenario-${s.id}`}>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-navy text-xs font-semibold text-white dark:bg-accent dark:text-accentfg">{letter}</span>
            {s.title}
            {featured && <Badge tone="accent">central KYM point</Badge>}
          </span>
        }
        description={s.group}
        actions={
          <Button size="sm" variant="accent" disabled={!canRun || busy} onClick={onRun} data-testid={`run-${s.id}`}>
            <Play size={13} /> {busy ? "Running…" : "Run"}
          </Button>
        }
      />
      <CardBody className="space-y-3">
        <p className="text-[13px]">{s.description}</p>
        <div className="text-xs text-muted"><span className="font-medium">Expected:</span> {s.expected}</div>
        {busy && <Spinner label="Running scenario…" />}
        {run && <RunResult r={run} />}
      </CardBody>
    </Card>
  );
}

function RunResult({ r }: { r: ScenarioRun }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-surface2/40 p-3" data-testid={`result-${r.id}`}>
      <div className="flex items-center gap-2">
        <Badge tone={r.passed ? "ok" : "bad"} className="px-2 py-1 text-xs" data-testid="scenario-passed">{r.passed ? "PASSED" : "FAILED"}</Badge>
        <span className="text-xs text-muted">{r.summary}</span>
      </div>
      <ol className="space-y-2">
        {r.steps.map((st, i) => (
          <li key={i} className="flex gap-2 text-[13px]">
            {st.ok ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-ok" /> : <XCircle size={15} className="mt-0.5 shrink-0 text-bad" />}
            <div className="min-w-0 flex-1">
              <div className="font-medium">{st.title}</div>
              {st.detail && <div className="text-xs text-muted">{st.detail}</div>}
              {(st.decision || st.status || st.reason_codes?.length) && (
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {st.status !== undefined && <Badge className="mono">HTTP {String(st.status)}</Badge>}
                  {st.decision && <DecisionBadge decision={st.decision} />}
                  <ReasonCodes codes={st.reason_codes} />
                </div>
              )}
              {st.note && <div className="mt-0.5 text-[11px] text-muted">{st.note}</div>}
              {st.request !== undefined && st.request !== null && (
                <details className="mt-1"><summary className="cursor-pointer text-[11px] text-muted">request</summary><JsonView data={st.request} maxH="max-h-40" /></details>
              )}
            </div>
          </li>
        ))}
      </ol>
      {r.learn && <Notice tone="info" title="What this shows">{r.learn}</Notice>}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {r.correlation_ids.map((c) => <Link key={c} className="mono text-accent hover:underline" href={`/ledger?q=${c}`}>{c}</Link>)}
        {r.transaction_ids?.map((t) => <Link key={t} className="mono text-accent hover:underline" href={`/disputes?tx=${t}`}>{t}</Link>)}
      </div>
    </div>
  );
}
