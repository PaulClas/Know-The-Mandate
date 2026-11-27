"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Gavel } from "lucide-react";
import { useEffect, useState } from "react";
import { Async, Empty, Hash, JsonView, KV, Notice, PageHeader, ReasonCodes, StatusBadge } from "@/components/common";
import { useQ } from "@/components/providers";
import { RiskPanel, TraceChecklist } from "@/components/trace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, downloadEvidence } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import type { EvidencePackage, ResponsibilityMatrixDef } from "@/lib/types";
import { fmtDateTime, humanize } from "@/lib/utils";

export default function DisputesPage() {
  const txs = useQ(["transactions", ""], () => api.transactions());
  const [tx, setTx] = useState("");
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("tx");
    if (p) setTx(p);
  }, []);
  useEffect(() => {
    if (!tx && txs.data?.length) setTx(txs.data[0].id);
  }, [txs.data, tx]);
  const ev = useQ(["evidence", tx], () => api.evidence(tx), { enabled: !!tx });

  return (
    <>
      <PageHeader title="Dispute investigation" description="Reconstruct what happened from signed evidence. This system attributes who did what; it never decides who is liable." />
      <Notice tone="warn" className="mb-4" title="No liability determination is made here">
        Technical evidence can show which party performed or controlled each step. Contractual allocation, potential legal liability and final adjudicated liability require contracts, legal analysis and a competent body.
      </Notice>
      <Card className="mb-4">
        <CardBody className="flex flex-wrap items-end gap-3">
          <div className="min-w-[320px] flex-1">
            <Label>Transaction</Label>
            <Select value={tx} onChange={(e) => setTx(e.target.value)} data-testid="tx-select">
              {(txs.data ?? []).length === 0 && <option value="">No transactions</option>}
              {(txs.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.id} · {t.status} · {t.action} · {formatMoney(t.amount_minor, t.currency)}</option>)}
              {tx && !(txs.data ?? []).some((t) => t.id === tx) && <option value={tx}>{tx}</option>}
            </Select>
          </div>
          {tx && ev.data && <DisputeActions tx={tx} dispute={ev.data.transaction.dispute} />}
        </CardBody>
      </Card>
      {!tx ? <Card><Empty>No transactions yet. Run a scenario or sandbox conversation first.</Empty></Card> : (
        <Async q={ev} what="evidence package">{(e) => <Investigation e={e} />}</Async>
      )}
      <MatrixExplorer />
    </>
  );
}

function DisputeActions({ tx, dispute }: { tx: string; dispute?: Record<string, unknown> | null }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("Customer does not recognise this payment");
  const open = useMutation({ mutationFn: () => api.openDispute(tx, reason), onSuccess: () => qc.invalidateQueries() });
  const dl = useMutation({ mutationFn: () => downloadEvidence(tx) });
  return (
    <div className="flex flex-wrap items-end gap-2">
      {dispute ? <Badge tone="warn">Dispute {String(dispute.status ?? "OPEN")}</Badge> : (
        <>
          <Input className="w-72" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Dispute reason" />
          <Button variant="outline" onClick={() => open.mutate()} disabled={open.isPending || !reason}><Gavel size={14} /> Open dispute</Button>
        </>
      )}
      <Button variant="accent" onClick={() => dl.mutate()} disabled={dl.isPending} data-testid="download-evidence"><Download size={14} /> Download evidence package</Button>
      {(open.error || dl.error) && <span className="text-xs text-bad">{(open.error ?? dl.error)?.message}</span>}
    </div>
  );
}

