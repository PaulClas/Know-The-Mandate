"use client";

import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Play } from "lucide-react";
import { useMemo, useState } from "react";
import { Async, Empty, JsonView, Notice, PageHeader, Spinner } from "@/components/common";
import { useQ } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select, Textarea } from "@/components/ui/input";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { GraphNode, OntologyCategory, OntologySummary, SparqlResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";

const CATS: { id: OntologyCategory; label: string; color: string }[] = [
  { id: "customer", label: "Customer", color: "#2563eb" },
  { id: "agent", label: "Agent", color: "#0f766e" },
  { id: "mandate", label: "Mandate", color: "#1e3a5f" },
  { id: "resource", label: "Resource", color: "#7c3aed" },
  { id: "permission", label: "Permission", color: "#15803d" },
  { id: "constraint", label: "Constraint", color: "#b45309" },
  { id: "evidence", label: "Evidence", color: "#64748b" },
  { id: "delegation", label: "Delegation", color: "#c2410c" },
  { id: "responsibility", label: "Responsibility", color: "#be123c" },
];
const COLOR = Object.fromEntries(CATS.map((c) => [c.id, c.color]));

export default function OntologyPage() {
  const [mode, setMode] = useState<"schema" | "instances">("schema");
  const [cats, setCats] = useState<OntologyCategory[]>(CATS.map((c) => c.id));
  const [node, setNode] = useState<GraphNode | null>(null);
  const summary = useQ(["ontology"], api.ontology);
  const graph = useQ(["ontology-graph", mode, cats.join(",")], () => api.ontologyGraph(mode, cats), { enabled: cats.length > 0 });

  const toggle = (c: OntologyCategory) => setCats((x) => (x.includes(c) ? x.filter((y) => y !== c) : [...x, c]));

  return (
    <>
      <PageHeader title="Ontology explorer" description="The KYM vocabulary and the live knowledge graph built from the registry, mandates, transactions and evidence. Experimental placeholder vocabulary (example.org)." />
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-2 p-3">
          <div className="flex rounded-md border border-border p-0.5" role="group" aria-label="Graph mode">
            {(["schema", "instances"] as const).map((m) => (
              <button key={m} onClick={() => { setMode(m); setNode(null); }} className={cn("cursor-pointer rounded px-2.5 py-1 text-xs font-medium", mode === m ? "bg-navy text-white dark:bg-accent dark:text-accentfg" : "text-muted")}>{m === "schema" ? "Schema (classes)" : "Instances"}</button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5" data-testid="category-chips">
            {CATS.map((c) => {
              const on = cats.includes(c.id);
              return (
                <button key={c.id} onClick={() => toggle(c.id)} aria-pressed={on} className={cn("flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs", on ? "border-transparent text-white" : "border-border text-muted")} style={on ? { background: c.color } : undefined}>
                  {c.label}
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card className="h-[620px] overflow-hidden" data-testid="ontology-graph">
          {cats.length === 0 ? <Empty>Select at least one category.</Empty> : (
            <Async q={graph} what="ontology graph">
              {(g) => g.nodes.length === 0 ? <Empty>No nodes in this selection{mode === "instances" ? " — instances appear as agents, mandates and transactions are created" : ""}.</Empty> : <Graph nodes={g.nodes} edges={g.edges} sel={node?.id} onSelect={setNode} />}
            </Async>
          )}
        </Card>
        <NodePanel node={node} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Class hierarchy" description="rdfs:subClassOf" />
          <Async q={summary} what="ontology summary">{(s) => <Hierarchy s={s} />}</Async>
        </Card>
        <Sparql />
      </div>
    </>
  );
}

function Graph({ nodes, edges, sel, onSelect }: { nodes: GraphNode[]; edges: { source: string; target: string; label?: string }[]; sel?: string; onSelect: (n: GraphNode) => void }) {
  const { rn, re } = useMemo(() => {
    const present = CATS.filter((c) => nodes.some((n) => n.category === c.id));
    const pos = new Map<string, { x: number; y: number }>();
    let bx = 0, by = 0, rowH = 0;
    present.forEach((c, bi) => {
      const group = nodes.filter((n) => n.category === c.id);
      const cols = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(group.length))));
      const rows = Math.ceil(group.length / cols);
      if (bi > 0 && bi % 3 === 0) { bx = 0; by += rowH + 80; rowH = 0; }
      group.forEach((n, i) => pos.set(n.id, { x: bx + (i % cols) * 190, y: by + Math.floor(i / cols) * 56 }));
      bx += cols * 190 + 60;
      rowH = Math.max(rowH, rows * 56);
    });
    const ids = new Set(nodes.map((n) => n.id));
    const rn: Node[] = nodes.map((n) => ({
      id: n.id,
      position: pos.get(n.id) ?? { x: 0, y: 0 },
      data: { label: n.label },
      style: { width: 170, fontSize: 11, padding: 5, borderRadius: 6, background: "var(--surface)", color: "var(--foreground)", border: `${n.id === sel ? 3 : 1.5}px solid ${COLOR[n.category] ?? "#64748b"}` },
    }));
    const re: Edge[] = edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e, i) => ({ id: `${i}-${e.source}-${e.target}`, source: e.source, target: e.target, label: e.label, labelStyle: { fontSize: 9 }, style: { strokeWidth: 1 } }));
    return { rn, re };
  }, [nodes, edges, sel]);
  return (
    <ReactFlow nodes={rn} edges={re} fitView minZoom={0.1} nodesDraggable onNodeClick={(_, n) => onSelect(nodes.find((x) => x.id === n.id)!)} proOptions={{ hideAttribution: true }}>
      <Background />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable nodeColor={(n) => COLOR[nodes.find((x) => x.id === n.id)?.category ?? ""] ?? "#64748b"} />
    </ReactFlow>
  );
}

function NodePanel({ node }: { node: GraphNode | null }) {
  const q = useQ(["onto-triples", node?.id], () => api.ontologyTriples(node!.id), { enabled: !!node });
  return (
    <Card className="max-h-[620px] overflow-auto">
      <CardHeader title={node ? node.label : "Node details"} description={node ? `${node.category}${node.type ? ` · ${node.type}` : ""}` : "Click a node to see its triples and JSON-LD"} />
      <CardBody className="space-y-3">
        {!node && <span className="text-[13px] text-muted">Nothing selected.</span>}
        {node && q.isLoading && <Spinner />}
        {node && q.error && <Notice tone="bad">{q.error.message}</Notice>}
        {q.data && (
          <>
            <div className="mono break-all text-[11px] text-muted">{q.data.node as string}</div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted">Triples ({q.data.triples.length})</div>
              <Table>
                <THead><TR><TH>Subject</TH><TH>Predicate</TH><TH>Object</TH></TR></THead>
                <TBody>{q.data.triples.map((t, i) => <TR key={i}>{t.map((x, j) => <TD key={j} className="mono break-all text-[11px]">{local(x)}</TD>)}</TR>)}</TBody>
              </Table>
            </div>
            <div><div className="mb-1 text-xs font-medium text-muted">JSON-LD</div><JsonView data={q.data.json_ld} maxH="max-h-72" /></div>
          </>
        )}
      </CardBody>
    </Card>
  );
}

const local = (iri: string) => iri.replace("https://example.org/kym/v1#", "kym:").replace("https://example.org/kym/id/", "kymid:").replace("http://www.w3.org/2000/01/rdf-schema#", "rdfs:").replace("http://www.w3.org/ns/prov#", "prov:").replace("http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdf:");

function Hierarchy({ s }: { s: OntologySummary }) {
  const ids = new Set(s.classes.map((c) => c.id));
  const children = new Map<string, typeof s.classes>();
  const roots: typeof s.classes = [];
  for (const c of s.classes) {
    const ps = c.parents.filter((p) => ids.has(p));
    if (ps.length === 0) roots.push(c);
    for (const p of ps) children.set(p, [...(children.get(p) ?? []), c]);
  }
  const render = (c: (typeof s.classes)[number], depth: number, seen: Set<string>): React.ReactNode => {
    if (seen.has(c.id)) return null;
    const next = new Set(seen).add(c.id);
    return (
      <div key={`${depth}-${c.id}`}>
        <div className="flex items-baseline gap-2 py-0.5" style={{ paddingLeft: depth * 14 }} title={c.comment}>
          <span className="text-muted">{depth ? "└" : "▸"}</span>
          <span className="text-[13px]">{c.label}</span>
          {c.parents.filter((p) => !ids.has(p)).map((p) => <Badge key={p} className="mono">{p}</Badge>)}
        </div>
        {(children.get(c.id) ?? []).map((k) => render(k, depth + 1, next))}
      </div>
    );
  };
  return (
    <div className="max-h-[420px] overflow-auto p-3" data-testid="class-hierarchy">
      <div className="mb-2 text-xs text-muted">{s.classes.length} classes · {s.object_properties.length} object properties · {s.datatype_properties.length} datatype properties · v{s.version}</div>
      {roots.map((r) => render(r, 0, new Set()))}
    </div>
  );
}

function Sparql() {
  const ex = useQ(["onto-examples"], api.ontologyExamples);
  const [query, setQuery] = useState("SELECT ?agent WHERE { ?agent a kym:AIAgent } LIMIT 10");
  const run = useMutation<SparqlResult, Error, string>({ mutationFn: api.sparql });
  const rows = (run.data?.rows ?? []) as unknown[];
  const cell = (r: unknown, v: string, i: number) => String(Array.isArray(r) ? r[i] : (r as Record<string, unknown>)[v] ?? "");
  return (
    <Card>
      <CardHeader title="SPARQL (read-only)" description="SELECT / ASK / CONSTRUCT only; updates are rejected by the server." />
      <CardBody className="space-y-3">
        <Select aria-label="Example queries" value="" onChange={(e) => { const x = ex.data?.find((y) => y.id === e.target.value); if (x) setQuery(x.query); }}>
          <option value="">{ex.error ? "Examples unavailable" : "Load an example query…"}</option>
          {(ex.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
        </Select>
        <Textarea rows={7} className="mono text-[12px]" spellCheck={false} value={query} onChange={(e) => setQuery(e.target.value)} data-testid="sparql-input" />
        <Button variant="accent" size="sm" onClick={() => run.mutate(query)} disabled={run.isPending || !query.trim()} data-testid="sparql-run"><Play size={13} /> Run query</Button>
        {run.error && <Notice tone="bad">{run.error.message}</Notice>}
        {run.data && (
          <div>
            <div className="mb-1 text-xs text-muted">{rows.length} row(s){run.data.truncated ? " (truncated)" : ""} · {run.data.type}</div>
            {rows.length === 0 ? <Empty>No results.</Empty> : (
              <div className="max-h-80 overflow-auto rounded-md border border-border">
                <Table>
                  <THead><TR>{run.data.vars.map((v) => <TH key={v}>?{v}</TH>)}</TR></THead>
                  <TBody>{rows.map((r, i) => <TR key={i}>{run.data!.vars.map((v, j) => <TD key={v} className="mono break-all text-[11px]">{local(cell(r, v, j))}</TD>)}</TR>)}</TBody>
                </Table>
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
