"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Async, Empty, Hash, JsonView, KV, Notice, PageHeader, Spinner } from "@/components/common";
import { useQ } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/utils";

const EVENT_TYPES = [
  "CUSTOMER_VERIFIED", "AGENT_REGISTERED", "AGENT_VERIFIED", "AGENT_SUSPENDED", "MANDATE_PROPOSED", "MANDATE_VALIDATED", "MANDATE_APPROVED", "MANDATE_ACTIVATED",
  "MANDATE_AMENDED", "MANDATE_DELEGATED", "MANDATE_REVOKED", "MANDATE_SUSPENDED", "MANDATE_APPROVAL_REQUESTED", "MANDATE_REJECTED", "MANDATE_EXPIRED", "MANDATE_SUPERSEDED",
  "TOKEN_ISSUED", "TOKEN_REJECTED", "TOKEN_REVOKED", "ACTION_REQUESTED", "POLICY_EVALUATED", "ACTION_DENIED", "RISK_EVALUATED", "HUMAN_APPROVAL_REQUESTED",
  "HUMAN_APPROVAL_GRANTED", "HUMAN_APPROVAL_REJECTED", "PAYMENT_EXECUTED", "PAYMENT_FAILED", "DISPUTE_OPENED",
];
const PAGE = 100;

export default function LedgerPage() {
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("q");
    if (p) setText(p);
  }, []);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(text); setOffset(0); }, 300);
    return () => clearTimeout(t);
  }, [text]);

  const q = useQ(["ledger", debounced, type, offset], () => api.ledgerEvents({ q: debounced, event_type: type, limit: PAGE, offset }));
  const verify = useMutation({ mutationFn: api.ledgerVerify });
  const cps = useQ(["checkpoints"], api.checkpoints);

  return (
    <>
      <PageHeader
        title="KYM evidence ledger"
        description="Append-only, hash-chained, signed record of every governance and enforcement event. The ledger proves integrity and key control; it does not by itself prove legally effective consent."
        actions={<Button variant="accent" onClick={() => verify.mutate()} disabled={verify.isPending} data-testid="verify-ledger"><ShieldCheck size={14} /> Verify integrity</Button>}
      />
      {verify.error && <Notice tone="bad" className="mb-4">{verify.error.message}</Notice>}
      {verify.data && (
        <Card className="mb-4" data-testid="verify-report">
          <CardHeader title="Integrity verification report" actions={verify.data.ok ? <Badge tone="ok"><CheckCircle2 size={12} /> VERIFIED</Badge> : <Badge tone="bad"><XCircle size={12} /> FAILED</Badge>} />
          <CardBody className="grid gap-4 md:grid-cols-2">
            <div>
              <KV label="Events checked">{verify.data.events_checked}</KV>
              <KV label="Checkpoints checked">{verify.data.checkpoints_checked}</KV>
              <KV label="Head hash"><Hash value={verify.data.head_hash} full /></KV>
              <KV label="Verified at">{fmtDateTime(verify.data.verified_at)}</KV>
              <KV label="Checks"><span className="flex flex-wrap gap-1">{verify.data.checks.map((c) => <Badge key={c} tone="ok" className="mono">{c}</Badge>)}</span></KV>
              {verify.data.problems.length > 0 && <JsonView data={verify.data.problems} />}
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted">Assumptions</div>
              <ul className="list-disc space-y-1 pl-4 text-xs text-muted">{verify.data.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
          </CardBody>
        </Card>
      )}

      <Tabs defaultValue="events">
        <TabsList>
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="checkpoints">Checkpoints</TabsTrigger>
        </TabsList>
        <TabsContent value="events" className="pt-4">
          <Card>
            <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
              <Input className="max-w-sm" placeholder="Search event, correlation, actor, mandate, transaction…" value={text} onChange={(e) => setText(e.target.value)} data-testid="ledger-search" />
              <Select className="w-auto" value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }} aria-label="Event type">
                <option value="">All event types</option>
                {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
              <span className="ml-auto text-xs text-muted">{q.data ? `${q.data.total} events` : ""}</span>
            </div>
            <Async q={q} what="ledger events">
              {(d) =>
                d.events.length === 0 ? <Empty>No events match.</Empty> : (
                  <>
                    <Table>
                      <THead><TR><TH>Seq</TH><TH>Event</TH><TH>Type</TH><TH>Correlation</TH><TH>Event hash</TH><TH>Previous hash</TH><TH>Signature</TH><TH>Actor</TH><TH>Mandate</TH></TR></THead>
                      <TBody>
                        {d.events.map((e) => (
                          <TR key={e.event_id} onClick={() => setSel(e.event_id)} data-testid="ledger-row">
                            <TD className="tabular-nums">{e.sequence}</TD>
                            <TD><span className="mono text-xs">{e.event_id}</span><div className="text-[11px] text-muted">{fmtDateTime(e.timestamp)}</div></TD>
                            <TD><Badge className="mono">{e.event_type}</Badge></TD>
                            <TD><Hash value={e.correlation_id} head={10} tail={4} /></TD>
                            <TD><Hash value={e.event_hash} /></TD>
                            <TD><Hash value={e.previous_hash} /></TD>
                            <TD><Hash value={e.signature} head={8} tail={4} /></TD>
                            <TD className="text-xs">{e.actor_id}<div className="text-muted">{e.actor_type}</div></TD>
                            <TD className="mono text-xs">{e.mandate_id ? `${e.mandate_id} v${e.mandate_version}` : "—"}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                    <div className="flex items-center justify-between border-t border-border p-2 text-xs">
                      <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                      <span className="text-muted">{offset + 1}–{offset + d.events.length} of {d.total}</span>
                      <Button size="sm" variant="outline" disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
                    </div>
                  </>
                )
              }
            </Async>
          </Card>
        </TabsContent>
        <TabsContent value="checkpoints" className="pt-4">
          <Async q={cps} what="checkpoints">
            {(c) => (
              <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
                <Card>
                  <CardHeader title="Signed checkpoints" description="Signed head hashes; compare with externally held copies to detect wholesale replacement." />
                  {c.checkpoints.length === 0 ? <Empty>No checkpoints.</Empty> : (
                    <Table>
                      <THead><TR><TH>Checkpoint</TH><TH>Seq</TH><TH>Events</TH><TH>Head hash</TH><TH>Signature</TH><TH>Witness</TH><TH>Created</TH></TR></THead>
                      <TBody>
                        {c.checkpoints.map((x) => (
                          <TR key={x.checkpoint_id}>
                            <TD className="mono text-xs">{x.checkpoint_id}</TD>
                            <TD>{x.sequence}</TD>
                            <TD>{x.event_count}</TD>
                            <TD><Hash value={x.head_hash} head={12} tail={6} /></TD>
                            <TD><Hash value={x.signature} head={8} tail={4} /><div className="mono text-[10px] text-muted">{x.key_id}</div></TD>
                            <TD>{x.witness_signature ? <><Hash value={x.witness_signature} head={8} tail={4} /><div className="mono text-[10px] text-muted">{x.witness_key_id}</div></> : "—"}</TD>
                            <TD className="text-xs">{fmtDateTime(x.created_at)}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  )}
                </Card>
                <Card>
                  <CardHeader title="Public keys" />
                  <CardBody><JsonView data={c.public_keys} maxH="max-h-96" /></CardBody>
                </Card>
              </div>
            )}
          </Async>
        </TabsContent>
      </Tabs>
      <EventDrawer id={sel} onClose={() => setSel(null)} />
    </>
  );
}

function EventDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useQ(["ledger-event", id], () => api.ledgerEvent(id!), { enabled: !!id });
  const e = q.data;
  return (
    <Dialog open={!!id} onClose={onClose} side title={<span className="mono">{id}</span>}>
      {q.isLoading && <Spinner />}
      {q.error && <Notice tone="bad">{q.error.message}</Notice>}
      {e && (
        <div className="space-y-4">
          <Card><CardBody className="py-2">
            <KV label="Type"><Badge className="mono">{e.event_type}</Badge></KV>
            <KV label="Sequence">{e.sequence}</KV>
            <KV label="Timestamp">{fmtDateTime(e.timestamp)}</KV>
            <KV label="Actor" mono>{e.actor_id} ({e.actor_type})</KV>
            <KV label="Principal" mono>{e.principal_id}</KV>
            <KV label="Agent" mono>{e.agent_id}</KV>
            <KV label="Mandate" mono>{e.mandate_id ? `${e.mandate_id} v${e.mandate_version}` : null}</KV>
            <KV label="Transaction" mono>{e.transaction_id}</KV>
            <KV label="Correlation"><Hash value={e.correlation_id} full /></KV>
            <KV label="Policy / ontology" mono>{e.policy_version} · {e.ontology_version}</KV>
            <KV label="Payload digest"><Hash value={e.payload_digest} full /></KV>
            <KV label="Previous hash"><Hash value={e.previous_hash} full /></KV>
            <KV label="Event hash"><Hash value={e.event_hash} full /></KV>
            <KV label="Signature"><Hash value={e.signature} full /></KV>
            <KV label="Signer" mono>{e.signer_id} · {e.signing_key_id}</KV>
          </CardBody></Card>
          <div>
            <div className="mb-1 text-xs font-medium text-muted">Payload {e.payload_redacted && <Badge tone="warn">redacted (erased; chain still verifies via digest)</Badge>}</div>
            <JsonView data={e.payload ?? null} maxH="max-h-96" />
          </div>
        </div>
      )}
    </Dialog>
  );
}
