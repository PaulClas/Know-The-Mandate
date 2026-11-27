"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Ban, Plus, Search, ShieldOff } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Async, Empty, Hash, JsonView, KV, Notice, PageHeader, Spinner, StatusBadge } from "@/components/common";
import { useQ, useSession } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, Select } from "@/components/ui/input";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { ACTIONS, actionLabel } from "@/lib/taxonomy";
import type { Agent } from "@/lib/types";
import { fmtDateTime, humanize } from "@/lib/utils";

export default function AgentsPage() {
  const { user } = useSession();
  const isAdmin = user?.role === "admin";
  const q = useQ(["agents"], api.agents);
  const [sel, setSel] = useState<string | null>(null);
  const [reg, setReg] = useState(false);
  const [filter, setFilter] = useState("");

  return (
    <>
      <PageHeader
        title="Agent registry"
        description="Know Your Agent: what each agent declares about itself is kept strictly apart from what the bank has independently verified."
        actions={isAdmin ? <Button variant="accent" onClick={() => setReg(true)}><Plus size={14} /> Register agent</Button> : <Badge>Registration: bank operator only</Badge>}
      />
      <Card>
        <div className="flex items-center gap-2 border-b border-border p-3">
          <Search size={14} className="text-muted" />
          <Input className="max-w-xs" placeholder="Filter agents…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <Async q={q} what="agents">
          {(agents) => {
            const rows = agents.filter((a) => (a.display_name + a.id + a.declared.operating_organization).toLowerCase().includes(filter.toLowerCase()));
            return (
              <Table>
                <THead>
                  <TR><TH>Agent</TH><TH>Operator</TH><TH>Category</TH><TH>Status</TH><TH>Autonomy</TH><TH>Trust</TH><TH>Key thumbprint</TH></TR>
                </THead>
                <TBody>
                  {rows.map((a) => (
                    <TR key={a.id} onClick={() => setSel(a.id)} data-testid={`agent-row-${a.id}`}>
                      <TD>
                        <div className="font-medium">{a.display_name}</div>
                        <div className="mono text-[11px] text-muted">{a.id}</div>
                      </TD>
                      <TD>{a.declared.operating_organization}</TD>
                      <TD>{humanize(a.declared.category)}</TD>
                      <TD><StatusBadge kind="agent" status={a.status} /></TD>
                      <TD>{humanize(a.declared.declared_autonomy_level)}</TD>
                      <TD><span className="tabular-nums">{a.trust?.score ?? "—"}</span></TD>
                      <TD><Hash value={a.verified?.key_thumbprint ?? a.public_key?.thumbprint} head={8} tail={4} /></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            );
          }}
        </Async>
      </Card>
      <AgentDrawer id={sel} onClose={() => setSel(null)} isAdmin={isAdmin} />
      <RegisterDialog open={reg} onClose={() => setReg(false)} />
    </>
  );
}

function AgentDrawer({ id, onClose, isAdmin }: { id: string | null; onClose: () => void; isAdmin: boolean }) {
  const qc = useQueryClient();
  const q = useQ(["agent", id], () => api.agent(id!), { enabled: !!id });
  const act = useMutation({
    mutationFn: (a: "verify" | "suspend" | "restrict" | "revoke") => api.agentAction(id!, a, "operator action via KYM console"),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <Dialog open={!!id} onClose={onClose} side title={q.data?.display_name ?? "Agent"}>
      {!q.data && q.isLoading && <Spinner />}
      {q.error && <Notice tone="bad">{q.error.message}</Notice>}
      {q.data && <AgentDetail a={q.data} isAdmin={isAdmin} act={(x) => act.mutate(x)} busy={act.isPending} error={act.error?.message} />}
    </Dialog>
  );
}

function AgentDetail({ a, isAdmin, act, busy, error }: { a: Agent; isAdmin: boolean; act: (x: "verify" | "suspend" | "restrict" | "revoke") => void; busy: boolean; error?: string }) {
  const d = a.declared;
  const mandates = a.mandates ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge kind="agent" status={a.status} />
        <span className="mono text-xs text-muted">{a.id}</span>
        {a.cnl_ref && <Badge className="mono">{a.cnl_ref}</Badge>}
      </div>
      {isAdmin && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="success" disabled={busy || a.status === "VERIFIED" || a.status === "REVOKED"} onClick={() => act("verify")}><BadgeCheck size={13} /> Verify</Button>
          <Button size="sm" variant="outline" disabled={busy || a.status === "RESTRICTED" || a.status === "REVOKED"} onClick={() => act("restrict")}>Restrict</Button>
          <Button size="sm" variant="outline" disabled={busy || a.status === "SUSPENDED" || a.status === "REVOKED"} onClick={() => act("suspend")}><Ban size={13} /> Suspend</Button>
          <Button size="sm" variant="danger" disabled={busy || a.status === "REVOKED"} onClick={() => act("revoke")}><ShieldOff size={13} /> Revoke</Button>
        </div>
      )}
      {error && <Notice tone="bad">{error}</Notice>}

      <Card>
        <CardHeader title="Agent-declared" description="Self-asserted by the operator at registration. Not verified by the bank." />
        <CardBody className="py-2">
          <KV label="Display name">{d.display_name}</KV>
          <KV label="Operating organization">{d.operating_organization}</KV>
          <KV label="Operator id" mono>{d.operator_id}</KV>
          <KV label="Responsible party">{d.responsible_party}</KV>
          <KV label="Developer">{d.developer}</KV>
          <KV label="Environment">{d.deployment_environment}</KV>
          <KV label="Model">{d.model_provider} / <span className="mono">{d.model_id}</span></KV>
          <KV label="Software version" mono>{d.software_version}</KV>
          <KV label="Build digest"><Hash value={d.build_digest} /></KV>
          <KV label="Autonomy level">{humanize(d.declared_autonomy_level)}</KV>
          <KV label="Supported tools">
            <span className="flex flex-wrap gap-1">{d.supported_tools.map((t) => <Badge key={t} className="mono">{t}</Badge>)}</span>
          </KV>
          <KV label="Requested capabilities">
            <span className="flex flex-wrap gap-1">{d.requested_capabilities.map((t) => <Badge key={t} tone="info" title={actionLabel(t)} className="mono">{t}</Badge>)}</span>
          </KV>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Bank-verified facts" description="Established by the bank's KYA service. Assurance is simulated in this demo." />
        <CardBody className="py-2">
          {a.verified ? (
            <>
              <KV label="Verified at">{fmtDateTime(a.verified.verified_at)}</KV>
              <KV label="Verified by" mono>{a.verified.verified_by}</KV>
              <KV label="Assurance"><Badge tone="warn">{a.verified.assurance}</Badge></KV>
              <KV label="Key thumbprint"><Hash value={a.verified.key_thumbprint} head={16} tail={8} /></KV>
              <KV label="Verified build digest"><Hash value={a.verified.build_digest} /></KV>
              <KV label="Checks">
                <ul className="space-y-0.5">
                  {a.verified.checks.map((c) => (
                    <li key={c.check} className="flex items-center gap-1.5">
                      <span className={c.ok ? "text-ok" : "text-bad"}>{c.ok ? "✓" : "✗"}</span>
                      <span className="mono text-xs">{c.check}</span>
                    </li>
                  ))}
                </ul>
              </KV>
            </>
          ) : (
            <p className="py-2 text-muted">Not verified by the bank. A pending or unverified agent cannot be issued tokens.</p>
          )}
          <KV label="Public key thumbprint"><Hash value={a.public_key?.thumbprint} head={16} tail={8} /></KV>
          <KV label="Attestation">
            {a.attestation ? (
              <div className="space-y-1">
                <Badge tone="warn">{a.attestation.assurance}</Badge> <span className="text-xs text-muted">issuer {a.attestation.statement.issuer} · key {a.attestation.key_id}</span>
                <JsonView data={a.attestation.statement} maxH="max-h-40" />
              </div>
            ) : "None"}
          </KV>
          <KV label="Security posture">
            <span className="flex flex-wrap gap-1">
              {Object.entries(a.security_posture ?? {}).map(([k, v]) => <Badge key={k} tone={v ? "ok" : "bad"}>{humanize(k)}</Badge>)}
            </span>
          </KV>
          <KV label="Registered">{fmtDateTime(a.registered_at)}</KV>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Trust profile" description="Informational only — an input to risk signals; can never override a denial." actions={<span className="text-xl font-semibold tabular-nums">{a.trust.score}</span>} />
        <CardBody>
          <div className="space-y-1.5">
            {Object.entries(a.trust.components).map(([k, v]) => (
              <div key={k} className="grid grid-cols-[170px_1fr_40px] items-center gap-2 text-xs">
                <span className="text-muted">{humanize(k)}</span>
                <div className="h-1.5 overflow-hidden rounded bg-surface2"><div className={k === "incident_penalty" ? "h-full bg-bad" : "h-full bg-accent"} style={{ width: `${Math.min(100, Number(v))}%` }} /></div>
                <span className="text-right tabular-nums">{v}</span>
              </div>
            ))}
          </div>
          <p className="mono mt-3 rounded bg-surface2 p-2 text-[11px]">{a.trust.formula}</p>
          <p className="mt-1 text-xs text-muted">Weights: {Object.entries(a.trust.weights).map(([k, v]) => `${k}=${v}`).join(" · ")}</p>
          <p className="mt-1 text-xs text-muted">{a.trust.note}</p>
          <p className="mt-2 text-xs">Observed: {a.stats.payments_executed} payments executed · {a.stats.payments_denied} denied · {a.stats.mandates_executed} mandate runs</p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title={`Incidents (${a.incidents.length})`} />
        {a.incidents.length === 0 ? <Empty>No recorded incidents.</Empty> : <JsonView data={a.incidents} />}
      </Card>

      <Card>
        <CardHeader title={`Mandate relationships (${mandates.length})`} />
        {mandates.length === 0 ? (
          <Empty>No mandates visible for this agent.</Empty>
        ) : (
          <ul className="divide-y divide-border">
            {mandates.map((m) => (
              <li key={`${m.mandate_id}-${m.version}`} className="flex items-center gap-2 px-4 py-2 text-[13px]">
                <span className="mono">{m.mandate_id} v{m.version}</span>
                <StatusBadge kind="mandate" status={m.status} />
                <span className="flex-1 truncate text-muted">{m.purpose} · {m.principal_id}</span>
                <Link href="/portal" className="text-xs text-accent hover:underline">portal</Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

const BLANK = {
  display_name: "", category: "personal_finance", operating_organization: "", operator_id: "", responsible_party: "", developer: "",
  deployment_environment: "cloud-sandbox", model_provider: "SyntheticLM Labs (fictional)", model_id: "synthetic-lm-1", software_version: "0.1.0",
  build_digest: "sha256:" + "ab".repeat(32), declared_autonomy_level: "supervised", tools: "get_balance, propose_payment",
};

function RegisterDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState(BLANK);
  const [caps, setCaps] = useState<string[]>(["balances.read"]);
  const m = useMutation({
    mutationFn: () => {
      const { tools, ...rest } = f;
      return api.registerAgent({
        declared: { ...rest, supported_tools: tools.split(",").map((s) => s.trim()).filter(Boolean), requested_capabilities: caps },
        generate_demo_keys: true,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      setF(BLANK);
      onClose();
    },
  });
  const set = (k: keyof typeof BLANK) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const field = (k: keyof typeof BLANK, label: string) => (
    <div>
      <Label>{label}</Label>
      <Input value={f[k]} onChange={set(k)} />
    </div>
  );
  return (
    <Dialog open={open} onClose={onClose} title="Register agent (declared facts)" wide>
      <Notice tone="info" className="mb-3">Everything entered here is an unverified claim. The bank verifies the attestation and key separately.</Notice>
      <div className="grid gap-3 md:grid-cols-2">
        {field("display_name", "Display name")}
        {field("operating_organization", "Operating organization")}
        {field("operator_id", "Operator id (e.g. organization_007)")}
        {field("responsible_party", "Responsible party")}
        {field("developer", "Developer")}
        {field("model_provider", "Model provider")}
        {field("model_id", "Model id")}
        {field("software_version", "Software version")}
        {field("build_digest", "Build digest (sha256:…)")}
        {field("tools", "Supported tools (comma separated)")}
        <div>
          <Label>Category</Label>
          <Select value={f.category} onChange={set("category")}>
            {["personal_finance", "bill_payment", "shopping", "savings", "treasury", "other"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
          </Select>
        </div>
        <div>
          <Label>Declared autonomy level</Label>
          <Select value={f.declared_autonomy_level} onChange={set("declared_autonomy_level")}>
            {["assistive", "supervised", "conditional", "high"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
          </Select>
        </div>
      </div>
      <div className="mt-3">
        <Label>Requested capabilities (action ids)</Label>
        <div className="flex flex-wrap gap-1.5">
          {ACTIONS.map((a) => {
            const on = caps.includes(a.id);
            return (
              <button key={a.id} type="button" onClick={() => setCaps(on ? caps.filter((c) => c !== a.id) : [...caps, a.id])}
                className={`mono cursor-pointer rounded border px-1.5 py-0.5 text-[11px] ${on ? "border-accent bg-accent/10 text-accent" : "border-border text-muted"}`}>
                {a.id}
              </button>
            );
          })}
        </div>
      </div>
      {m.error && <Notice tone="bad" className="mt-3">{m.error.message}</Notice>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button variant="accent" disabled={m.isPending || !f.display_name || !f.operator_id} onClick={() => m.mutate()}>Register</Button>
      </div>
    </Dialog>
  );
}
