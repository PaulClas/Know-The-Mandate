"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Async, DecisionBadge, Empty, Hash, JsonView, KV, Notice, PageHeader, ReasonCodes, Spinner, StatusBadge } from "@/components/common";
import { useQ } from "@/components/providers";
import { TraceChecklist } from "@/components/trace";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { actionLabel } from "@/lib/taxonomy";
import { fmtDateTime } from "@/lib/utils";
import Link from "next/link";

const STATUSES = ["EXECUTED", "DENIED", "PENDING_APPROVAL", "RISK_REVIEW", "CANCELLED", "COMPLETED"];

export default function TransactionsPage() {
  const [status, setStatus] = useState("");
  const [text, setText] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const q = useQ(["transactions", status], () => api.transactions(status || undefined), { refetchInterval: 10_000 });
  const filtered = useMemo(() => {
    const t = text.toLowerCase();
    return (q.data ?? []).filter((x) => !t || [x.id, x.agent_id, x.action, x.payee_id, x.mandate_id, ...(x.reason_codes ?? [])].join(" ").toLowerCase().includes(t));
  }, [q.data, text]);

  return (
    <>
      <PageHeader title="Transaction monitor" description="Every action an agent attempted — executed or not. Amounts are stored as integer minor units." />
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <Search size={14} className="text-muted" />
          <Input className="max-w-xs" placeholder="Search id, agent, action, reason code…" value={text} onChange={(e) => setText(e.target.value)} />
          <Select className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
          <span className="ml-auto text-xs text-muted">{filtered.length} shown</span>
        </div>
        <Async q={q} what="transactions">
          {() =>
            filtered.length === 0 ? (
              <Empty>No transactions match. Run a scenario or the sandbox to generate activity.</Empty>
            ) : (
              <Table>
                <THead><TR><TH>Time</TH><TH>Transaction</TH><TH>Action</TH><TH>Agent</TH><TH className="text-right">Amount</TH><TH>Status</TH><TH>Decision</TH><TH>Reason codes</TH></TR></THead>
                <TBody>
                  {filtered.map((t) => (
                    <TR key={t.id} onClick={() => setSel(t.id)} data-testid={`tx-row`}>
                      <TD className="whitespace-nowrap text-xs text-muted">{fmtDateTime(t.created_at)}</TD>
                      <TD><span className="mono text-xs">{t.id}</span></TD>
                      <TD>{actionLabel(t.action)}</TD>
                      <TD className="mono text-xs">{t.agent_id}</TD>
                      <TD className="mono text-right">{t.amount_minor != null ? formatMoney(t.amount_minor, t.currency) : "—"}</TD>
                      <TD><StatusBadge kind="tx" status={t.status} /></TD>
                      <TD><DecisionBadge decision={t.outcome} /></TD>
                      <TD><ReasonCodes codes={t.reason_codes} /></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )
          }
        </Async>
      </Card>
      <TxDrawer id={sel} onClose={() => setSel(null)} />
    </>
  );
}

function TxDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useQ(["transaction", id], () => api.transaction(id!), { enabled: !!id });
  const t = q.data;
  return (
    <Dialog open={!!id} onClose={onClose} side title={<span className="mono">{id}</span>}>
      {q.isLoading && <Spinner />}
      {q.error && <Notice tone="bad">{q.error.message}</Notice>}
      {t && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge kind="tx" status={t.status} />
            <DecisionBadge decision={t.outcome} />
            <ReasonCodes codes={t.reason_codes} />
          </div>
          <Card>
            <CardBody className="py-2">
              <KV label="Action">{actionLabel(t.action)} <span className="mono text-xs text-muted">{t.action}</span></KV>
              <KV label="Amount" mono>{formatMoney(t.amount_minor, t.currency)} {t.amount_minor != null && <span className="text-muted">({t.amount_minor} minor)</span>}</KV>
              <KV label="Account" mono>{t.account_id}</KV>
              <KV label="Counterparty" mono>{t.payee_id}</KV>
              <KV label="Agent" mono>{t.agent_id}</KV>
              <KV label="Principal" mono>{t.principal_id}</KV>
              <KV label="Mandate" mono>{t.mandate_id ? `${t.mandate_id} v${t.mandate_version}` : "—"}</KV>
              <KV label="Correlation"><Hash value={t.correlation_id} full /></KV>
              <KV label="Created">{fmtDateTime(t.created_at)}</KV>
              {t.failure_reason && <KV label="Failure">{t.failure_reason}</KV>}
              {t.risk && <KV label="Risk"><Badge>{t.risk.level} · {t.risk.score}</Badge></KV>}
            </CardBody>
          </Card>
          {t.decision && (
            <Card>
              <CardHeader title="Decision trace" description={`policy ${t.decision.policy_version}`} />
              <TraceChecklist trace={t.decision.trace} />
            </Card>
          )}
          {t.operation && <JsonView data={t.operation} maxH="max-h-48" />}
          <div className="flex gap-3 text-xs">
            <Link className="text-accent hover:underline" href={`/disputes?tx=${t.id}`}>Open dispute investigation →</Link>
            <Link className="text-accent hover:underline" href={`/ledger?q=${t.correlation_id}`}>Ledger events →</Link>
          </div>
        </div>
      )}
    </Dialog>
  );
}