function Investigation({ e }: { e: EvidencePackage }) {
  const t = e.transaction;
  const agentDecl = (e.agent?.declared_metadata ?? {}) as Record<string, string>;
  const verified = e.agent?.verified_facts as Record<string, unknown> | undefined;
  const op = e.operation?.operation as Record<string, unknown> | undefined;
  const grant = e.oauth_grant as Record<string, unknown> | null | undefined;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Timeline reconstruction" description="Ordered, signed events leading to and following the operation" actions={<StatusBadge kind="tx" status={t.status} />} />
          <ol className="relative ml-5 space-y-3 border-l border-border py-3 pr-3 pl-4" data-testid="timeline">
            {(e.timeline ?? []).map((it, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-accent bg-surface" />
                <div className="flex flex-wrap items-center gap-2"><Badge className="mono">{it.title}</Badge><span className="text-xs text-muted">{fmtDateTime(it.at)}</span></div>
                <div className="text-xs text-muted">{it.actor}</div>
                {it.detail && <div className="mono mt-0.5 line-clamp-2 break-all text-[11px] text-muted" title={it.detail}>{it.detail}</div>}
              </li>
            ))}
          </ol>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Parties & identity" />
            <CardBody className="py-2">
              <KV label="Customer">{String(e.customer?.name ?? "")} <span className="mono text-xs text-muted">{String(e.customer?.id ?? "")}</span> · {String(e.customer?.jurisdiction ?? "")} · KYC {String(e.customer?.kyc_status ?? "")}</KV>
              <KV label="Agent">{String(e.agent?.display_name ?? "")} <span className="mono text-xs text-muted">{String(e.agent?.id ?? "")}</span> <span className="text-xs text-muted">(now {String(e.agent?.status_now ?? "")})</span></KV>
              <KV label="Operator">{String(e.operator?.name ?? "")} <span className="text-muted">· responsible party: {String(e.operator?.responsible_party ?? "")}</span></KV>
              <KV label="Agent key thumbprint"><Hash value={String(e.agent?.key_thumbprint ?? "")} /></KV>
              <KV label="Declared by agent">{agentDecl.model_provider} / {agentDecl.model_id} · v{agentDecl.software_version}</KV>
              <KV label="Verified by bank">{verified ? <Badge tone="warn">{String(verified.assurance)}</Badge> : "—"}</KV>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Mandate & consent" />
            <CardBody className="py-2">
              <KV label="Mandate" mono>{e.mandate?.content ? `${e.mandate.content.mandate_id} v${e.mandate.content.version}` : "—"} <StatusBadge kind="mandate" status={e.mandate?.status_now} /></KV>
              <KV label="Digest"><Hash value={e.mandate?.digest} full /></KV>
              <KV label="Consent receipt">{e.consent ? <span><Badge tone={e.consent.signature_valid ? "ok" : "bad"}>signature {e.consent.signature_valid ? "valid" : "INVALID"}</Badge> <span className="mono text-xs text-muted">{String(e.consent.receipt?.receipt_id ?? "")} · {e.consent.key_id}</span></span> : "none"}</KV>
              <KV label="Assurance">{e.consent?.receipt?.assurance ? String((e.consent.receipt.assurance as Record<string, unknown>).level) : "—"}</KV>
            </CardBody>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="OAuth grant metadata" description="Technical permission only — metadata, never the token" />
          <CardBody className="py-2">
            {grant ? (
              <>
                <KV label="Token id" mono>{String(grant.jti)}</KV>
                <KV label="Scope" mono>{String(grant.scope)}</KV>
                <KV label="Audience" mono>{String(grant.aud)}</KV>
                <KV label="Issued / expires">{fmtDateTime(String(grant.issued_at))} → {fmtDateTime(String(grant.expires_at))}</KV>
                <KV label="Revoked">{grant.revoked_at ? fmtDateTime(String(grant.revoked_at)) : "no"}</KV>
                <KV label="DPoP key binding"><Hash value={String(grant.cnf_jkt)} /></KV>
                <KV label="Bound mandate" mono>{String(grant.mandate_id)} v{String(grant.mandate_version)}</KV>
              </>
            ) : <Empty>No grant recorded for this operation.</Empty>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Requested operation" />
          <CardBody className="py-2">
            {op ? (
              <>
                <KV label="Action" mono>{String(op.action)}</KV>
                <KV label="Amount" mono>{formatMoney(op.amount_minor as number, op.currency as string)} ({String(op.amount_minor)} minor)</KV>
                <KV label="Account" mono>{String(op.account_id)}</KV>
                <KV label="Counterparty" mono>{String(op.counterparty_kind)} · {String(op.counterparty_id)}</KV>
                <KV label="Purpose" mono>{String(op.purpose)}</KV>
                <KV label="Operation hash"><Hash value={e.operation?.op_hash} full /></KV>
              </>
            ) : <Empty>No operation recorded.</Empty>}
            <KV label="Execution">{e.execution?.status ? <StatusBadge kind="tx" status={e.execution.status} /> : "—"} <span className="text-xs text-muted">{e.execution?.postings?.length ?? 0} ledger postings · {e.execution?.balanced ? "balanced" : ""}</span></KV>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Policy decision" description={`policy ${e.policy?.version ?? "—"} · replay ${e.policy?.replay_matches === undefined ? "n/a" : e.policy.replay_matches ? "matches recorded decision" : "DIFFERS"}`} actions={<ReasonCodes codes={e.policy?.reason_codes} />} />
          <TraceChecklist trace={e.policy?.trace ?? []} />
        </Card>
        <div className="space-y-4">
          <RiskPanel risk={e.risk} />
          <Card>
            <CardHeader title={`Human approvals (${e.approvals?.length ?? 0})`} />
            {e.approvals?.length ? <JsonView data={e.approvals} /> : <Empty>No human approval was required or obtained.</Empty>}
          </Card>
          <Card>
            <CardHeader title={`Subsequent events (${e.subsequent_events?.length ?? 0})`} description="Revocations, suspensions and other events after the operation" />
            {e.subsequent_events?.length ? (
              <ul className="divide-y divide-border">{e.subsequent_events.map((s) => <li key={s.event_id} className="px-4 py-2 text-[13px]"><Badge className="mono">{s.event_type}</Badge> <span className="text-xs text-muted">{fmtDateTime(s.timestamp)} · {s.actor_id}</span></li>)}</ul>
            ) : <Empty>None recorded.</Empty>}
          </Card>
        </div>
      </div>

      {e.verification && (
        <Notice tone={e.verification.ok ? "ok" : "bad"} title={`Evidence package verification: ${e.verification.ok ? "OK" : "PROBLEMS FOUND"}`}>
          {e.verification.events_verified} of {e.verification.events_in_package} events verified (hash chain, signatures). {e.verification.assumptions?.[0]}
        </Notice>
      )}

      {e.responsibility && <Responsibility r={e.responsibility} />}
      {e.limitations && <Notice tone="info" title="Limitations of this evidence"><ul className="list-disc pl-4">{e.limitations.map((l) => <li key={l}>{l}</li>)}</ul></Notice>}
    </div>
  );
}

