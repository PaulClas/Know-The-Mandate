"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRightLeft, CheckCircle2, FileCheck2, Loader2, Sparkles, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Empty, Hash, JsonView, KV, Notice, PageHeader, StatusBadge } from "@/components/common";
import { useQ, useSession } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { formatMoney, parseMajorToMinor } from "@/lib/money";
import { DEFAULT_INSTRUCTION, EXAMPLE_CNL } from "@/lib/studio-defaults";
import { ACTIONS, actionLabel } from "@/lib/taxonomy";
import type { CompileResult, MandateView } from "@/lib/types";
import { fmtDateTime } from "@/lib/utils";

const PURPOSES = ["household_bill_management", "personal_finance_analysis", "personal_shopping", "savings_optimization", "business_treasury", "supplier_payments", "scenario_demo"];

// ---- CNL tweaking helpers: numeric controls rewrite the CNL text (string based, no float arithmetic)
const NUM = String.raw`\d+(?:\.\d+)?`;
function moneyRe(prefix: string, suffix = "") {
  return new RegExp(`(${prefix}\\s+)(?:(${NUM})(\\s+[A-Z]{3})|([A-Z]{3}\\s+)(${NUM}))${suffix}`, "g");
}
const TWEAKS = {
  max: { label: "Max per payment", re: () => moneyRe("WITH MAX_AMOUNT", String.raw`(?=\s+PER\s+TRANSACTION)`) },
  monthly: { label: "Monthly budget", re: () => moneyRe("LIMIT TOTAL_PAYMENTS TO", String.raw`(?=\s+PER\s+CALENDAR_MONTH)`) },
  approval: { label: "Human approval above", re: () => moneyRe("FOR PAYMENTS ABOVE") },
} as const;
type TweakKey = keyof typeof TWEAKS;

function readTweak(cnl: string, k: TweakKey): string | null {
  const m = TWEAKS[k].re().exec(cnl);
  return m ? (m[2] ?? m[5]) : null;
}
function writeTweak(cnl: string, k: TweakKey, v: string): string {
  return cnl.replace(TWEAKS[k].re(), (_m, p1, n1, c1, p4) => (n1 !== undefined ? `${p1}${v}${c1}` : `${p4}${v}`));
}
function readExpiry(cnl: string): string {
  return /EXPIRE AT (\d{4}-\d{2}-\d{2})T/.exec(cnl)?.[1] ?? "";
}
function writeExpiry(cnl: string, d: string): string {
  return cnl.replace(/(EXPIRE AT )\d{4}-\d{2}-\d{2}(T[\d:]+Z)/, `$1${d}$2`);
}
function currencyOf(cnl: string): string {
  return /\b(?:MAX_AMOUNT|TO|ABOVE)\s+(?:\d+(?:\.\d+)?\s+)?([A-Z]{3})\b(?!_)/.exec(cnl)?.[1] ?? "CAD";
}

