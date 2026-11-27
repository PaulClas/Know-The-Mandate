"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Landmark, Lock, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Async, Empty, Hash, KV, Notice, PageHeader, Spinner, StatusBadge } from "@/components/common";
import { useQ, useSession } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { mandateToCnl } from "@/lib/cnl";
import { formatMoney } from "@/lib/money";
import { actionLabel } from "@/lib/taxonomy";
import type { Agent, Approval, MandateSummary } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

type Lang = "en" | "fr";

export default function PortalPage() {
  const { user } = useSession();
  const isCustomer = user?.role === "customer";
  const accounts = useQ(["accounts"], api.accounts);
  const agents = useQ(["agents"], api.agents);
  const mandates = useQ(["mandates"], () => api.mandates(), { refetchInterval: 8000 });
  const approvals = useQ(["approvals"], api.approvals, { refetchInterval: 6000 });
  const customers = useQ(["customers"], api.customers);
  const [lang, setLang] = useState<Lang>("en");
  const [focus, setFocus] = useState<string | null>(null);

  // Alice (CA-QC) prefers French; other customers default to English
  useEffect(() => {
    const me = customers.data?.find((c) => c.id === user?.id);
    setLang(me?.jurisdiction === "CA-QC" ? "fr" : "en");
  }, [user?.id, customers.data]);
  useEffect(() => setFocus(new URLSearchParams(window.location.search).get("mandate")), []);

  const pending = (approvals.data ?? []).filter((a) => a.status === "PENDING");

  return (
    <>
      <PageHeader
        title="Customer banking portal"
        description={isCustomer ? `Signed in as ${user?.name}.` : `Viewing as ${user?.name} (${user?.role}). Switch to a customer in the header to approve or revoke.`}
        actions={
          <div className="flex items-center gap-1" role="group" aria-label="Language">
            {(["en", "fr"] as const).map((l) => <Button key={l} size="sm" variant={lang === l ? "default" : "outline"} onClick={() => setLang(l)}>{l.toUpperCase()}</Button>)}
          </div>
        }
      />
      <Notice tone="info" className="mb-4" title={<span className="flex items-center gap-1.5"><Lock size={13} /> Bank-controlled interface, independent of the agent</span>}>
        Approvals here are made on the bank&apos;s own surface — an agent can never approve for you. Demo assurance level: <Badge tone="warn" className="mono">DEMO_SIMULATED_SESSION</Badge> — a simulated bank session with a server-held demo key, not a passkey/WebAuthn step-up.
      </Notice>

      {pending.length > 0 && (
        <section className="mb-6" data-testid="pending-approvals">
          <h2 className="mb-2 text-sm font-semibold">Payments waiting for your approval ({pending.length})</h2>
          <div className="grid gap-3 lg:grid-cols-2">{pending.map((a) => <ApprovalCard key={a.id} a={a} canAct={isCustomer && a.eligible_approvers.includes(user!.id)} />)}</div>
        </section>
      )}

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Accounts" />
            <Async q={accounts} what="accounts">
              {(list) => list.length === 0 ? <Empty>No accounts.</Empty> : (
                <ul className="divide-y divide-border">
                  {list.map((a) => (
                    <li key={a.accountId} className="px-4 py-2.5">
                      <div className="flex items-center gap-2"><Landmark size={14} className="text-muted" /><span className="font-medium">{a.nickname}</span><Badge className="ml-auto">{a.accountType}</Badge></div>
                      <div className="mono mt-0.5 text-lg font-semibold tabular-nums">{formatMoney(a.availableBalanceMinor, a.currency)}</div>
                      <div className="mono text-[11px] text-muted">{a.accountId} · {a.cnl_ref}{a.reservedMinor ? ` · ${formatMoney(a.reservedMinor, a.currency)} reserved` : ""}</div>
                    </li>
                  ))}
                </ul>
              )}
            </Async>
          </Card>
          <Card>
            <CardHeader title="Connected agents" description="Authority each agent holds today, within bank limits." />
            <Async q={mandates} what="mandates">
              {(ms) => {
                const active = ms.filter((m) => m.status === "ACTIVE" || m.status === "SUSPENDED");
                return active.length === 0 ? <Empty>No agent currently holds authority.</Empty> : (
                  <ul className="divide-y divide-border">
                    {active.map((m) => <ConnectedAgent key={`${m.mandate_id}-${m.version}`} m={m} agent={agents.data?.find((a) => a.id === m.agent_id)} />)}
                  </ul>
                );
              }}
            </Async>
          </Card>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Mandates</h2>
            <span className="flex gap-3 text-xs"><Link href="/delegation" className="text-accent hover:underline">Delegation graph →</Link><Link href="/studio" className="text-accent hover:underline">New mandate in studio →</Link></span>
          </div>
          <Async q={mandates} what="mandates">
            {(ms) => ms.length === 0 ? <Card><Empty>No mandates yet. Create one in the Mandate studio.</Empty></Card> : (
              <div className="space-y-3">
                {ms.map((m) => <MandateCard key={`${m.mandate_id}-${m.version}`} m={m} lang={lang} isCustomer={isCustomer} focused={focus === m.mandate_id} agents={agents.data ?? []} />)}
              </div>
            )}
          </Async>
        </div>
      </div>
    </>
  );
}