const LEVEL_TONE: Record<string, "info" | "neutral" | "warn" | "bad"> = { factual: "info", contractual: "neutral", potential_legal: "warn", adjudicated: "bad" };

function Responsibility({ r }: { r: NonNullable<EvidencePackage["responsibility"]> }) {
  return (
    <div className="space-y-4" data-testid="responsibility">
      <Card>
        <CardHeader title="Responsibility attribution" description="Four distinct questions. Only the first can be answered from technical evidence." />
        <div className="grid gap-px border-b border-border bg-border md:grid-cols-4">
          {r.levels.map((l) => (
            <div key={l.id} className="bg-surface p-3">
              <Badge tone={LEVEL_TONE[l.id] ?? "neutral"}>{l.name}</Badge>
              <p className="mt-1 text-xs text-muted">{l.description}</p>
              <p className="mt-1 text-[11px] font-medium">{l.id === "factual" ? "Shown below from signed evidence." : l.id === "adjudicated" ? "Never determined by this application." : "Not determined: needs external input."}</p>
            </div>
          ))}
        </div>
        <Table>
          <THead><TR><TH>Step</TH><TH>Party</TH><TH>Evidence</TH><TH>System control</TH><TH>Level</TH></TR></THead>
          <TBody>
            {r.attribution.map((a) => (
              <TR key={a.step}><TD><div className="font-medium">{a.question}</div></TD><TD>{a.party}</TD><TD className="text-xs text-muted">{a.evidence}</TD><TD className="text-xs">{a.system_control}</TD><TD><Badge tone={LEVEL_TONE[a.level] ?? "neutral"}>{a.level}</Badge></TD></TR>
            ))}
          </TBody>
        </Table>
        <div className="border-t border-border p-3 text-xs font-medium text-muted">{r.disclaimer}</div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="What can be established technically" />
          <ul className="list-disc space-y-1.5 p-4 pl-8 text-[13px]">{r.can_establish.map((c) => <li key={c}>{c}</li>)}</ul>
        </Card>
        <Card>
          <CardHeader title="What cannot be established technically" />
          <ul className="list-disc space-y-1.5 p-4 pl-8 text-[13px]">{r.cannot_establish.map((c) => <li key={c}>{c}</li>)}</ul>
        </Card>
      </div>
    </div>
  );
}