export default function StudioPage() {
  const { user } = useSession();
  const customers = useQ(["customers"], api.customers);
  const agents = useQ(["agents"], api.agents);
  const accounts = useQ(["accounts"], api.accounts);
  const payees = useQ(["payees"], api.payees);

  const [principal, setPrincipal] = useState<string>("");
  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION);
  const [cnl, setCnl] = useState(EXAMPLE_CNL);
  const [lang, setLang] = useState<"en" | "fr">("en");
  const [result, setResult] = useState<CompileResult | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<CompileResult | null>(null);
  const [created, setCreated] = useState<MandateView | null>(null);
  const [twoOpen, setTwoOpen] = useState(false);
  const seq = useRef(0);

  // default principal: the signed-in customer, else the first listed customer (Alice for the bank operator)
  useEffect(() => {
    if (!customers.data?.length) return;
    const list = customers.data;
    if (principal && list.some((c) => c.id === principal)) return;
    const own = list.find((c) => c.id === user?.id);
    setPrincipal((own ?? list.find((c) => c.id === "customer_001") ?? list[0]).id);
  }, [customers.data, user?.id, principal]);

  // live, debounced compile of the CNL
  useEffect(() => {
    if (!principal) return;
    const my = ++seq.current;
    setCompiling(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.compile({ principal_id: principal, cnl });
        if (my !== seq.current) return;
        setResult(r);
        setCompileError(null);
      } catch (e) {
        if (my !== seq.current) return;
        setCompileError((e as Error).message);
      } finally {
        if (my === seq.current) setCompiling(false);
      }
    }, 450);
    return () => clearTimeout(t);
  }, [principal, cnl]);

  const analyze = useCallback(async () => {
    if (!principal) return;
    try {
      setAnalysis(await api.compile({ principal_id: principal, instruction }));
    } catch (e) {
      setCompileError((e as Error).message);
    }
  }, [principal, instruction]);
  useEffect(() => {
    if (principal) analyze();
    // analyze once per principal; further analyses are explicit
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [principal]);

  const qc = useQueryClient();
  const create = useMutation({
    mutationFn: () => api.createMandate({ principal_id: principal, cnl }),
    onSuccess: (m) => {
      setCreated(m);
      qc.invalidateQueries();
    },
  });

  const ccy = currencyOf(cnl);
  const principalAccounts = (accounts.data ?? []).filter((a) => a.owner_id === principal);

  return (
    <>
      <PageHeader
        title="Mandate studio"
        description="Turn an ambiguous instruction into an explicit, validated, machine-readable mandate. An LLM may suggest text; only the deterministic compiler, the bank's policy, and the customer's approval can make authority."
        actions={
          <Button variant="outline" onClick={() => setTwoOpen(true)} data-testid="two-phrasings">
            <ArrowRightLeft size={14} /> Two phrasings → same digest
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="1 · Original instruction" description="Free text, exactly as the customer might say it." />
            <CardBody className="space-y-2">
              <div>
                <Label>Principal (whose authority)</Label>
                <Select value={principal} onChange={(e) => setPrincipal(e.target.value)} data-testid="principal-select">
                  {(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name} · {c.id}</option>)}
                </Select>
              </div>
              <Textarea rows={4} value={instruction} onChange={(e) => setInstruction(e.target.value)} data-testid="instruction" />
              <Button size="sm" variant="outline" onClick={analyze}><Sparkles size={13} /> Detect ambiguities</Button>
            </CardBody>
          </Card>

          <Ambiguities analysis={analysis} />

          <ResolutionForm
            principal={principal}
            accounts={principalAccounts}
            agents={agents.data ?? []}
            payees={payees.data ?? []}
            instruction={instruction}
            onProposed={(text) => setCnl(text)}
          />
        </div>

        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              title="2 · KYM-CNL editor"
              description="Controlled natural language. Compiles deterministically; the same authority always yields the same digest."
              actions={
                <>
                  {compiling && <Loader2 size={14} className="animate-spin text-muted" />}
                  <Button size="sm" variant="ghost" onClick={() => setCnl(EXAMPLE_CNL)}>Reset example</Button>
                </>
              }
            />
            <CardBody className="space-y-3">
              <Textarea className="mono min-h-[210px] text-[12.5px]" spellCheck={false} value={cnl} onChange={(e) => setCnl(e.target.value)} data-testid="cnl-editor" />
              <Tweaks cnl={cnl} setCnl={setCnl} ccy={ccy} />
              {compileError && <Notice tone="bad" title="Compile request failed">{compileError}</Notice>}
              {result && !result.ok && result.errors.length > 0 && <ParseErrors result={result} cnl={cnl} />}
              <div className="flex flex-wrap items-center gap-2">
                <StatusPills r={result} />
                <div className="ml-auto flex items-center gap-2">
                  <Button variant="accent" data-testid="create-mandate" disabled={!result?.ok || !result.validation?.ok || create.isPending || !principal} onClick={() => create.mutate()}>
                    <FileCheck2 size={14} /> Create mandate
                  </Button>
                </div>
              </div>
              {create.error && <Notice tone="bad" title="Create failed">{create.error.message}</Notice>}
            </CardBody>
          </Card>

          {created && <Lifecycle id={created.mandate_id} version={created.version} initial={created} />}

          <Artifacts r={result} lang={lang} setLang={setLang} />
        </div>
      </div>
      <TwoPhrasings open={twoOpen} onClose={() => setTwoOpen(false)} principal={principal} />
    </>
  );
}

