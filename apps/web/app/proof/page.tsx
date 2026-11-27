"use client";

import { useMutation } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { Notice, PageHeader, Spinner } from "@/components/common";
import { useSession } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api, type RedteamRow, type Tier } from "@/lib/api";

const TIERS: [string, string][] = [
  ["scope_only", "Scope-only bank"],
  ["rar_static", "OAuth + static RAR"],
  ["kym", "KYM"],
];

function Cell({ t, gap }: { t?: Tier; gap?: boolean }) {
  if (!t) return <Badge tone="warn">error</Badge>;
  if (t.blocked === null) return <Badge>n/a</Badge>;
  if (t.blocked) return <Badge tone="ok">blocked</Badge>;
  return <Badge tone={gap ? "warn" : "bad"}>succeeded</Badge>;
}

export default function ProofPage() {
  const { user } = useSession();
  const can = user?.role === "admin" || user?.role === "investigator";
  const run = useMutation({ mutationFn: api.redteamRun });
  const rep = run.data;

  return (
    <>
      <PageHeader
        title="Prove it (or break it)"
        description="Every attack uses the same real, validly signed access token against three designs. Baselines are deliberately simple models of common designs. Results are measured on this run, not asserted."
        actions={
          <Button variant="accent" disabled={!can || run.isPending} onClick={() => run.mutate()} data-testid="run-redteam">
            <Play size={14} /> {run.isPending ? "Running attacks…" : "Run all attacks"}
          </Button>
        }
      />
      {!can && <Notice tone="warn" className="mb-4" title="Bank operator or investigator required">Switch user in the header. Running creates synthetic mandates and transactions; use “Reset demo” on the Scenarios page afterwards.</Notice>}
      <Notice tone="info" className="mb-4" title="Self-assessment">
        This harness was written by KYM&apos;s authors. It is falsifiable and reproducible (<span className="mono">make redteam</span>), not an independent audit. One attack is an intentional <b>honest gap</b>: a wrong payment that stays inside the mandate cannot be detected by mandate enforcement.
      </Notice>
      {run.isPending && <Spinner label="Running 23 attacks (about 10–20 seconds)…" />}
      {run.error && <Notice tone="bad" className="mb-4">{run.error.message}</Notice>}
      {rep && (
        <div className="space-y-4" data-testid="redteam-report">
          <div className="grid gap-3 sm:grid-cols-3">
            {TIERS.map(([k, label]) => (
              <Card key={k}>
                <CardBody>
                  <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
                  <div className="text-2xl font-semibold" data-testid={`tally-${k}`}>{rep.summary[k as "kym"].blocked}/{rep.summary[k as "kym"].applicable}</div>
                  <div className="text-xs text-muted">applicable attacks blocked (honest case excluded)</div>
                </CardBody>
              </Card>
            ))}
          </div>
          <Notice tone={rep.summary.errors.length ? "bad" : "ok"} title="Not blocked by KYM">
            {rep.summary.kym_not_blocked.length ? <span className="mono">{rep.summary.kym_not_blocked.join(", ")}</span> : "none"}
            {rep.summary.errors.length ? <> · harness errors: {rep.summary.errors.join(", ")}</> : null}
          </Notice>
          <Card>
            <CardHeader title="Attack matrix" description="blocked = no money moved / no integrity or availability harm" />
            <CardBody className="overflow-x-auto p-0">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted">
                    <th className="p-2">Attack</th>
                    {TIERS.map(([k, l]) => <th key={k} className="p-2">{l}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rep.attacks.map((r: RedteamRow) => (
                    <tr key={r.id} className="border-b border-border/60 align-top" data-testid={`attack-${r.id}`}>
                      <td className="p-2">
                        <div className="font-medium">{r.title}</div>
                        <div className="mono text-[11px] text-muted">{r.category} · {r.refs.join(" · ")}</div>
                        <details className="mt-1">
                          <summary className="cursor-pointer text-[11px] text-muted">details</summary>
                          <ul className="mt-1 space-y-0.5 text-[12px]">
                            {Object.entries(r.results).map(([t, v]) => <li key={t}><span className="mono">{t}</span>: {v.detail}</li>)}
                            {r.note && <li className="text-muted">Note: {r.note}</li>}
                            {r.error && <li className="text-bad">Error: {r.error}</li>}
                          </ul>
                        </details>
                      </td>
                      {TIERS.map(([k]) => <td key={k} className="p-2"><Cell t={r.results[k]} gap={r.expected_gap} /></td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        </div>
      )}
    </>
  );
}