function MatrixExplorer() {
  const q = useQ(["resp-matrix"], api.responsibilityMatrix);
  return (
    <section className="mt-8">
      <h2 className="mb-2 text-sm font-semibold">Interactive responsibility matrix & hypothetical fault categories</h2>
      <Async q={q} what="responsibility matrix">{(m) => <Explorer m={m} />}</Async>
    </section>
  );
}

function Explorer({ m }: { m: ResponsibilityMatrixDef }) {
  const [assign, setAssign] = useState<Record<string, string>>(() => Object.fromEntries(m.steps.map((s) => [s.id, s.default_role])));
  const [fault, setFault] = useState(m.faults[0]?.id ?? "");
  const f = m.faults.find((x) => x.id === fault);
  const role = (id: string) => m.roles.find((r) => r.id === id);
  return (
    <Tabs defaultValue="matrix">
      <TabsList>
        <TabsTrigger value="matrix">Responsibility matrix</TabsTrigger>
        <TabsTrigger value="faults">Hypothetical fault categories</TabsTrigger>
      </TabsList>
      <TabsContent value="matrix" className="pt-3">
        <Card>
          <CardHeader title="Who performed or controlled each step?" description="Click a cell to reassign a step to a different role (hypothetical what-if; nothing is saved)." />
          <Table>
            <THead><TR><TH>Step</TH>{m.roles.map((r) => <TH key={r.id} title={r.description}>{r.name}</TH>)}</TR></THead>
            <TBody>
              {m.steps.map((s) => (
                <TR key={s.id}>
                  <TD className="font-medium">{s.question}</TD>
                  {m.roles.map((r) => {
                    const on = assign[s.id] === r.id;
                    return (
                      <TD key={r.id} className="text-center">
                        <button aria-label={`${s.question}: ${r.name}`} onClick={() => setAssign({ ...assign, [s.id]: r.id })} className={`h-5 w-5 cursor-pointer rounded-full border ${on ? "border-accent bg-accent" : "border-border hover:bg-surface2"}`} />
                      </TD>
                    );
                  })}
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="border-t border-border p-3 text-xs text-muted">{m.disclaimer} Selected roles say who <em>did or controlled</em> a step — not who must bear loss. {role(assign["executed"])?.name && <>Executed by: {role(assign["executed"])?.name}.</>}</div>
        </Card>
      </TabsContent>
      <TabsContent value="faults" className="pt-3">
        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <div className="space-y-1.5">
            {m.faults.map((x) => (
              <button key={x.id} onClick={() => setFault(x.id)} className={`w-full cursor-pointer rounded-md border px-3 py-2 text-left text-[13px] ${fault === x.id ? "border-accent bg-accent/5" : "border-border bg-surface hover:bg-surface2"}`}>{x.title}</button>
            ))}
          </div>
          {f && (
            <Card>
              <CardHeader title={f.title} description="Hypothetical category — illustrates how the four levels separate." />
              <CardBody className="space-y-3 text-[13px]">
                <Level tone="info" name="Factual" text={f.factual} />
                <Level tone="neutral" name="Contractual" text={f.contractual} />
                <Level tone="warn" name="Potential legal liability" text={f.potential_legal} />
                <Level tone="bad" name="Final adjudicated liability" text="Not determined by this system. Decided only by a court, tribunal or other competent body." />
                <div><div className="mb-1 text-xs font-medium text-muted">Evidence to gather</div><div className="flex flex-wrap gap-1">{f.evidence.map((x) => <Badge key={x}>{humanize(x)}</Badge>)}</div></div>
              </CardBody>
            </Card>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}

function Level({ tone, name, text }: { tone: "info" | "neutral" | "warn" | "bad"; name: string; text: string }) {
  return <div><Badge tone={tone}>{name}</Badge><p className="mt-1">{text}</p></div>;
}