function StatusPills({ r }: { r: CompileResult | null }) {
  if (!r) return <Badge>compiling…</Badge>;
  const v = r.validation;
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="compile-status">
      <Badge tone={r.ok ? "ok" : "bad"}>{r.ok ? "Compiles" : "Does not compile"}</Badge>
      {v && <Badge tone={v.schema.ok ? "ok" : "bad"}>Schema</Badge>}
      {v && <Badge tone={v.semantic.ok ? "ok" : "bad"}>Semantic</Badge>}
      {v && <Badge tone={v.bank_policy.ok ? "ok" : "bad"}>Bank policy</Badge>}
      {v && <Badge tone={v.shacl.conforms ? "ok" : "bad"}>SHACL {v.shacl.conforms ? "conforms" : "violations"}</Badge>}
      {r.canonical_digest && <span className="text-xs text-muted">digest <Hash value={r.canonical_digest} head={14} tail={6} /></span>}
    </div>
  );
}

function Ambiguities({ analysis }: { analysis: CompileResult | null }) {
  const amb = analysis?.ambiguities ?? [];
  return (
    <Card>
      <CardHeader title={`Ambiguities${amb.length ? ` (${amb.length})` : ""}`} description="Words the compiler refuses to guess. Resolve each explicitly below." />
      {amb.length === 0 ? (
        <Empty>{analysis ? "No ambiguous phrases detected." : "Analyzing instruction…"}</Empty>
      ) : (
        <ul className="divide-y divide-border" data-testid="ambiguities">
          {amb.map((a) => (
            <li key={a.id} className="px-4 py-2 text-[13px]">
              <div className="flex items-center gap-2">
                <AlertTriangle size={13} className="text-warn" />
                <span className="font-medium">“{a.phrase}”</span>
                <Badge className="ml-auto">{a.kind}</Badge>
              </div>
              <div className="mt-0.5 text-muted">{a.question}</div>
              <div className="text-xs text-muted">Hint: {a.hint}</div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ResolutionForm({ principal, accounts, agents, payees, instruction, onProposed }: {
  principal: string;
  accounts: { accountId: string; nickname: string; cnl_ref: string; currency: string }[];
  agents: { id: string; display_name: string; cnl_ref: string | null; status: string }[];
  payees: { id: string; name: string; cnl_ref: string; kind: string }[];
  instruction: string;
  onProposed: (cnl: string) => void;
}) {
  const [agent, setAgent] = useState("");
  const [accts, setAccts] = useState<string[]>([]);
  const [reads, setReads] = useState<string[]>(["READ_BALANCE"]);
  const [verb, setVerb] = useState("PAY_INVOICE");
  const [bens, setBens] = useState<string[]>([]);
  const [maxAmt, setMaxAmt] = useState("");
  const [monthly, setMonthly] = useState("");
  const [approval, setApproval] = useState("");
  const [expiry, setExpiry] = useState("");
  const [purpose, setPurpose] = useState("");
  const [prohibit, setProhibit] = useState<string[]>(["EXTERNAL_TRANSFER", "DELEGATION"]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ccy = accounts.find((a) => accts.includes(a.cnl_ref))?.currency ?? "CAD";

  const toggle = (arr: string[], set: (v: string[]) => void, v: string) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const validMoney = (s: string) => s === "" || parseMajorToMinor(s, ccy) !== null;
  const complete = agent && accts.length && purpose && expiry && (!maxAmt || bens.length) && validMoney(maxAmt) && validMoney(monthly) && validMoney(approval);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const resolutions: Record<string, unknown> = {
        agent, purpose, expires_at: `${expiry}T00:00:00Z`, currency: ccy, accounts: accts, read_actions: reads, prohibit,
      };
      if (maxAmt && bens.length) resolutions.payment = { verb, accounts: accts, beneficiaries: bens, max_amount: maxAmt };
      if (monthly) resolutions.monthly_budget = monthly;
      if (approval !== "") resolutions.approval_above = approval;
      const r = await api.compile({ principal_id: principal, instruction, resolutions });
      if (r.proposed_cnl) onProposed(r.proposed_cnl);
      else setErr(r.errors.map((e) => e.message).join("; ") || "No CNL proposed");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="Resolve explicitly" description="Every field is a decision by the customer. Nothing is defaulted or invented; empty optional fields produce no authority." />
      <CardBody className="space-y-3">
        <div>
          <Label>Agent</Label>
          <Select value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="">Select agent…</option>
            {agents.filter((a) => a.cnl_ref).map((a) => <option key={a.id} value={a.cnl_ref!}>{a.display_name} ({a.status})</option>)}
          </Select>
        </div>
        <div>
          <Label>Accounts</Label>
          <div className="space-y-1">
            {accounts.length === 0 && <span className="text-xs text-muted">No accounts for this principal.</span>}
            {accounts.map((a) => (
              <label key={a.accountId} className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" checked={accts.includes(a.cnl_ref)} onChange={() => toggle(accts, setAccts, a.cnl_ref)} />
                {a.nickname} <span className="mono text-xs text-muted">{a.cnl_ref}</span>
              </label>
            ))}
          </div>
        </div>
        <div>
          <Label>Read actions</Label>
          <div className="flex flex-wrap gap-2">
            {ACTIONS.filter((a) => a.group === "Read" && a.id !== "data.transmit_external").map((a) => (
              <label key={a.id} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={reads.includes(a.cnl)} onChange={() => toggle(reads, setReads, a.cnl)} />{a.label}</label>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label>Payment action</Label>
            <Select value={verb} onChange={(e) => setVerb(e.target.value)}>
              {ACTIONS.filter((a) => ["payments.pay_invoice", "payments.initiate"].includes(a.id)).map((a) => <option key={a.id} value={a.cnl}>{a.label}</option>)}
            </Select>
          </div>
          <div>
            <Label>Max per payment ({ccy})</Label>
            <Input inputMode="decimal" placeholder="e.g. 250.00" value={maxAmt} onChange={(e) => setMaxAmt(e.target.value)} />
          </div>
        </div>
        <div>
          <Label>Beneficiaries (closed list)</Label>
          <div className="max-h-28 space-y-1 overflow-auto">
            {payees.filter((p) => p.kind === "beneficiary").map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={bens.includes(p.cnl_ref)} onChange={() => toggle(bens, setBens, p.cnl_ref)} />{p.name}</label>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label>Monthly budget ({ccy})</Label>
            <Input inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} placeholder="optional" />
          </div>
          <div>
            <Label>Human approval above ({ccy})</Label>
            <Input inputMode="decimal" value={approval} onChange={(e) => setApproval(e.target.value)} placeholder="optional" />
          </div>
          <div>
            <Label>Expiry date</Label>
            <Input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
          </div>
          <div>
            <Label>Purpose</Label>
            <Select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              <option value="">Select…</option>
              {PURPOSES.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          {["EXTERNAL_TRANSFER", "DELEGATION"].map((p) => (
            <label key={p} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={prohibit.includes(p)} onChange={() => toggle(prohibit, setProhibit, p)} />PROHIBIT {p}</label>
          ))}
        </div>
        {err && <Notice tone="bad">{err}</Notice>}
        <Button variant="accent" size="sm" disabled={!complete || busy} onClick={submit} data-testid="generate-cnl">Generate CNL from my answers</Button>
      </CardBody>
    </Card>
  );
}

function Tweaks({ cnl, setCnl, ccy }: { cnl: string; setCnl: (s: string) => void; ccy: string }) {
  return (
    <div className="rounded-md border border-border bg-surface2/40 p-3">
      <div className="mb-2 text-xs font-medium text-muted">Constraint controls (rewrite the CNL above)</div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(Object.keys(TWEAKS) as TweakKey[]).map((k) => {
          const v = readTweak(cnl, k);
          const minor = v ? parseMajorToMinor(v, ccy) : null;
          return (
            <div key={k}>
              <Label>{TWEAKS[k].label}</Label>
              <Input
                inputMode="decimal"
                disabled={v === null}
                value={v ?? ""}
                placeholder={v === null ? "not in CNL" : ""}
                onChange={(e) => /^\d*(\.\d{0,2})?$/.test(e.target.value) && e.target.value !== "" && setCnl(writeTweak(cnl, k, e.target.value))}
                aria-label={TWEAKS[k].label}
              />
              {minor !== null && <div className="mt-0.5 text-[11px] text-muted">= {formatMoney(minor, ccy)} · {minor} minor units</div>}
            </div>
          );
        })}
        <div>
          <Label>Expiry date</Label>
          <Input type="date" value={readExpiry(cnl)} disabled={!readExpiry(cnl)} onChange={(e) => e.target.value && setCnl(writeExpiry(cnl, e.target.value))} aria-label="Expiry date" />
        </div>
      </div>
    </div>
  );
}

function ParseErrors({ result, cnl }: { result: CompileResult; cnl: string }) {
  const lines = cnl.split("\n");
  return (
    <div className="space-y-2" data-testid="parse-errors">
      {result.errors.map((e, i) => (
        <Notice key={i} tone="bad" title={<span>{e.code}{e.line ? ` · line ${e.line}, col ${e.column}` : ""}</span>}>
          <div>{e.message}</div>
          {e.line && <pre className="mono mt-1 overflow-auto rounded bg-surface/60 p-2 text-[12px]">{lines[e.line - 1]}{"\n"}{" ".repeat(Math.max(0, (e.column ?? 1) - 1))}^</pre>}
          {e.expected && e.expected.length > 0 && <div className="mt-1 text-xs">Expected: {e.expected.join(", ")}</div>}
        </Notice>
      ))}
    </div>
  );
}

function CheckList({ checks }: { checks: { id: string; ok: boolean; detail: string }[] }) {
  return (
    <ul className="divide-y divide-border">
      {checks.map((c) => (
        <li key={c.id} className="flex items-start gap-2 px-3 py-1.5 text-[13px]">
          {c.ok ? <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-ok" /> : <XCircle size={14} className="mt-0.5 shrink-0 text-bad" />}
          <div className="min-w-0">
            <div className="mono text-xs">{c.id}</div>
            <div className="text-muted">{c.detail}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Artifacts({ r, lang, setLang }: { r: CompileResult | null; lang: "en" | "fr"; setLang: (l: "en" | "fr") => void }) {
  const [tab, setTab] = useState("normalized");
  const hasMandate = !!r?.mandate;
  const tabs = useMemo(
    () => [
      ["normalized", "Normalized CNL"], ["ast", "AST"], ["mandate", "Mandate JSON"], ["jsonld", "JSON-LD"], ["turtle", "Turtle"],
      ["shacl", "SHACL & checks"], ["oauth", "OAuth vs RAR"], ["policy", "Runtime policy"], ["effective", "Effective permissions"], ["consent", "Consent summary"],
    ],
    [],
  );
  return (
    <Card>
      <CardHeader title="3 · Compiled artifacts" description="Everything below is derived deterministically from the CNL." />
      <div className="px-3 pt-2">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>{tabs.map(([v, l]) => <TabsTrigger key={v} value={v}>{l}</TabsTrigger>)}</TabsList>
          <div className="py-3">
            {!r ? <Empty>Compiling…</Empty> : !hasMandate && tab !== "ast" ? (
              <Empty>No mandate yet — fix the CNL errors above.</Empty>
            ) : (
              <>
                <TabsContent value="normalized">
                  <JsonView data={r.normalized_cnl ?? ""} maxH="max-h-96" />
                  {r.defaults_applied && r.defaults_applied.length > 0 && (
                    <Notice tone="warn" className="mt-2" title="Defaults applied by the compiler (confirm before approval)">
                      <ul className="list-disc pl-4">{r.defaults_applied.map((d) => <li key={d}>{d}</li>)}</ul>
                    </Notice>
                  )}
                  <div className="mt-3"><KV label="Canonical digest"><Hash value={r.canonical_digest} full /></KV></div>
                </TabsContent>
                <TabsContent value="ast"><JsonView data={r.ast ?? []} maxH="max-h-96" /></TabsContent>
                <TabsContent value="mandate"><JsonView data={r.mandate} maxH="max-h-[28rem]" /></TabsContent>
                <TabsContent value="jsonld"><JsonView data={r.json_ld} maxH="max-h-[28rem]" /></TabsContent>
                <TabsContent value="turtle"><JsonView data={r.turtle ?? ""} maxH="max-h-[28rem]" /></TabsContent>
                <TabsContent value="shacl">
                  <div className="space-y-3" data-testid="shacl-panel">
                    <div className="flex items-center gap-2">
                      <Badge tone={r.shacl?.conforms ? "ok" : "bad"} data-testid="shacl-conforms">{r.shacl?.conforms ? "SHACL: conforms" : "SHACL: violations"}</Badge>
                      <span className="text-xs text-muted">Shapes validate the mandate&apos;s RDF graph against the KYM ontology.</span>
                    </div>
                    {r.shacl && !r.shacl.conforms && <JsonView data={r.shacl.results} />}
                    {r.shacl && <JsonView data={r.shacl.report_text} maxH="max-h-32" />}
                    <div className="grid gap-3 lg:grid-cols-2">
                      <Card><CardHeader title="Semantic checks" actions={<Badge tone={r.validation?.semantic.ok ? "ok" : "bad"}>{r.validation?.semantic.ok ? "pass" : "fail"}</Badge>} /><CheckList checks={r.validation?.semantic.checks ?? []} /></Card>
                      <Card><CardHeader title="Bank policy checks" actions={<Badge tone={r.validation?.bank_policy.ok ? "ok" : "bad"}>{r.validation?.bank_policy.ok ? "pass" : "fail"}</Badge>} /><CheckList checks={r.validation?.bank_policy.checks ?? []} /></Card>
                    </div>
                  </div>
                </TabsContent>
                <TabsContent value="oauth">
                  {r.oauth && (
                    <div className="space-y-3">
                      <div className="grid gap-3 lg:grid-cols-2">
                        <Card>
                          <CardHeader title="OAuth scopes" description="Coarse, bank-defined strings" />
                          <CardBody className="flex flex-wrap gap-1.5">{r.oauth.scopes.map((s) => <Badge key={s} tone="info" className="mono">{s}</Badge>)}</CardBody>
                        </Card>
                        <Card>
                          <CardHeader title="What scopes cannot express" description="Carried by RAR (RFC 9396) or by the mandate itself" />
                          <Table>
                            <THead><TR><TH>Dimension</TH><TH>Carried by</TH></TR></THead>
                            <TBody>{r.oauth.scope_gaps.map((g) => <TR key={g.dimension}><TD>{g.dimension}</TD><TD className="text-muted">{g.carried_by}</TD></TR>)}</TBody>
                          </Table>
                        </Card>
                      </div>
                      <Card>
                        <CardHeader title="RAR authorization_details" description="Structured, per-account/beneficiary/amount authority sent with the token request" />
                        <CardBody><JsonView data={r.oauth.authorization_details} maxH="max-h-80" /></CardBody>
                      </Card>
                      <JsonView data={r.oauth.kym_token_claims} maxH="max-h-32" />
                    </div>
                  )}
                </TabsContent>
                <TabsContent value="policy"><JsonView data={r.runtime_policy} maxH="max-h-[28rem]" /></TabsContent>
                <TabsContent value="effective">
                  <p className="mb-2 text-xs text-muted">Effective authority is the intersection of: mandate permissions ∩ agent registered capabilities and status ∩ accounts the principal actually controls ∩ bank policy caps.</p>
                  <Table>
                    <THead><TR><TH>Action</TH><TH>Resources</TH><TH>Effective</TH><TH>Limits</TH><TH>Narrowed by</TH></TR></THead>
                    <TBody>
                      {(r.effective_permissions ?? []).map((p, i) => (
                        <TR key={i}>
                          <TD><div>{actionLabel(p.action)}</div><div className="mono text-[11px] text-muted">{p.action}</div></TD>
                          <TD className="mono text-xs">{p.resources.join(", ")}</TD>
                          <TD><Badge tone={p.effective ? "ok" : "bad"}>{p.effective ? "effective" : "not effective"}</Badge></TD>
                          <TD className="text-xs">{p.limits.length ? p.limits.map((l) => <div key={l}>{l}</div>) : "—"}</TD>
                          <TD className="text-xs">{p.narrowed_by.length ? p.narrowed_by.map((l) => <div key={l}>{l}</div>) : "—"}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </TabsContent>
                <TabsContent value="consent">
                  <div className="mb-2 flex items-center gap-2">
                    {(["en", "fr"] as const).map((l) => (
                      <Button key={l} size="sm" variant={lang === l ? "default" : "outline"} onClick={() => setLang(l)}>{l.toUpperCase()}</Button>
                    ))}
                    <span className="ml-2 text-xs text-muted">Shown to the customer in the bank-controlled interface; its digest is bound to the approval.</span>
                  </div>
                  <pre className="whitespace-pre-wrap rounded-md border border-border bg-surface2/50 p-3 text-[13px] leading-relaxed" data-testid="consent-summary">{r.consent_summary?.[lang]}</pre>
                  <div className="mt-3"><KV label="Canonical digest"><Hash value={r.canonical_digest} full /></KV></div>
                </TabsContent>
              </>
            )}
          </div>
        </Tabs>
      </div>
    </Card>
  );
}

function Lifecycle({ id, version, initial }: { id: string; version: number; initial: MandateView }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const q = useQ(["mandate", id, version], () => api.mandate(id, version), { refetchInterval: 4000 });
  const m = q.data ?? initial;
  const activate = useMutation({ mutationFn: () => api.activateMandate(id, version), onSuccess: () => qc.invalidateQueries() });
  const isCustomer = user?.role === "customer";
  const err = activate.error instanceof ApiError ? activate.error.message : null;
  return (
    <Card className="border-accent/40" data-testid="lifecycle">
      <CardHeader title={<span>Mandate created · <span className="mono">{m.mandate_id} v{m.version}</span></span>} actions={<StatusBadge kind="mandate" status={m.status} />} description="Immutable version. Lifecycle state is authoritative bank state, held separately from the content." />
      <CardBody className="space-y-3">
        <KV label="Digest"><Hash value={m.digest} full /></KV>
        <KV label="Customer approval">{m.consent ? <Badge tone="ok">recorded · {m.consent.id}</Badge> : <Badge tone="warn">not yet approved</Badge>}</KV>
        <ol className="space-y-1 border-l border-border pl-3 text-xs">
          {m.state_history.map((h, i) => (
            <li key={i}><span className="mono">{h.to}</span> <span className="text-muted">· {h.actor} · {fmtDateTime(h.at)} · {h.reason}</span></li>
          ))}
        </ol>
        {m.status === "PENDING_CUSTOMER_APPROVAL" && !m.consent && (
          <Notice tone="info">
            The agent cannot use this mandate until the customer approves it in the bank-controlled portal.{" "}
            {isCustomer ? <Link href={`/portal?mandate=${m.mandate_id}`} className="font-medium underline">Approve in bank portal →</Link> : <span>Switch to the customer in the header to approve.</span>}
          </Notice>
        )}
        {m.status === "PENDING_CUSTOMER_APPROVAL" && m.consent && (
          <div className="flex items-center gap-2">
            <Button variant="success" onClick={() => activate.mutate()} disabled={activate.isPending}>Activate mandate</Button>
            <span className="text-xs text-muted">Approval is bound to digest {m.digest.slice(7, 19)}…</span>
          </div>
        )}
        {err && <Notice tone="bad">{err}</Notice>}
        {m.status === "ACTIVE" && <Notice tone="ok">Mandate is ACTIVE. Try it in the <Link className="underline" href="/playground">authorization playground</Link>.</Notice>}
        {m.status === "REJECTED" && <Notice tone="bad" title="Rejected by validation">{m.state_history.at(-1)?.reason}</Notice>}
      </CardBody>
    </Card>
  );
}

function TwoPhrasings({ open, onClose, principal }: { open: boolean; onClose: () => void; principal: string }) {
  const A = `PURPOSE household_bill_management.
PERMIT agent.finance-assistant TO READ_BALANCE ON account.chequing-001.
PERMIT agent.finance-assistant TO PAY_INVOICE FROM account.chequing-001 TO beneficiary.hydro-quebec, beneficiary.videotron WITH MAX_AMOUNT 250.00 CAD PER TRANSACTION.
PROHIBIT EXTERNAL_TRANSFER.
START AT 2026-12-01T00:00:00Z.
EXPIRE AT 2027-01-01T00:00:00Z.
`;
  const B = `// same authority, different phrasing and order
EXPIRE AT 2027-01-01T00:00:00Z.
FORBID EXTERNAL_TRANSFER.
START AT 2026-12-01T00:00:00Z.
ALLOW agent.finance-assistant TO PAY_INVOICE FROM account.chequing-001 TO beneficiary.videotron, beneficiary.hydro-quebec WITH MAX_AMOUNT CAD 250 PER TRANSACTION.
ALLOW agent.finance-assistant TO READ_BALANCE ON account.chequing-001.
PURPOSE household_bill_management.
`;
  const [out, setOut] = useState<{ a?: CompileResult; b?: CompileResult; err?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const [a, b] = await Promise.all([api.compile({ principal_id: principal, cnl: A }), api.compile({ principal_id: principal, cnl: B })]);
      setOut({ a, b });
    } catch (e) {
      setOut({ err: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const same = out?.a?.canonical_digest && out.a.canonical_digest === out.b?.canonical_digest;
  return (
    <Dialog open={open} onClose={onClose} wide title="Two phrasings → same digest">
      <p className="mb-3 text-[13px] text-muted">Different wording, statement order, money formats and synonyms (PERMIT/ALLOW, PROHIBIT/FORBID) that express the same authority compile to the same canonical mandate and therefore the same SHA-256 digest. A single changed limit would not.</p>
      <div className="grid gap-3 md:grid-cols-2">
        {([["Phrasing A", A, out?.a], ["Phrasing B", B, out?.b]] as const).map(([t, text, r]) => (
          <Card key={t}>
            <CardHeader title={t} />
            <CardBody className="space-y-2">
              <pre className="mono overflow-auto whitespace-pre-wrap text-[11.5px]">{text}</pre>
              {r && <div className="text-xs">{r.ok ? <>digest <Hash value={r.canonical_digest} head={16} tail={8} /></> : <span className="text-bad">{r.errors.map((e) => e.message).join("; ")}</span>}</div>}
            </CardBody>
          </Card>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button variant="accent" onClick={run} disabled={busy || !principal}>Compile both</Button>
        {out?.err && <span className="text-sm text-bad">{out.err}</span>}
        {out?.a && out.b && <Badge tone={same ? "ok" : "bad"} data-testid="digest-match">{same ? "Digests are IDENTICAL" : "Digests differ"}</Badge>}
      </div>
      <p className="mt-2 text-xs text-muted">Uses the selected principal ({principal}); the example references Alice&apos;s accounts.</p>
    </Dialog>
  );
}
