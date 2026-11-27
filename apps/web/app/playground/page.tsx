"use client";

import { useMutation } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DecisionPill, JsonView, Notice, PageHeader, ReasonCodes, StatusBadge } from "@/components/common";
import { useQ } from "@/components/providers";
import { RiskPanel, TraceChecklist } from "@/components/trace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatMoney, minorToMajorString, parseMajorToMinor } from "@/lib/money";
import { ACTION_BY_ID, ACTIONS, TOKEN_PROFILES } from "@/lib/taxonomy";
import type { EvaluateRequest, EvaluateResult, Mandate, TokenProfile } from "@/lib/types";

interface Form {
  mandateKey: string;
  agent_id: string;
  action: string;
  account_id: string;
  counterparty: string;
  amount: string;
  currency: string;
  purpose: string;
  token_profile: TokenProfile;
}

type CounterpartyKind = "beneficiary" | "merchant" | "to_account" | "none";
function counterpartyKind(action: string): CounterpartyKind {
  if (["payments.initiate", "payments.pay_invoice", "transfers.external"].includes(action)) return "beneficiary";
  if (action === "purchases.goods") return "merchant";
  if (action === "transfers.execute") return "to_account";
  return "none";
}

const PRESETS: { id: string; label: string; hint: string }[] = [
  { id: "token_ok_mandate_bad", label: "Valid token, invalid mandate", hint: "Central KYM point: OAuth passes, the mandate does not authorize this payee." },
  { id: "balance_read", label: "Balance read", hint: "Read-only action within the mandate" },
  { id: "valid_payment", label: "Valid payment", hint: "Permitted beneficiary, within limits" },
  { id: "wrong_beneficiary", label: "Wrong beneficiary", hint: "Payee not listed in the mandate" },
  { id: "over_limit", label: "Over limit", hint: "Above the per-transaction maximum" },
  { id: "expired", label: "Expired token", hint: "Technically defective credential" },
  { id: "wrong_audience", label: "Wrong audience", hint: "Token minted for another API" },
  { id: "missing_scope", label: "Missing scope", hint: "Token lacks the required scope" },
  { id: "no_dpop", label: "No DPoP proof", hint: "Sender-constraint proof missing" },
  { id: "revoked", label: "Revoked token", hint: "Token revoked at the authorization server" },
  { id: "wrong_actor", label: "Wrong actor", hint: "Token not bound to this client/agent" },
];

