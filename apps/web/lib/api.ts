import type {
  Account, Agent, FaultCategory, ResponsibilityLevel, ResponsibilityMatrixDef, Approval, Checkpoint, CompileRequest, CompileResult, ControlItem, Customer, DelegationNode, DemoUser,
  EvaluateRequest, EvaluateResult, EvidencePackage, LedgerEvent, LedgerVerifyReport, MandateSummary, MandateView,
  OntologyGraph, OntologySummary, Overview, Payee, ProfileItem, SandboxAgent, SandboxChatRequest, SandboxChatResponse,
  ScenarioMeta, ScenarioRun, SessionResponse, SparqlExample, SparqlResult, StandardItem, Transaction, TransactionDetail,
  TriplesResult,
} from "./types";

const TOKEN_KEY = "kym.token";
const USER_KEY = "kym.user";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
  /** Endpoint not (yet) available in the backend. */
  get pending() {
    return this.status === 404 || this.status === 501 || this.status === 405;
  }
}

export const session = {
  get token(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
  },
  get userId(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(USER_KEY);
  },
  set(token: string, userId: string) {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, userId);
  },
};

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.message === "string") return b.error ? `${b.error}: ${b.message}` : b.message;
    if (typeof b.detail === "string") return b.detail;
    if (b.detail && typeof b.detail === "object") {
      const d = b.detail as Record<string, unknown>;
      if (Array.isArray(d)) return d.map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : JSON.stringify(x))).join("; ");
      if (typeof d.error === "string") return `${d.error}${Array.isArray(d.errors) ? ": " + d.errors.map((e: { message?: string }) => e.message).join("; ") : ""}`;
    }
    if (typeof b.error === "string") return b.error;
  }
  return `HTTP ${status}`;
}

async function loginAs(userId: string): Promise<string> {
  const r = await fetch("/api/session", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ user_id: userId }) });
  if (!r.ok) throw new ApiError(r.status, "login failed", null);
  const j = (await r.json()) as SessionResponse;
  session.set(j.token, userId);
  return j.token;
}

async function request<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  const tok = session.token;
  if (tok) headers.authorization = `Bearer ${tok}`;
  let r: Response;
  try {
    r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    throw new ApiError(0, `Network error: ${(e as Error).message}. Is the API running on :8000?`, null);
  }
  if (r.status === 401 && retry && session.userId) {
    await loginAs(session.userId);
    return request<T>(method, path, body, false);
  }
  const text = await r.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }
  if (!r.ok) throw new ApiError(r.status, errorMessage(parsed, r.status), parsed);
  return parsed as T;
}

const get = <T>(p: string) => request<T>("GET", p);
const post = <T>(p: string, b: unknown = {}) => request<T>("POST", p, b);
const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return p.length ? "?" + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&") : "";
};
const list = <T>(x: unknown, ...keys: string[]): T[] => {
  if (Array.isArray(x)) return x as T[];
  if (x && typeof x === "object") for (const k of keys) if (Array.isArray((x as Record<string, unknown>)[k])) return (x as Record<string, T[]>)[k];
  return [];
};

