"use client";

import { ExternalLink, FlaskConical } from "lucide-react";
import { useMemo, useState } from "react";
import { Async, Empty, Notice, PageHeader } from "@/components/common";
import { useQ } from "@/components/providers";
import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { ControlItem, ProfileItem, StandardItem } from "@/lib/types";
import { humanize } from "@/lib/utils";

const STATUS_TONE: Record<string, Tone> = { implemented: "ok", simulated: "info", mapped: "neutral", proposed: "warn", not_implemented: "bad" };
const SOURCE_LABEL: Record<string, { label: string; tone: Tone }> = {
  enacted_law: { label: "Enacted law", tone: "info" },
  operative_requirement: { label: "Operative requirement", tone: "info" },
  proposed_regulation: { label: "Proposed", tone: "warn" },
  supervisory_guidance: { label: "Supervisory guidance", tone: "neutral" },
  industry_standard: { label: "Industry standard", tone: "neutral" },
  kym_proposal: { label: "KYM proposal", tone: "warn" },
};
const JURISDICTIONS = [
  { id: "CA", label: "Canada" },
  { id: "CA-QC", label: "Quebec" },
  { id: "US", label: "United States" },
];

export default function StandardsPage() {
  return (
    <>
      <PageHeader title="Standards & regulatory mapping" description="How KYM relates to published standards and to Canadian, Québec and U.S. requirements — as a mapping exercise, not a compliance claim." />
      <Notice tone="warn" className="mb-4" title="Nothing here is legal advice or a compliance claim">
        KYM is an experimental, synthetic demo. Mappings are illustrative, may be incomplete or out of date, and have not been reviewed by counsel. KYM-authored artifacts are proposals, not standards.
      </Notice>
      <Tabs defaultValue="standards">
        <TabsList>
          <TabsTrigger value="standards">Standards</TabsTrigger>
          <TabsTrigger value="regulatory">Regulatory profiles</TabsTrigger>
        </TabsList>
        <TabsContent value="standards" className="pt-4"><Standards /></TabsContent>
        <TabsContent value="regulatory" className="pt-4"><Regulatory /></TabsContent>
      </Tabs>
    </>
  );
}

function StatusChip({ s }: { s: string }) {
  return <Badge tone={STATUS_TONE[s] ?? "neutral"}>{s.replace(/_/g, " ")}</Badge>;
}

function Standards() {
  const q = useQ(["standards"], api.standards);
  const [status, setStatus] = useState("");
  const [cat, setCat] = useState("");
  return (
    <Async q={q} what="standards">
      {(list: StandardItem[]) => {
        const cats = [...new Set(list.map((x) => x.category ?? "other"))].sort();
        const counts = list.reduce<Record<string, number>>((a, x) => ((a[x.kym_status] = (a[x.kym_status] ?? 0) + 1), a), {});
        const rows = list.filter((x) => (!status || x.kym_status === status) && (!cat || (x.category ?? "other") === cat));
        return (
          <Card>
            <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
              {Object.entries(counts).map(([k, v]) => (
                <button key={k} onClick={() => setStatus(status === k ? "" : k)} className="cursor-pointer" aria-pressed={status === k}>
                  <Badge tone={STATUS_TONE[k] ?? "neutral"} className={status === k ? "ring-2 ring-accent" : ""}>{v} {k.replace(/_/g, " ")}</Badge>
                </button>
              ))}
              <Select className="ml-auto w-auto" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category">
                <option value="">All categories</option>
                {cats.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
              </Select>
            </div>
            {rows.length === 0 ? <Empty>No standards match.</Empty> : (
              <Table>
                <THead><TR><TH>Standard</TH><TH>Body</TH><TH>Category</TH><TH>KYM status</TH><TH>Notes</TH></TR></THead>
                <TBody>
                  {rows.map((s) => {
                    const ext = (s.body ?? "").toLowerCase().includes("kym") || s.id.startsWith("kym-");
                    return (
                      <TR key={s.id}>
                        <TD>
                          <div className="flex items-center gap-1.5 font-medium">
                            {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">{s.name}</a> : s.name}
                            {s.url && <ExternalLink size={11} className="text-muted" />}
                          </div>
                          <div className="mono text-[11px] text-muted">{s.id}</div>
                          {ext && <Badge tone="warn" className="mt-1"><FlaskConical size={10} /> EXPERIMENTAL KYM EXTENSION — not a standard</Badge>}
                        </TD>
                        <TD className="text-xs">{s.body}</TD>
                        <TD className="text-xs">{humanize(s.category)}</TD>
                        <TD><StatusChip s={s.kym_status} /></TD>
                        <TD className="max-w-md text-xs text-muted">{s.notes}</TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>
        );
      }}
    </Async>
  );
}

function Regulatory() {
  const [j, setJ] = useState("CA");
  const profiles = useQ(["compliance-profiles"], api.complianceProfiles);
  const controls = useQ(["compliance-controls", j], () => api.complianceControls(j));
  const profile = useMemo(() => profiles.data?.find((p: ProfileItem) => p.jurisdiction === j), [profiles.data, j]);
  return (
    <div className="space-y-4">
      <Tabs value={j} onValueChange={setJ}>
        <TabsList>{JURISDICTIONS.map((x) => <TabsTrigger key={x.id} value={x.id}>{x.label}</TabsTrigger>)}</TabsList>
      </Tabs>
      {profile && (
        <Card>
          <CardHeader title={profile.name} description={`Consent languages: ${profile.consent_languages.join(", ").toUpperCase()}`} />
          <CardBody className="space-y-2 text-[13px]">
            <p>{profile.summary}</p>
            <ul className="list-disc space-y-1 pl-5 text-muted">{profile.key_distinctions.map((k) => <li key={k}>{k}</li>)}</ul>
          </CardBody>
        </Card>
      )}
      <Async q={controls} what="controls">
        {(list: ControlItem[]) => (
          <Card>
            <CardHeader title={`Controls (${list.length})`} description="Source-by-source mapping with verification date and limitations" />
            {list.length === 0 ? <Empty>No controls for this jurisdiction.</Empty> : (
              <Table>
                <THead><TR><TH>Source</TH><TH>Type</TH><TH>Provision</TH><TH>Status</TH><TH>Verified</TH><TH>KYM status</TH><TH>Limitations</TH></TR></THead>
                <TBody>
                  {list.map((c) => {
                    const st = SOURCE_LABEL[c.source_type] ?? { label: humanize(c.source_type), tone: "neutral" as Tone };
                    return (
                      <TR key={c.id}>
                        <TD className="min-w-[200px]">
                          <div className="font-medium">{c.source_url ? <a className="hover:underline" href={c.source_url} target="_blank" rel="noreferrer">{c.source}</a> : c.source}</div>
                          <div className="mono text-[11px] text-muted">{c.id}</div>
                        </TD>
                        <TD><Badge tone={st.tone}>{st.label}</Badge></TD>
                        <TD className="min-w-[180px] text-xs">{c.provision}</TD>
                        <TD className="min-w-[200px] text-xs text-muted">{c.current_status}</TD>
                        <TD className="whitespace-nowrap text-xs">{c.date_verified ?? <Badge tone="warn">unverified</Badge>}</TD>
                        <TD>{c.implementation_status ? <StatusChip s={c.implementation_status} /> : "—"}</TD>
                        <TD className="min-w-[220px] text-xs text-muted">{c.limitations}</TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>
        )}
      </Async>
      <p className="text-xs text-muted">Controls describe what a regime appears to require and how KYM might evidence it. They are not an assertion that Meridian Bank or KYM is compliant.</p>
    </div>
  );
}
