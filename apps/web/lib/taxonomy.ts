// Mirror of apps/api/kym/taxonomy.py (action ids, CNL verbs, money-moving flag). Display only; the bank PDP is authoritative.
export interface ActionDef {
  id: string;
  cnl: string;
  label: string;
  group: string;
  moneyMoving: boolean;
}

export const ACTIONS: ActionDef[] = [
  { id: "accounts.read", cnl: "READ_ACCOUNT", label: "Read account", group: "Read", moneyMoving: false },
  { id: "balances.read", cnl: "READ_BALANCE", label: "Read balance", group: "Read", moneyMoving: false },
  { id: "transactions.read", cnl: "READ_TRANSACTIONS", label: "Read transactions", group: "Read", moneyMoving: false },
  { id: "accounts.owner.read", cnl: "READ_ACCOUNT_OWNER", label: "Read account owner", group: "Read", moneyMoving: false },
  { id: "data.transmit_external", cnl: "TRANSMIT_DATA_EXTERNAL", label: "Transmit data externally", group: "Read", moneyMoving: false },
  { id: "analysis.categorize", cnl: "CATEGORIZE_TRANSACTIONS", label: "Categorize transactions", group: "Analyze", moneyMoving: false },
  { id: "analysis.cashflow", cnl: "ANALYZE_CASH_FLOW", label: "Analyze cash flow", group: "Analyze", moneyMoving: false },
  { id: "analysis.budget", cnl: "GENERATE_BUDGET", label: "Generate budget", group: "Analyze", moneyMoving: false },
  { id: "payments.prepare", cnl: "PREPARE_PAYMENT", label: "Prepare payment", group: "Prepare", moneyMoving: false },
  { id: "transfers.prepare", cnl: "PREPARE_TRANSFER", label: "Prepare transfer", group: "Prepare", moneyMoving: false },
  { id: "investments.prepare", cnl: "PREPARE_INVESTMENT_ORDER", label: "Prepare investment order", group: "Prepare", moneyMoving: false },
  { id: "payments.initiate", cnl: "INITIATE_PAYMENT", label: "Initiate payment", group: "Execute", moneyMoving: true },
  { id: "payments.pay_invoice", cnl: "PAY_INVOICE", label: "Pay invoice", group: "Execute", moneyMoving: true },
  { id: "purchases.goods", cnl: "PURCHASE_GOODS", label: "Purchase goods", group: "Execute", moneyMoving: true },
  { id: "transfers.execute", cnl: "EXECUTE_TRANSFER", label: "Internal transfer", group: "Execute", moneyMoving: true },
  { id: "transfers.external", cnl: "EXTERNAL_TRANSFER", label: "External transfer", group: "Execute", moneyMoving: true },
  { id: "investments.trade", cnl: "EXECUTE_INVESTMENT_ORDER", label: "Execute investment order", group: "Execute", moneyMoving: true },
  { id: "mandates.request", cnl: "REQUEST_MANDATE", label: "Request mandate", group: "Authority", moneyMoving: false },
  { id: "mandates.delegate", cnl: "DELEGATE", label: "Delegate authority", group: "Authority", moneyMoving: false },
  { id: "mandates.revoke", cnl: "REVOKE_MANDATE", label: "Revoke mandate", group: "Authority", moneyMoving: false },
];

export const ACTION_BY_ID = Object.fromEntries(ACTIONS.map((a) => [a.id, a]));
export const actionLabel = (id: string) => ACTION_BY_ID[id]?.label ?? id;

export const TOKEN_PROFILES = [
  { id: "valid", label: "Valid token" },
  { id: "wrong_audience", label: "Wrong audience" },
  { id: "expired", label: "Expired" },
  { id: "missing_scope", label: "Missing scope" },
  { id: "wrong_actor", label: "Wrong actor (client binding)" },
  { id: "revoked", label: "Revoked token" },
  { id: "no_dpop", label: "No DPoP proof" },
] as const;
