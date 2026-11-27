// TypeScript mirror of the backend data model (apps/api/kym/schemas.py) and API responses.
// Money is always integer minor units (e.g. 8500 = CAD 85.00). Never use floats for arithmetic.

export type PrincipalType = "individual" | "business";

export interface Principal {
  id: string;
  type: PrincipalType;
}
export interface Mandatary {
  agent_id: string;
  operator_id: string;
  client_id: string;
}
export interface Constraints {
  currency: string | null;
  maximum_amount_minor: number | null;
  allowed_beneficiaries: string[];
  allowed_merchants: string[];
  allowed_destination_accounts: string[];
  allowed_merchant_categories: string[];
  allowed_countries: string[];
}
export interface Permission {
  action: string;
  resources: string[];
  constraints: Constraints;
}
export interface AggregateConstraints {
  maximum_daily_amount_minor: number | null;
  maximum_monthly_amount_minor: number | null;
  maximum_transaction_count_monthly: number | null;
}
export interface Obligations {
  human_approval_above_minor: number | null;
  required_approvals: number;
  notify_customer: boolean;
}
export interface DelegationRule {
  allowed: boolean;
  maximum_depth: number;
}
export interface Lineage {
  parent_mandate_id: string;
  parent_mandate_version: number;
  depth: number;
}
export interface Validity {
  not_before: string;
  expires_at: string;
  budget_timezone: string;
}
export interface Mandate {
  mandate_id: string;
  schema_version: string;
  ontology_version: string;
  version: number;
  principal: Principal;
  mandatary: Mandatary;
  purpose: string;
  currency: string;
  permissions: Permission[];
  prohibitions: string[];
  aggregate_constraints: AggregateConstraints;
  obligations: Obligations;
  delegation: DelegationRule;
  validity: Validity;
  jurisdictions: string[];
  policy_version: string;
  lineage: Lineage | null;
}

export type MandateStatus =
  | "DRAFT"
  | "PENDING_VALIDATION"
  | "VALIDATED"
  | "PENDING_CUSTOMER_APPROVAL"
  | "ACTIVE"
  | "SUSPENDED"
  | "EXPIRED"
  | "REVOKED"
  | "SUPERSEDED"
  | "REJECTED";

export interface MandateSummary {
  mandate_id: string;
  version: number;
  status: MandateStatus;
  principal_id: string;
  agent_id: string;
  purpose: string;
  digest: string;
  created_at: string;
  expires_at: string;
  parent_mandate_id: string | null;
  currency: string;
}

export interface StateHistoryItem {
  from: string;
  to: string;
  at: string;
  actor: string;
  reason: string;
}

export interface MandateView {
  mandate_id: string;
  version: number;
  status: MandateStatus;
  digest: string;
  content: Mandate;
  created_at: string;
  created_by: string;
  state_history: StateHistoryItem[];
  validation: ValidationReport | null;
  versions: { version: number; status: MandateStatus }[];
  consent: { id: string; receipt: Record<string, unknown>; signature: string; key_id: string } | null;
  children: { child_id: string; child_version: number }[];
  parent: Lineage | null;
}

// ---- session / users
export type Role = "admin" | "investigator" | "customer";
export interface DemoUser {
  id: string;
  role: Role;
  name: string;
}
export interface SessionResponse {
  token: string;
  user: DemoUser;
  warning?: string;
}

// ---- agents
export type AgentStatus =
  | "UNREGISTERED"
  | "PENDING_VERIFICATION"
  | "VERIFIED"
  | "RESTRICTED"
  | "SUSPENDED"
  | "REVOKED";

