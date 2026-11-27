import { expect, test, type APIRequestContext } from "@playwright/test";

export async function adminToken(request: APIRequestContext): Promise<string> {
  const r = await request.post("/api/session", { data: { user_id: "admin_001" } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).token as string;
}

// Scenario C creates (and leaves ACTIVE) a mandate for the bill payment agent and produces a denied transaction.
export async function ensureActiveMandate(request: APIRequestContext, agentId = "agent_billpay_001") {
  const token = await adminToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const ms = await (await request.get("/api/mandates", { headers })).json();
  const txs = await (await request.get("/api/transactions", { headers })).json();
  if (!ms.some((m: { status: string; agent_id: string }) => m.status === "ACTIVE" && m.agent_id === agentId) || txs.length === 0) {
    const r = await request.post("/api/scenarios/C/run", { headers, data: {} });
    expect(r.ok()).toBeTruthy();
  }
}

export { expect, test };