function ConnectedAgent({ m, agent }: { m: MandateSummary; agent?: Agent }) {
  const v = useQ(["mandate", m.mandate_id, m.version], () => api.mandate(m.mandate_id, m.version));
  const effective = agent?.status === "VERIFIED" && m.status === "ACTIVE";
  return (
    <li className="px-4 py-2.5 text-[13px]">
      <div className="flex items-center gap-2">
        <span className="font-medium">{agent?.display_name ?? m.agent_id}</span>
        {agent && <StatusBadge kind="agent" status={agent.status} />}
        <StatusBadge kind="mandate" status={m.status} />
      </div>
      {!effective && <div className="text-xs text-warn">Not effective now: {agent?.status !== "VERIFIED" ? `agent is ${agent?.status}` : `mandate is ${m.status}`}</div>}
      <ul className="mt-1 space-y-0.5 text-xs">
        {v.data?.content.permissions.map((p, i) => (
          <li key={i} className={effective ? "" : "text-muted line-through"}>
            {actionLabel(p.action)} <span className="mono text-muted">on {p.resources.join(", ")}</span>
            {p.constraints.maximum_amount_minor ? <span className="text-muted"> · max {formatMoney(p.constraints.maximum_amount_minor, v.data!.content.currency)}</span> : null}
          </li>
        ))}
      </ul>
      {v.data?.content.aggregate_constraints.maximum_monthly_amount_minor ? <div className="mt-0.5 text-xs text-muted">Monthly budget {formatMoney(v.data.content.aggregate_constraints.maximum_monthly_amount_minor, m.currency)}</div> : null}
    </li>
  );
}