export interface AgentDeclared {
  display_name: string;
  category: string;
  operating_organization: string;
  operator_id: string;
  responsible_party: string;
  developer: string;
  deployment_environment: string;
  model_provider: string;
  model_id: string;
  software_version: string;
  build_digest: string;
  supported_tools: string[];
  requested_capabilities: string[];
  declared_autonomy_level: string;
}
export interface Agent {
  id: string;
  cnl_ref: string | null;
  display_name: string;
  status: AgentStatus;
  client_id: string;
  registered_at: string;
  declared: AgentDeclared;
  verified: {
    checks: { check: string; ok: boolean }[];
    verified_at: string;
    verified_by: string;
    key_thumbprint: string;
    build_digest: string;
    assurance: string;
  } | null;
  public_key: { kty: string; crv: string; x: string; y: string; thumbprint: string } | null;
  attestation: {
    statement: { agent_id: string; build_digest: string; key_thumbprint: string; issued_at: string; issuer: string };
    key_id: string;
    assurance: string;
  } | null;
  security_posture: Record<string, boolean>;
  incidents: { id?: string; at?: string; severity?: string; summary?: string; description?: string }[];
  stats: { payments_executed: number; payments_denied: number; mandates_executed: number };
  trust: {
    score: number;
    components: Record<string, number>;
    weights: Record<string, number>;
    formula: string;
    note: string;
  };
  mandates?: MandateSummary[];
}

// ---- bank data
export interface Account {
  accountId: string;
  nickname: string;
  accountType: string;
  currency: string;
  status: string;
  currentBalanceMinor: number;
  reservedMinor: number;
  availableBalanceMinor: number;
  owner_id: string;
  cnl_ref: string;
}
export interface Customer {
  id: string;
  type: PrincipalType;
  name: string;
  jurisdiction: string;
  kyc_status: string;
  kyc_date: string;
  kyc_evidence_ref: string;
  risk_class: string;
  restrictions: string[];
  cnl_ref: string;
  preferred_language?: string;
  representatives: { person_id: string; role: string; can_sign: boolean; account_ids: string[] }[];
}
export interface Payee {
  id: string;
  kind: "beneficiary" | "merchant";
  name: string;
  country: string;
  category: string;
  cnl_ref: string;
}

// ---- overview / ledger
export interface LedgerEvent {
  event_id: string;
  sequence: number;
  event_type: string;
  timestamp: string;
  actor_id: string;
  actor_type: string;
  principal_id: string | null;
  agent_id: string | null;
  mandate_id: string | null;
  mandate_version: number | null;
  transaction_id: string | null;
  correlation_id: string;
  policy_version: string | null;
  ontology_version: string | null;
  payload_digest: string;
  previous_hash: string;
  signer_id: string;
  signing_key_id: string;
  event_hash: string;
  signature: string;
  payload?: Record<string, unknown> | null;
  payload_redacted?: boolean;
}
export interface LedgerVerifyReport {
  ok: boolean;
  events_checked: number;
  checkpoints_checked: number;
  head_hash: string;
  problems: unknown[];
  checks: string[];
  verified_at: string;
  assumptions: string[];
}
export interface Checkpoint {
  checkpoint_id: string;
  sequence: number;
  head_hash: string;
  event_count: number;
  created_at: string;
  ontology_version: string;
  signature: string;
  key_id: string;
  witness_signature?: string;
  witness_key_id?: string;
}
export interface Overview {
  registered_agents: number;
  verified_agents: number;
  active_mandates: number;
  revoked_mandates: number;
  pending_customer_approvals: number;
  pending_transaction_approvals: number;
  total_authorized_payments_minor: number;
  executed_payments: number;
  denied_actions: number;
  decision_distribution: Record<string, number>;
  ledger: { ok: boolean; events: number; head_hash: string; checkpoints: number; problems: unknown[] };
  recent_events: LedgerEvent[];
  trial_balance: Record<string, unknown>;
  disclaimer: string;
}