export const api = {
  login: loginAs,
  users: () => fetch("/api/session/users").then((r) => r.json() as Promise<DemoUser[]>),
  me: () => get<DemoUser>("/api/me"),
  overview: () => get<Overview>("/api/overview"),
  metrics: () => get<Record<string, unknown>>("/api/metrics"),

  agents: () => get<Agent[]>("/api/agents"),
  agent: (id: string) => get<Agent>(`/api/agents/${id}`),
  registerAgent: (body: unknown) => post<Agent>("/api/agents", body),
  agentAction: (id: string, action: "verify" | "suspend" | "restrict" | "revoke", reason = "operator action") =>
    post<Agent>(`/api/agents/${id}/${action}`, action === "verify" ? {} : { reason }),

  customers: () => get<Customer[]>("/api/customers"),
  accounts: () => get<Account[]>("/api/accounts"),
  payees: () => get<Payee[]>("/api/payees"),

  compile: (b: CompileRequest) => post<CompileResult>("/api/mandates/compile", b),
  createMandate: (b: { principal_id: string; cnl: string }) => post<MandateView>("/api/mandates", b),
  mandates: (q: { principal_id?: string; agent_id?: string } = {}) => get<MandateSummary[]>(`/api/mandates${qs(q)}`),
  mandate: (id: string, version?: number) => get<MandateView>(`/api/mandates/${id}${qs({ version })}`),
  mandateSemantic: (id: string, version?: number) =>
    get<{ json_ld: unknown; turtle: string; shacl: unknown }>(`/api/mandates/${id}/semantic${qs({ version })}`),
  approveMandate: (id: string, digest: string, version: number, language: string) =>
    post<MandateView>(`/api/mandates/${id}/approve`, { digest, version, language }),
  activateMandate: (id: string, version?: number) => post<MandateView>(`/api/mandates/${id}/activate${qs({ version })}`),
  suspendMandate: (id: string, reason = "suspended by customer") => post<MandateView>(`/api/mandates/${id}/suspend`, { reason }),
  resumeMandate: (id: string) => post<MandateView>(`/api/mandates/${id}/resume`),
  revokeMandate: (id: string, reason = "revoked by customer") => post<MandateView>(`/api/mandates/${id}/revoke`, { reason }),
  amendMandate: (id: string, cnl: string) => post<MandateView>(`/api/mandates/${id}/amend`, { cnl }),
  delegationGraph: (principal_id?: string) => get<{ nodes: DelegationNode[]; edges: { source: string; target: string }[] }>(`/api/delegation/graph${qs({ principal_id })}`),

  approvals: () => get<Approval[]>("/api/approvals"),
  decideApproval: (id: string, d: "approve" | "reject") => post<Approval>(`/api/approvals/${id}/${d}`),

  evaluate: (b: EvaluateRequest) => post<EvaluateResult>("/api/authorization/evaluate", b),

  ledgerEvents: (q: { q?: string; event_type?: string; limit?: number; offset?: number; correlation_id?: string; transaction_id?: string; mandate_id?: string }) =>
    get<{ events: LedgerEvent[]; total: number }>(`/api/ledger/events${qs(q)}`),
  ledgerEvent: (id: string) => get<LedgerEvent>(`/api/ledger/events/${id}`),
  ledgerVerify: () => post<LedgerVerifyReport>("/api/ledger/verify"),
  checkpoints: () => get<{ checkpoints: Checkpoint[]; public_keys: Record<string, Record<string, string>> }>("/api/ledger/checkpoints"),

  transactions: (status?: string) => get<Transaction[]>(`/api/transactions${qs({ status })}`),
  transaction: (id: string) => get<TransactionDetail>(`/api/transactions/${id}`),
  evidence: (id: string) => get<EvidencePackage>(`/api/transactions/${id}/evidence`),
  openDispute: (id: string, reason: string) => post<Record<string, unknown>>(`/api/transactions/${id}/dispute`, { reason }),
  responsibilityMatrix: () => get<ResponsibilityMatrixDef>("/api/responsibility/matrix"),
  responsibilityFaults: () => get<{ faults: FaultCategory[]; levels: ResponsibilityLevel[]; disclaimer: string }>("/api/responsibility/faults"),

  ontology: () => get<OntologySummary>("/api/ontology"),
  ontologyGraph: (mode: string, categories: string[]) => get<OntologyGraph>(`/api/ontology/graph${qs({ mode, categories: categories.join(",") })}`),
  ontologyTriples: (node: string) => get<TriplesResult>(`/api/ontology/triples${qs({ node })}`),
  ontologyExamples: () => get<unknown>("/api/ontology/examples").then((x) => list<SparqlExample>(x, "examples")),
  sparql: (query: string) => post<SparqlResult>("/api/ontology/query", { query }),

  sandboxAgents: () => get<unknown>("/api/sandbox/agents").then((x) => list<SandboxAgent>(x, "agents")),
  sandboxChat: (b: SandboxChatRequest) => post<SandboxChatResponse>("/api/sandbox/chat", b),

  scenarios: () => get<unknown>("/api/scenarios").then((x) => list<ScenarioMeta>(x, "scenarios")),
  runScenario: (id: string) => post<ScenarioRun>(`/api/scenarios/${id}/run`),
  redteamRun: () => post<RedteamReport>("/api/redteam/run"),
  resetDemo: () => post<Record<string, unknown>>("/api/demo/reset"),

  standards: () => get<unknown>("/api/standards").then((x) => list<StandardItem>(x, "standards", "items")),
  complianceProfiles: () => get<unknown>("/api/compliance/profiles").then((x) => list<ProfileItem>(x, "profiles", "items")),
  complianceControls: (jurisdiction: string) =>
    get<unknown>(`/api/compliance/controls${qs({ jurisdiction })}`).then((x) => list<ControlItem>(x, "controls", "items")),
};

export type Tier = { blocked: boolean | null; detail: string };
export type RedteamRow = { id: string; title: string; category: string; refs: string[]; expected_gap: boolean; results: Record<string, Tier>; note: string | null; error: string | null; ms: number };
export type RedteamReport = { generated_at: string; attacks: RedteamRow[]; method: string; summary: { scope_only: { blocked: number; applicable: number }; rar_static: { blocked: number; applicable: number }; kym: { blocked: number; applicable: number }; kym_not_blocked: string[]; errors: string[]; total_attacks: number } };

export async function downloadEvidence(txId: string) {
  const r = await fetch(`/api/transactions/${txId}/evidence/download`, { headers: session.token ? { authorization: `Bearer ${session.token}` } : {} });
  if (!r.ok) throw new ApiError(r.status, errorMessage(await r.json().catch(() => null), r.status), null);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `kym-evidence-${txId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