function MandateCard({ m, lang, isCustomer, focused, agents }: { m: MandateSummary; lang: Lang; isCustomer: boolean; focused: boolean; agents: Agent[] }) {
  const qc = useQueryClient();
  const v = useQ(["mandate", m.mandate_id, m.version], () => api.mandate(m.mandate_id, m.version));
  const accounts = useQ(["accounts"], api.accounts);
  const payees = useQ(["payees"], api.payees);
  const view = v.data;
  const [summary, setSummary] = useState<{ en: string; fr: string } | null>(null);
  const [open, setOpen] = useState(focused);

  useEffect(() => {
    if (!open || !view || !accounts.data || !payees.data || summary) return;
    api.compile({ principal_id: m.principal_id, cnl: mandateToCnl(view.content, agents, accounts.data, payees.data) })
      .then((r) => r.consent_summary && setSummary(r.consent_summary))
      .catch(() => undefined);
  }, [open, view, accounts.data, payees.data, agents, m.principal_id, summary]);

  const done = () => qc.invalidateQueries();
  const approve = useMutation({ mutationFn: () => api.approveMandate(m.mandate_id, view!.digest, m.version, lang), onSuccess: done });
  const activate = useMutation({ mutationFn: () => api.activateMandate(m.mandate_id, m.version), onSuccess: done });
  const suspend = useMutation({ mutationFn: () => api.suspendMandate(m.mandate_id), onSuccess: done });
  const resume = useMutation({ mutationFn: () => api.resumeMandate(m.mandate_id), onSuccess: done });
  const revoke = useMutation({ mutationFn: () => api.revokeMandate(m.mandate_id), onSuccess: done });
  const err = [approve, activate, suspend, resume, revoke].find((x) => x.error)?.error?.message;
  const busy = [approve, activate, suspend, resume, revoke].some((x) => x.isPending);
  const agent = agents.find((a) => a.id === m.agent_id);
  const c = view?.content;

  return (
    <Card className={focused ? "border-accent" : ""} data-testid={`mandate-${m.mandate_id}`}>
      <CardHeader
        title={<span className="flex flex-wrap items-center gap-2"><span className="mono">{m.mandate_id} v{m.version}</span><StatusBadge kind="mandate" status={m.status} /></span>}
        description={`${agent?.display_name ?? m.agent_id} · ${m.purpose} · expires ${fmtDateTime(m.expires_at)}`}
        actions={<Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>{open ? "Hide" : "Consent summary"}</Button>}
      />
      <CardBody className="space-y-3">
        {!view ? <Spinner /> : (
          <>
            <div className="grid gap-x-6 sm:grid-cols-2">
              <KV label="Digest"><Hash value={m.digest} /></KV>
              <KV label="Delegation">{c?.delegation.allowed ? `allowed, max depth ${c.delegation.maximum_depth}` : "not allowed"} · depth {c?.lineage?.depth ?? 0}{c?.lineage && <span className="text-muted"> (child of {c.lineage.parent_mandate_id})</span>}</KV>
              <KV label="Customer approval">{view.consent ? <Badge tone="ok">recorded</Badge> : <Badge tone="warn">not yet</Badge>}</KV>
              <KV label="Versions">{view.versions.map((x) => `v${x.version} ${x.status}`).join(" · ")}</KV>
            </div>
            {open && (
              <div>
                {summary ? <pre className="whitespace-pre-wrap rounded-md border border-border bg-surface2/50 p-3 text-[13px] leading-relaxed" data-testid="portal-consent">{summary[lang]}</pre> : <Spinner label="Rendering consent summary…" />}
              </div>
            )}
            {err && <Notice tone="bad">{err}</Notice>}
            {isCustomer && (
              <div className="flex flex-wrap gap-2">
                {m.status === "PENDING_CUSTOMER_APPROVAL" && !view.consent && <Button variant="success" size="sm" disabled={busy} onClick={() => approve.mutate()} data-testid="approve-mandate"><Check size={13} /> Approve this mandate ({lang.toUpperCase()})</Button>}
                {m.status === "PENDING_CUSTOMER_APPROVAL" && view.consent && <Button variant="accent" size="sm" disabled={busy} onClick={() => activate.mutate()} data-testid="activate-mandate">Activate</Button>}
                {m.status === "ACTIVE" && <Button variant="outline" size="sm" disabled={busy} onClick={() => suspend.mutate()}>Suspend</Button>}
                {m.status === "SUSPENDED" && <Button variant="outline" size="sm" disabled={busy} onClick={() => resume.mutate()}>Resume</Button>}
                {(m.status === "ACTIVE" || m.status === "SUSPENDED") && <Button variant="danger" size="sm" disabled={busy} onClick={() => revoke.mutate()} data-testid="revoke-mandate">Revoke</Button>}
              </div>
            )}
            {!isCustomer && <div className="text-xs text-muted">Only the customer can approve, suspend, resume or revoke in this interface.</div>}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function ApprovalCard({ a, canAct }: { a: Approval; canAct: boolean }) {
  const qc = useQueryClient();
  const d = a.display;
  const m = useMutation({ mutationFn: (x: "approve" | "reject") => api.decideApproval(a.id, x), onSuccess: () => qc.invalidateQueries() });
  return (
    <Card className="border-warn/50" data-testid="approval-card">
      <CardHeader title="Approve this payment?" description={`Requested by ${d.requesting_agent}${d.agent_operator ? ` (${d.agent_operator})` : ""}`} actions={<Badge tone="warn">expires {fmtDateTime(a.expires_at)}</Badge>} />
      <CardBody>
        <KV label="Account">{d.account}</KV>
        <KV label="Action">{actionLabel(d.action)}</KV>
        <KV label="Amount"><span className="text-base font-semibold">{formatMoney(d.amount_minor, d.currency)}</span></KV>
        <KV label="Beneficiary">{d.beneficiary}</KV>
        <KV label="Mandate" mono>{d.mandate}</KV>
        <KV label="Why approval">{a.reason}</KV>
        <KV label="Bound to">{a.binding}</KV>
        <p className="mt-2 text-xs text-muted">Approving once does not widen the mandate. {a.required_approvals > 1 ? `${a.required_approvals} approvals required (${a.grants.length} so far).` : ""}</p>
        {m.error && <Notice tone="bad" className="mt-2">{m.error.message}</Notice>}
        <div className="mt-3 flex gap-2">
          <Button variant="success" disabled={!canAct || m.isPending} onClick={() => m.mutate("approve")} data-testid="approve-once"><Check size={14} /> Approve once</Button>
          <Button variant="danger" disabled={!canAct || m.isPending} onClick={() => m.mutate("reject")}><X size={14} /> Reject</Button>
        </div>
        {!canAct && <p className="mt-1 text-xs text-muted">Only an eligible customer approver can decide.</p>}
      </CardBody>
    </Card>
  );
}