// ---- decisions
export type Decision = "ALLOW" | "DENY" | "REQUIRE_HUMAN_APPROVAL" | "REFER_TO_RISK_REVIEW";
export type TraceOutcome = "PASS" | "FAIL" | "SKIP" | "INFO" | "REFER" | "REQUIRE_APPROVAL";
export interface TraceItem {
  id: string;
  name: string;
  outcome: TraceOutcome;
  detail: string;
  reason_code: string | null;
  rule: string | null;
}
export interface RiskAssessment {
  score: number;
  level: string;
  signals: { id: string; triggered: boolean; points: number; detail: string }[];
  [k: string]: unknown;
}
export interface EvaluateResult {
  decision: Decision;
  reason_codes: string[];
  trace: TraceItem[];
  risk?: RiskAssessment | null;
  [k: string]: unknown;
}
export type TokenProfile =
  | "valid"
  | "wrong_audience"
  | "expired"
  | "missing_scope"
  | "wrong_actor"
  | "revoked"
  | "no_dpop";

export interface EvaluateRequest {
  agent_id: string;
  mandate_id: string;
  version?: number | null;
  action: string;
  account_id: string;
  beneficiary_id?: string | null;
  merchant_id?: string | null;
  to_account_id?: string | null;
  amount_minor?: number | null;
  currency?: string | null;
  purpose?: string | null;
  token_profile: TokenProfile;
  approval_id?: string | null;
}

// ---- transactions
export type TxStatus =
  | "EXECUTED"
  | "DENIED"
  | "PENDING_APPROVAL"
  | "RISK_REVIEW"
  | "CANCELLED"
  | "COMPLETED"
  | "AUTHORIZED"
  | "FAILED"
  | "REVIEW_CLEARED"
  | string;
export interface Transaction {
  id: string;
  kind: string;
  action: string;
  status: TxStatus;
  principal_id: string;
  agent_id: string;
  mandate_id: string | null;
  mandate_version: number | null;
  account_id: string | null;
  payee_id: string | null;
  amount_minor: number | null;
  currency: string | null;
  decision_id: string | null;
  outcome: Decision | null;
  reason_codes: string[];
  approval_id: string | null;
  correlation_id: string;
  created_at: string;
  updated_at: string;
  failure_reason: string | null;
  risk: { score: number | null; level: string | null } | null;
}
export interface TransactionDetail extends Transaction {
  operation: Record<string, unknown> | null;
  decision: {
    id: string;
    decision: Decision;
    reason_codes: string[];
    trace: TraceItem[];
    policy_version: string;
    inputs_digest: string;
  } | null;
}

// ---- approvals
export interface Approval {
  id: string;
  tx_id: string;
  status: string;
  op_hash: string;
  mandate_id: string;
  mandate_version: number;
  principal_id: string;
  required_approvals: number;
  eligible_approvers: string[];
  grants: Record<string, unknown>[];
  reason: string;
  created_at: string;
  expires_at: string;
  display: {
    requesting_agent: string;
    agent_id: string;
    agent_operator: string | null;
    account: string;
    action: string;
    amount_minor: number | null;
    currency: string | null;
    beneficiary: string | null;
    mandate: string;
    purpose: string;
  };
  consumed_at: string | null;
  binding: string;
  assurance: string;
}

