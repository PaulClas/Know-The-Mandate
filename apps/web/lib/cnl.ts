import { ACTION_BY_ID } from "./taxonomy";
import type { Account, Agent, Mandate, Payee } from "./types";
import { minorToMajorString } from "./money";

/** Client-side mirror of the bank's CNL normalizer, used only to preview the consent summary of an existing mandate. */
export function mandateToCnl(m: Mandate, agents: Agent[], accounts: Account[], payees: Payee[]): string {
  const ccy = m.currency;
  const money = (minor: number) => `${minorToMajorString(minor, ccy).replace(/\.?0+$/, (x) => (x.startsWith(".") ? "" : x))} ${ccy}`;
  const agentRef = agents.find((a) => a.id === m.mandatary.agent_id)?.cnl_ref ?? m.mandatary.agent_id;
  const acct = (id: string) => accounts.find((a) => a.accountId === id)?.cnl_ref ?? id;
  const payee = (id: string) => payees.find((p) => p.id === id)?.cnl_ref ?? id;
  const out = [`PURPOSE ${m.purpose}.`, `JURISDICTION ${[...m.jurisdictions].sort().join(", ")}.`, `BUDGET_TIMEZONE ${m.validity.budget_timezone}.`];
  for (const p of m.permissions) {
    const def = ACTION_BY_ID[p.action];
    const res = p.resources.map(acct).sort().join(", ");
    const c = p.constraints;
    if (def?.moneyMoving) {
      const to = [
        ...[...c.allowed_beneficiaries, ...c.allowed_merchants].map(payee),
        ...c.allowed_merchant_categories.map((x) => `category.${x}`),
        ...c.allowed_countries.map((x) => `country.${x.toLowerCase()}`),
        ...c.allowed_destination_accounts.map(acct),
      ].sort();
      out.push(`PERMIT ${agentRef} TO ${def.cnl} FROM ${res} TO ${to.join(", ")} WITH MAX_AMOUNT ${money(c.maximum_amount_minor ?? 0)} PER TRANSACTION.`);
    } else out.push(`PERMIT ${agentRef} TO ${def?.cnl ?? p.action} ON ${res}.`);
  }
  const a = m.aggregate_constraints;
  if (a.maximum_daily_amount_minor) out.push(`LIMIT TOTAL_PAYMENTS TO ${money(a.maximum_daily_amount_minor)} PER CALENDAR_DAY.`);
  if (a.maximum_monthly_amount_minor) out.push(`LIMIT TOTAL_PAYMENTS TO ${money(a.maximum_monthly_amount_minor)} PER CALENDAR_MONTH.`);
  if (a.maximum_transaction_count_monthly) out.push(`LIMIT PAYMENT_COUNT TO ${a.maximum_transaction_count_monthly} PER CALENDAR_MONTH.`);
  const o = m.obligations;
  if (o.human_approval_above_minor !== null) {
    out.push(`REQUIRE ${o.required_approvals === 1 ? "" : o.required_approvals + " "}${o.required_approvals === 1 ? "HUMAN_APPROVAL" : "HUMAN_APPROVALS"} FOR PAYMENTS ABOVE ${money(o.human_approval_above_minor)}.`);
  }
  for (const p of m.prohibitions) if (p !== "mandates.delegate") out.push(`PROHIBIT ${ACTION_BY_ID[p]?.cnl ?? p}.`);
  out.push(m.delegation.allowed ? `ALLOW DELEGATION TO DEPTH ${m.delegation.maximum_depth}.` : "PROHIBIT DELEGATION.");
  out.push(`START AT ${m.validity.not_before}.`, `EXPIRE AT ${m.validity.expires_at}.`);
  return out.join("\n");
}
