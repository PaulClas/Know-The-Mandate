"use client";

import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";
import { Async, Empty, PageHeader, StatusBadge } from "@/components/common";
import { useQ } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import type { DelegationNode } from "@/lib/types";
import { fmtDate } from "@/lib/utils";

const COLOR: Record<string, string> = { ACTIVE: "#15803d", PENDING_CUSTOMER_APPROVAL: "#b45309", SUSPENDED: "#b45309", REVOKED: "#b91c1c", REJECTED: "#b91c1c" };

export default function DelegationPage() {
  const q = useQ(["delegation"], () => api.delegationGraph(), { refetchInterval: 10_000 });
  const [sel, setSel] = useState<string | null>(null);

  return (
    <>
      <PageHeader title="Delegation graph" description="A child mandate can only narrow its parent: lower or equal limits, a subset of actions and counterparties, an earlier or equal expiry, and a bounded depth." />
      <Async q={q} what="delegation graph">
        {(g) => g.nodes.length === 0 ? (
          <Card><Empty>No mandates yet. Run scenario for delegation (admin) or create a mandate in the studio.</Empty></Card>
        ) : (
          <Graph nodes={g.nodes} edges={g.edges} sel={sel} setSel={setSel} />
        )}
      </Async>
    </>
  );
}

function Graph({ nodes, edges, sel, setSel }: { nodes: DelegationNode[]; edges: { source: string; target: string }[]; sel: string | null; setSel: (id: string | null) => void }) {
  const rf = useMemo(() => {
    const byDepth = new Map<number, DelegationNode[]>();
    nodes.forEach((n) => byDepth.set(n.depth, [...(byDepth.get(n.depth) ?? []), n]));
    const rn: Node[] = nodes.map((n) => {
      const row = byDepth.get(n.depth)!;
      return {
        id: n.id,
        position: { x: row.indexOf(n) * 270, y: n.depth * 150 },
        data: {
          label: (
            <div className="text-left text-[11px] leading-snug">
              <div className="font-semibold">{n.agent_id}</div>
              <div className="mono">{n.mandate_id} v{n.version}</div>
              <div>{n.status.replace(/_/g, " ")} · depth {n.depth}</div>
              <div>max {formatMoney(n.max_amount_minor, n.currency)}</div>
            </div>
          ),
        },
        style: { width: 230, border: `2px solid ${n.id === sel ? "var(--accent)" : COLOR[n.status] ?? "#64748b"}`, borderRadius: 8, background: "var(--surface)", color: "var(--foreground)", padding: 8 },
      };
    });
    const re: Edge[] = edges.map((e) => ({ id: `${e.source}->${e.target}`, source: e.source, target: e.target, label: "delegates", markerEnd: { type: MarkerType.ArrowClosed }, animated: true }));
    return { rn, re };
  }, [nodes, edges, sel]);

  const node = nodes.find((n) => n.id === sel);
  const parentEdge = edges.find((e) => e.target === sel);
  const parent = nodes.find((n) => n.id === parentEdge?.source);
  const childEdges = edges.filter((e) => e.source === sel);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <Card className="h-[560px] overflow-hidden" data-testid="delegation-graph">
        <ReactFlow nodes={rf.rn} edges={rf.re} fitView onNodeClick={(_, n) => setSel(n.id)} onPaneClick={() => setSel(null)} nodesDraggable={false} proOptions={{ hideAttribution: true }}>
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Card>
      <div className="space-y-4">
        <Card>
          <CardHeader title={node ? "Selected mandate" : "Select a node"} />
          <CardBody className="space-y-2 text-[13px]">
            {!node ? <span className="text-muted">Click a mandate to compare it with its parent.</span> : (
              <>
                <div className="flex items-center gap-2"><span className="mono">{node.id}</span><StatusBadge kind="mandate" status={node.status} /></div>
                <div>Agent <span className="mono">{node.agent_id}</span> · principal <span className="mono">{node.principal_id}</span></div>
                <div>Delegation: {node.delegation.allowed ? `allowed to depth ${node.delegation.maximum_depth}` : "not allowed"} · this depth {node.depth}</div>
                <div>{childEdges.length} child mandate(s)</div>
              </>
            )}
          </CardBody>
        </Card>
        {node && parent && <Compare parent={parent} child={node} />}
        {node && !parent && <Card><CardBody className="text-xs text-muted">Root mandate — granted directly by the customer; no parent to compare.</CardBody></Card>}
      </div>
    </div>
  );
}

function Compare({ parent, child }: { parent: DelegationNode; child: DelegationNode }) {
  const subset = (a: string[], b: string[]) => a.every((x) => b.includes(x));
  const rows: { label: string; p: string; c: string; ok: boolean }[] = [
    { label: "Max per payment", p: formatMoney(parent.max_amount_minor, parent.currency), c: formatMoney(child.max_amount_minor, child.currency), ok: child.max_amount_minor <= parent.max_amount_minor },
    { label: "Monthly budget", p: parent.monthly_minor != null ? formatMoney(parent.monthly_minor, parent.currency) : "none", c: child.monthly_minor != null ? formatMoney(child.monthly_minor, child.currency) : "none", ok: parent.monthly_minor == null || (child.monthly_minor != null && child.monthly_minor <= parent.monthly_minor) },
    { label: "Actions", p: parent.actions.join(", "), c: child.actions.join(", "), ok: subset(child.actions, parent.actions) },
    { label: "Beneficiaries", p: parent.beneficiaries.join(", ") || "—", c: child.beneficiaries.join(", ") || "—", ok: subset(child.beneficiaries, parent.beneficiaries) },
    { label: "Expires", p: fmtDate(parent.expires_at), c: fmtDate(child.expires_at), ok: child.expires_at <= parent.expires_at },
    { label: "Depth", p: String(parent.depth), c: String(child.depth), ok: child.depth <= parent.depth + 1 && child.depth <= parent.delegation.maximum_depth + parent.depth },
  ];
  const allOk = rows.every((r) => r.ok);
  return (
    <Card data-testid="authority-compare">
      <CardHeader title="Parent vs child authority" description="Child must be ⊆ parent" actions={<Badge tone={allOk ? "ok" : "bad"}>{allOk ? "child narrows parent" : "child exceeds parent"}</Badge>} />
      <Table>
        <THead><TR><TH>Dimension</TH><TH>Parent</TH><TH>Child</TH><TH /></TR></THead>
        <TBody>
          {rows.map((r) => (
            <TR key={r.label}><TD className="text-muted">{r.label}</TD><TD className="mono text-xs">{r.p}</TD><TD className="mono text-xs">{r.c}</TD><TD>{r.ok ? <span className="text-ok">✓</span> : <span className="text-bad">✗</span>}</TD></TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