// ---- mandate studio compile output
export interface CompileError {
  code: string;
  message: string;
  line?: number;
  column?: number;
  context?: string;
  expected?: string[];
  [k: string]: unknown;
}
export interface Ambiguity {
  id: string;
  kind: string;
  phrase: string;
  question: string;
  hint: string;
  resolved: boolean;
}
export interface Check {
  id: string;
  ok: boolean;
  detail: string;
}
export interface ValidationReport {
  ok: boolean;
  schema: { ok: boolean; errors: unknown[] };
  semantic: { ok: boolean; checks: Check[] };
  bank_policy: { ok: boolean; checks: Check[] };
  shacl: ShaclReport;
}
export interface ShaclReport {
  conforms: boolean;
  results: unknown[];
  report_text: string;
}
export interface EffectivePermission {
  action: string;
  resources: string[];
  effective: boolean;
  limits: string[];
  narrowed_by: string[];
}
export interface CompileResult {
  original_intent: string | null;
  cnl_version: string;
  ambiguities: Ambiguity[];
  required_resolutions: { id: string; question: string }[];
  proposed_cnl: string | null;
  ok: boolean;
  errors: CompileError[];
  reference_time: string;
  ast?: Record<string, unknown>[];
  cnl_input?: string;
  normalized_cnl?: string;
  defaults_applied?: string[];
  mandate?: Mandate;
  canonical_digest?: string;
  json_ld?: Record<string, unknown>;
  turtle?: string;
  shacl?: ShaclReport;
  validation?: ValidationReport;
  oauth?: {
    scopes: string[];
    authorization_details: Record<string, unknown>[];
    kym_token_claims: Record<string, unknown>;
    scope_gaps: { dimension: string; carried_by: string }[];
  };
  runtime_policy?: Record<string, unknown>;
  consent_summary?: { en: string; fr: string };
  effective_permissions?: EffectivePermission[];
}
export interface CompileRequest {
  principal_id: string;
  instruction?: string | null;
  cnl?: string | null;
  resolutions?: Record<string, unknown> | null;
  reference_time?: string | null;
}

export interface DelegationNode {
  id: string;
  mandate_id: string;
  version: number;
  status: MandateStatus;
  agent_id: string;
  principal_id: string;
  depth: number;
  delegation: DelegationRule;
  currency: string;
  expires_at: string;
  max_amount_minor: number;
  monthly_minor: number | null;
  actions: string[];
  beneficiaries: string[];
}

// ---- ontology (pending backend)
export interface OntologySummary {
  version: string;
  namespace: string;
  experimental: boolean;
  classes: { id: string; label: string; comment?: string; parents: string[] }[];
  object_properties: { id: string; label: string; domain?: string; range?: string }[];
  datatype_properties: { id: string; label: string; domain?: string; range?: string }[];
}
export type OntologyCategory =
  | "customer"
  | "agent"
  | "mandate"
  | "resource"
  | "permission"
  | "constraint"
  | "evidence"
  | "delegation"
  | "responsibility";
export interface GraphNode {
  id: string;
  label: string;
  category: OntologyCategory | string;
  type?: string;
}
export interface GraphEdge {
  source: string;
  target: string;
  label?: string;
}
export interface OntologyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
export interface TriplesResult {
  node?: string;
  triples: [string, string, string][];
  json_ld: unknown;
}
export interface SparqlExample {
  id: string;
  title: string;
  query: string;
}
export interface SparqlResult {
  type: string;
  vars: string[];
  rows: Record<string, unknown>[] | unknown[][];
  truncated?: boolean;
}

// ---- sandbox (pending backend)
export interface SandboxAgent {
  id: string;
  name: string;
  description: string;
  sample_prompts: string[];
  mandate_id?: string | null;
  status?: string;
  active_mandates?: MandateSummary[];
}
export type SandboxStepKind =
  | "instruction"
  | "tool_call"
  | "oauth"
  | "mandate"
  | "risk"
  | "decision"
  | "execution"
  | "ledger";
export interface SandboxStep {
  index: number;
  kind: SandboxStepKind;
  title: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  status?: string;
  decision?: Decision | string;
  reason_codes?: string[];
  detail?: string;
  ledger_event_ids?: string[];
  checks?: { name: string; outcome: string; detail: string }[];
}
export interface SandboxChatRequest {
  agent_id: string;
  message: string;
  customer_id?: string;
  mandate_id?: string;
  untrusted_document?: string;
}
export interface SandboxChatResponse {
  reply: string;
  steps: SandboxStep[];
}

