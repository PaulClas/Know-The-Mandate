"use client";

import { Activity, CheckCircle2, FileX2, ShieldAlert, XCircle } from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Async, Hash, Notice, PageHeader, Stat } from "@/components/common";
import { useQ } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { isScenarioC } from "@/lib/scenarios";
import { fmtDateTime, humanize } from "@/lib/utils";

const DECISION_COLOR: Record<string, string> = { ALLOW: "#15803d", DENY: "#b91c1c", REQUIRE_HUMAN_APPROVAL: "#b45309", REFER_TO_RISK_REVIEW: "#c2410c" };

export default function OverviewPage() {
  const q = useQ(["overview"], api.overview, { refetchInterval: 15_000 });
  const sc = useQ(["scenarios"], api.scenarios);
  const scenarioC = sc.data?.find(isScenarioC);

  return (
    <>
      <div className="mb-4 rounded-lg border border-border bg-navy px-5 py-4 text-white dark:bg-surface2">
        <div className="text-[11px] font-medium uppercase tracking-widest opacity-70">KYM — Know Your Mandate · Meridian Bank</div>
        <p className="mt-1 text-lg font-semibold leading-snug tracking-tight md:text-xl" data-testid="tagline">
          The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers.
        </p>
        <p className="mt-1.5 text-xs opacity-80">Synthetic demo — not compliant or certified. All customers, accounts, agents and payments are fictional.</p>
      </div>

      <PageHeader title="Executive overview" description="Financial authority delegated to AI agents: who is allowed to act, under which mandate, and what the bank can prove afterwards." />

      <Async q={q} what="overview">
        {(o) => {
          const dist = Object.entries(o.decision_distribution).map(([name, value]) => ({ name, value }));
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Stat label="Registered agents" value={o.registered_agents} sub={`${o.verified_agents} bank-verified`} />
                <Stat label="Active mandates" value={o.active_mandates} sub={`${o.revoked_mandates} revoked`} />
                <Stat label="Pending customer approvals" value={o.pending_customer_approvals + o.pending_transaction_approvals} tone={o.pending_customer_approvals + o.pending_transaction_approvals ? "warn" : undefined} sub={`${o.pending_customer_approvals} mandates · ${o.pending_transaction_approvals} payments`} />
                <Stat label="Authorized payments" value={formatMoney(o.total_authorized_payments_minor, "CAD")} sub={`${o.executed_payments} executed`} tone="ok" />
                <Stat label="Denied actions" value={o.denied_actions} tone={o.denied_actions ? "bad" : undefined} />
                <Stat label="Revoked mandates" value={o.revoked_mandates} />
                <Card className="col-span-2 p-3.5" data-testid="ledger-integrity">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-muted">Evidence ledger integrity</div>
                  <div className="mt-1.5 flex items-center gap-2">
                    {o.ledger.ok ? (
                      <Badge tone="ok" className="px-2 py-1 text-xs"><CheckCircle2 size={13} /> VERIFIED</Badge>
                    ) : (
                      <Badge tone="bad" className="px-2 py-1 text-xs"><XCircle size={13} /> INTEGRITY FAILURE</Badge>
                    )}
                    <span className="text-xs text-muted">{o.ledger.events} events · {o.ledger.checkpoints} checkpoints</span>
                  </div>
                  <div className="mt-1.5 text-xs text-muted">
                    head hash <Hash value={o.ledger.head_hash} head={12} tail={8} />
                  </div>
                </Card>
              </div>

              {scenarioC ? (
                <FeaturedC id={scenarioC.id} title={scenarioC.title} />
              ) : (
                <FeaturedC />
              )}

              <div className="grid gap-4 lg:grid-cols-5">
                <Card className="lg:col-span-2">
                  <CardHeader title="Decision distribution" description="Policy decisions on agent-attempted actions" />
                  <CardBody>
                    {dist.length === 0 ? (
                      <div className="py-10 text-center text-[13px] text-muted">No agent actions decided yet. Run a scenario or the playground.</div>
                    ) : (
                      <div className="h-56">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={dist} margin={{ left: -20, right: 8 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                            <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted)" }} tickFormatter={(v: string) => humanize(v.toLowerCase())} interval={0} />
                            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--muted)" }} />
                            <RTooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", fontSize: 12 }} />
                            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                              {dist.map((d) => (
                                <Cell key={d.name} fill={DECISION_COLOR[d.name] ?? "#64748b"} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </CardBody>
                </Card>
                <Card className="lg:col-span-3">
                  <CardHeader title="Recent activity" description="Latest evidence ledger events" actions={<Link href="/ledger" className="text-xs text-accent hover:underline">Open ledger</Link>} />
                  <ul className="divide-y divide-border">
                    {o.recent_events.map((e) => (
                      <li key={e.event_id} className="flex items-center gap-3 px-4 py-2 text-[13px]">
                        <Activity size={13} className="shrink-0 text-muted" />
                        <Badge className="mono">{e.event_type}</Badge>
                        <span className="min-w-0 flex-1 truncate text-muted">
                          {e.actor_id}
                          {e.agent_id ? ` · ${e.agent_id}` : ""}
                          {e.mandate_id ? ` · ${e.mandate_id} v${e.mandate_version}` : ""}
                        </span>
                        <span className="shrink-0 text-xs text-muted">#{e.sequence} · {fmtDateTime(e.timestamp)}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
              <Notice tone="warn" title="Synthetic demo — not compliant or certified">
                {o.disclaimer} Sandbox OAuth, simulated sessions and simulated attestations stand in for production controls.
              </Notice>
            </div>
          );
        }}
      </Async>
    </>
  );
}

function FeaturedC({ id, title }: { id?: string; title?: string }) {
  return (
    <Card className="border-accent/40" data-testid="featured-scenario-c">
      <div className="flex flex-wrap items-center gap-4 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-accent/10 text-accent">
          <ShieldAlert size={20} />
        </div>
        <div className="min-w-[260px] flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Scenario C — valid OAuth token, invalid mandate</h3>
            <Badge tone="accent">central KYM point</Badge>
          </div>
          <p className="mt-0.5 text-[13px] text-muted">
            The agent presents a perfectly valid, correctly bound access token. The bank still denies the payment because the <em>mandate</em> — not the token — does not authorize it. OAuth proves who may call; the mandate decides what may be done.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href={id ? `/scenarios?run=${encodeURIComponent(id)}` : "/scenarios"}>
            <Button variant="accent">{id ? `Run ${title ?? "Scenario C"}` : "Open scenarios"}</Button>
          </Link>
          <Link href="/playground?preset=token_ok_mandate_bad">
            <Button variant="outline"><FileX2 size={14} /> Try in playground</Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