export default function PlaygroundPage() {
  const mandates = useQ(["mandates"], () => api.mandates());
  const accounts = useQ(["accounts"], api.accounts);
  const payees = useQ(["payees"], api.payees);
  const agents = useQ(["agents"], api.agents);

  const [form, setForm] = useState<Form | null>(null);
  const [content, setContent] = useState<Mandate | null>(null);
  const [result, setResult] = useState<{ req: EvaluateRequest; res: EvaluateResult } | null>(null);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [initial, setInitial] = useState<string | null>(null);

  useEffect(() => setInitial(new URLSearchParams(window.location.search).get("preset")), []);

  const run = useMutation({
    mutationFn: (req: EvaluateRequest) => api.evaluate(req),
    onSuccess: (res, req) => setResult({ req, res }),
  });

  const toRequest = useCallback((f: Form): EvaluateRequest | null => {
    const [mid, ver] = f.mandateKey.split(":");
    const kind = counterpartyKind(f.action);
    const money = ACTION_BY_ID[f.action]?.moneyMoving;
    const minor = money ? parseMajorToMinor(f.amount || "0", f.currency) : null;
    if (money && minor === null) return null;
    return {
      agent_id: f.agent_id, mandate_id: mid, version: Number(ver), action: f.action, account_id: f.account_id,
      beneficiary_id: kind === "beneficiary" ? f.counterparty : undefined,
      merchant_id: kind === "merchant" ? f.counterparty : undefined,
      to_account_id: kind === "to_account" ? f.counterparty : undefined,
      amount_minor: minor, currency: money ? f.currency : undefined, purpose: f.purpose, token_profile: f.token_profile,
    };
  }, []);

  const mandateKey = form?.mandateKey;
  useEffect(() => {
    if (!mandateKey) return;
    const [mid, ver] = mandateKey.split(":");
    let live = true;
    api.mandate(mid, Number(ver)).then((m) => live && setContent(m.content)).catch(() => live && setContent(null));
    return () => { live = false; };
  }, [mandateKey]);

  useEffect(() => {
    if (form || !mandates.data) return;
    const m = mandates.data.find((x) => x.status === "ACTIVE") ?? mandates.data[0];
    if (!m) return;
    setForm({ mandateKey: `${m.mandate_id}:${m.version}`, agent_id: m.agent_id, action: "balances.read", account_id: "", counterparty: "", amount: "", currency: m.currency, purpose: m.purpose, token_profile: "valid" });
  }, [mandates.data, form]);

  const payPerm = useMemo(() => content?.permissions.find((p) => ACTION_BY_ID[p.action]?.moneyMoving && p.constraints.maximum_amount_minor), [content]);

  const applyPreset = useCallback((id: string) => {
    if (!form || !content) return;
    const readPerm = content.permissions.find((p) => !ACTION_BY_ID[p.action]?.moneyMoving) ?? content.permissions[0];
    const pay = payPerm ?? content.permissions[0];
    const max = pay.constraints.maximum_amount_minor ?? 10000;
    const approvalAbove = content.obligations.human_approval_above_minor;
    const safe = Math.max(1, Math.min(Math.floor(max / 2), approvalAbove ?? max));
    const allowed = [...pay.constraints.allowed_beneficiaries, ...pay.constraints.allowed_merchants, ...pay.constraints.allowed_destination_accounts];
    const outsider = (payees.data ?? []).find((p) => p.kind === "beneficiary" && !allowed.includes(p.id) && p.country === "CA" && !/watchlist/.test(p.id)) ?? (payees.data ?? []).find((p) => !allowed.includes(p.id));
    const base: Form = {
      ...form, currency: content.currency, purpose: content.purpose, token_profile: "valid", action: pay.action, account_id: pay.resources[0],
      counterparty: allowed[0] ?? "", amount: minorToMajorString(safe, content.currency),
    };
    let f: Form = base;
    switch (id) {
      case "balance_read":
        f = { ...base, action: readPerm.action, account_id: readPerm.resources[0], counterparty: "", amount: "" };
        break;
      case "valid_payment":
        break;
      case "wrong_beneficiary":
      case "token_ok_mandate_bad":
        f = { ...base, counterparty: outsider?.id ?? "beneficiary_new_supplier" };
        break;
      case "over_limit":
        f = { ...base, amount: minorToMajorString(max + 10000, content.currency) };
        break;
      default:
        f = { ...base, token_profile: id as TokenProfile };
    }
    setForm(f);
    setActivePreset(id);
    const req = toRequest(f);
    if (req) run.mutate(req);
  }, [form, content, payPerm, payees.data, toRequest, run]);

  useEffect(() => {
    if (initial && content && form && payees.data && !result && !run.isPending && !activePreset) applyPreset(initial);
  }, [initial, content, form, payees.data, result, run.isPending, activePreset, applyPreset]);

  const set = (k: keyof Form, v: string) => setForm((f) => (f ? { ...f, [k]: v } : f));
  const kind = form ? counterpartyKind(form.action) : "none";
  const money = form ? ACTION_BY_ID[form.action]?.moneyMoving : false;
  const cpOptions =
    kind === "to_account" ? (accounts.data ?? []).map((a) => ({ id: a.accountId, name: `${a.nickname} (${a.accountId})` }))
    : (payees.data ?? []).filter((p) => (kind === "merchant" ? p.kind === "merchant" : p.kind === "beneficiary")).map((p) => ({ id: p.id, name: p.name }));
  const req = form ? toRequest(form) : null;
  const tokenChecksPassed = result?.res.trace.filter((t) => t.id.startsWith("token"));

  return (
    <>
      <PageHeader title="Authorization playground" description="Dry-run a request through the same gateway, policy decision point and risk engine the bank API uses — with a real signed token, optionally defective on purpose." />
      {mandates.data && mandates.data.length === 0 && (
        <Notice tone="warn" className="mb-4" title="No mandates exist yet">Run a scenario (admin) or create and approve a mandate in the Mandate studio, then come back.</Notice>
      )}
      <Card className="mb-4 border-accent/40">
        <CardHeader title="Presets" description="One click fills the form from the selected mandate and runs it." />
        <CardBody className="space-y-2">
          <button
            data-testid="preset-token_ok_mandate_bad"
            onClick={() => applyPreset("token_ok_mandate_bad")}
            disabled={!content}
            className="flex w-full cursor-pointer items-center gap-3 rounded-md border-2 border-accent/50 bg-accent/5 p-3 text-left hover:bg-accent/10 disabled:opacity-50"
          >
            <Play size={16} className="text-accent" />
            <span>
              <span className="block text-sm font-semibold">Valid token, invalid mandate <Badge tone="accent">central KYM point</Badge></span>
              <span className="text-xs text-muted">{PRESETS[0].hint}</span>
            </span>
          </button>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.slice(1).map((p) => (
              <Button key={p.id} size="sm" variant={activePreset === p.id ? "default" : "outline"} title={p.hint} disabled={!content} data-testid={`preset-${p.id}`} onClick={() => applyPreset(p.id)}>{p.label}</Button>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[400px_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Request" />
          <CardBody className="space-y-3">
            {!form ? <div className="text-sm text-muted">Waiting for mandates…</div> : (
              <>
                <div>
                  <Label>Mandate</Label>
                  <Select value={form.mandateKey} onChange={(e) => { const m = mandates.data?.find((x) => `${x.mandate_id}:${x.version}` === e.target.value); setForm({ ...form, mandateKey: e.target.value, agent_id: m?.agent_id ?? form.agent_id, currency: m?.currency ?? form.currency, purpose: m?.purpose ?? form.purpose }); }}>
                    {(mandates.data ?? []).map((m) => <option key={`${m.mandate_id}:${m.version}`} value={`${m.mandate_id}:${m.version}`}>{m.mandate_id} v{m.version} · {m.status} · {m.agent_id}</option>)}
                  </Select>
                  <div className="mt-1 flex gap-1">{content && <StatusBadge kind="mandate" status={mandates.data?.find((x) => `${x.mandate_id}:${x.version}` === form.mandateKey)?.status} />}</div>
                </div>
                <div>
                  <Label>Agent</Label>
                  <Select value={form.agent_id} onChange={(e) => set("agent_id", e.target.value)}>
                    {(agents.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.display_name} ({a.status})</option>)}
                  </Select>
                </div>
                <div>
                  <Label>Action</Label>
                  <Select value={form.action} onChange={(e) => set("action", e.target.value)} data-testid="action-select">
                    {ACTIONS.map((a) => <option key={a.id} value={a.id}>{a.label} · {a.id}</option>)}
                  </Select>
                </div>
                <div>
                  <Label>Account</Label>
                  <Select value={form.account_id} onChange={(e) => set("account_id", e.target.value)}>
                    <option value="">Select…</option>
                    {(accounts.data ?? []).map((a) => <option key={a.accountId} value={a.accountId}>{a.nickname} ({a.accountId}) · {a.currency}</option>)}
                  </Select>
                </div>
                {kind !== "none" && (
                  <div>
                    <Label>{kind === "merchant" ? "Merchant" : kind === "to_account" ? "Destination account" : "Beneficiary"}</Label>
                    <Select value={form.counterparty} onChange={(e) => set("counterparty", e.target.value)}>
                      <option value="">Select…</option>
                      {cpOptions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </Select>
                  </div>
                )}
                {money && (
                  <div className="grid grid-cols-[1fr_90px] gap-2">
                    <div>
                      <Label>Amount (major units)</Label>
                      <Input inputMode="decimal" value={form.amount} onChange={(e) => set("amount", e.target.value)} data-testid="amount" />
                      <div className="mt-0.5 text-[11px] text-muted">{req?.amount_minor != null ? `${req.amount_minor} minor units · ${formatMoney(req.amount_minor, form.currency)}` : "invalid amount"}</div>
                    </div>
                    <div>
                      <Label>Currency</Label>
                      <Input value={form.currency} onChange={(e) => set("currency", e.target.value.toUpperCase().slice(0, 3))} />
                    </div>
                  </div>
                )}
                <div>
                  <Label>Purpose</Label>
                  <Input value={form.purpose} onChange={(e) => set("purpose", e.target.value)} />
                </div>
                <div>
                  <Label>Token profile</Label>
                  <Select value={form.token_profile} onChange={(e) => set("token_profile", e.target.value)} data-testid="token-profile">
                    {TOKEN_PROFILES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                  </Select>
                </div>
                <Button variant="accent" className="w-full" disabled={!req || !form.account_id || run.isPending} onClick={() => { setActivePreset(null); if (req) run.mutate(req); }} data-testid="run-evaluate">
                  <Play size={14} /> Evaluate
                </Button>
              </>
            )}
          </CardBody>
        </Card>

        <div className="min-w-0 space-y-4">
          {run.error && <Notice tone="bad" title="Evaluation failed">{run.error.message}</Notice>}
          {!result && !run.error && <Card><div className="p-10 text-center text-[13px] text-muted">Pick a preset or fill the form, then evaluate.</div></Card>}
          {result && (
            <>
              <Card data-testid="result">
                <CardBody className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <DecisionPill decision={result.res.decision} />
                    <span className="text-xs text-muted">token profile <Badge className="mono">{result.req.token_profile}</Badge></span>
                  </div>
                  <div><div className="mb-1 text-xs font-medium text-muted">Reason codes</div><ReasonCodes codes={result.res.reason_codes} /></div>
                  {result.res.decision === "DENY" && tokenChecksPassed && tokenChecksPassed.length > 0 && tokenChecksPassed.every((t) => t.outcome === "PASS") && (
                    <Notice tone="info" title="Token checks passed — the denial comes from the mandate">A valid OAuth token is technical permission, not delegated authority.</Notice>
                  )}
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="Decision trace" description="Every check the policy decision point performed, in order." />
                <TraceChecklist trace={result.res.trace} />
              </Card>
              <RiskPanel risk={result.res.risk} />
              <details className="text-xs"><summary className="cursor-pointer text-muted">Raw request / response</summary><JsonView data={result} maxH="max-h-80" className="mt-2" /></details>
            </>
          )}
        </div>
      </div>
    </>
  );
}