// ---- scenarios (pending backend)
export interface ScenarioMeta {
  id: string;
  title: string;
  group?: string;
  description: string;
  expected: string;
  featured?: boolean;
}
export interface ScenarioStep {
  title: string;
  detail?: string;
  request?: unknown;
  status?: string | number;
  decision?: string;
  reason_codes?: string[];
  ok: boolean;
  note?: string;
  transaction_id?: string;
}
export interface ScenarioRun {
  id: string;
  title: string;
  passed: boolean;
  expected: string;
  summary: string;
  steps: ScenarioStep[];
  correlation_ids: string[];
  transaction_ids?: string[];
  learn?: string;
}

// ---- evidence / disputes (pending backend)
export interface TimelineItem {
  at: string;
  seq?: number;
  title: string;
  detail?: string;
  actor?: string;
  event_type?: string;
  event_id?: string;
}
export interface Attribution {
  step: string;
  question: string;
  party: string;
  evidence: string;
  system_control: string;
  level: string;
}
export interface ResponsibilityLevel {
  id: string;
  name: string;
  description: string;
}
export interface FaultCategory {
  id: string;
  title: string;
  factual: string;
  contractual: string;
  potential_legal: string;
  evidence: string[];
}
export interface ResponsibilityMatrixDef {
  roles: { id: string; name: string; description: string }[];
  steps: { id: string; question: string; default_role: string }[];
  levels: ResponsibilityLevel[];
  faults: FaultCategory[];
  disclaimer: string;
}
export interface EvidencePackage {
  package_version: string;
  generated_at: string;
  transaction: Transaction & { dispute?: Record<string, unknown> | null };
  customer?: Record<string, unknown>;
  agent?: Record<string, unknown> & { declared_metadata?: Record<string, unknown>; verified_facts?: Record<string, unknown> };
  operator?: Record<string, unknown>;
  mandate?: { content?: Mandate; digest?: string; json_ld?: unknown; status_now?: string; state_history?: StateHistoryItem[] } & Record<string, unknown>;
  consent?: { receipt?: Record<string, unknown>; signature?: string; key_id?: string; signature_valid?: boolean } | null;
  oauth_grant?: Record<string, unknown> | null;
  operation?: { operation?: Record<string, unknown>; op_hash?: string } | null;
  policy?: { version?: string; decision_id?: string; decision?: string; reason_codes?: string[]; trace?: TraceItem[]; replay_matches?: boolean } & Record<string, unknown>;
  risk?: RiskAssessment | null;
  approvals?: Record<string, unknown>[] | null;
  execution?: { status?: string; postings?: unknown[]; balanced?: boolean } & Record<string, unknown>;
  subsequent_events?: LedgerEvent[];
  ledger_events?: LedgerEvent[];
  verification?: { ok?: boolean; events_verified?: number; events_in_package?: number; problems?: unknown[]; verified_at?: string; assumptions?: string[] } | null;
  timeline?: TimelineItem[];
  limitations?: string[];
  responsibility?: {
    attribution: Attribution[];
    can_establish: string[];
    cannot_establish: string[];
    levels: ResponsibilityLevel[];
    faults: FaultCategory[];
    disclaimer: string;
  };
}

// ---- compliance (pending backend)
export interface StandardItem {
  id: string;
  name: string;
  body?: string;
  url?: string;
  category?: string;
  kym_status: "implemented" | "simulated" | "mapped" | "proposed" | "not_implemented" | string;
  notes?: string;
  experimental?: boolean;
}
export interface ControlItem {
  id: string;
  jurisdiction: string;
  source: string;
  source_type: string;
  source_url?: string;
  provision: string;
  source_version?: string;
  date_verified: string | null;
  current_status: string;
  applicability?: string;
  related_kym_capability?: string;
  implementation_status?: string;
  limitations?: string;
  evidence_required?: string[];
}
export interface ProfileItem {
  jurisdiction: string;
  name: string;
  summary: string;
  key_distinctions: string[];
  consent_languages: string[];
}
