import { ensureActiveMandate, expect, test } from "./helpers";

test.beforeAll(async ({ request }) => {
  await ensureActiveMandate(request);
});

test("sandbox shows the observable step chain for a prompt", async ({ page }) => {
  await page.goto("/sandbox");
  await page.getByTestId("sandbox-agent-agent_billpay_001").click();
  await page.getByTestId("sandbox-input").fill("Pay CAD 300 to Hydro-Québec");
  await page.getByRole("button", { name: "Send" }).click();
  const stepper = page.getByTestId("stepper");
  await expect(stepper).toBeVisible({ timeout: 30_000 });
  for (const kind of ["tool_call", "oauth", "mandate", "risk", "decision", "execution", "ledger"]) {
    await expect(stepper.locator(`[data-kind="${kind}"]`).first()).toBeVisible();
  }
  await expect(page.getByTestId("agent-reply")).toBeVisible();
});

test("ledger lists events and verifies integrity", async ({ page }) => {
  await page.goto("/ledger");
  await expect(page.getByTestId("ledger-row").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("verify-ledger").click();
  await expect(page.getByTestId("verify-report")).toContainText("VERIFIED");
  await page.getByTestId("ledger-row").first().click();
  await expect(page.getByText("Payload", { exact: false }).first()).toBeVisible();
});

test("ontology graph renders nodes and a node click shows triples", async ({ page }) => {
  await page.goto("/ontology");
  await expect(page.locator(".react-flow__node").first()).toBeVisible({ timeout: 20_000 });
  await page.locator(".react-flow__node").first().click();
  await expect(page.getByText(/Triples \(\d+\)/)).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("sparql-run").click();
  await expect(page.getByText(/row\(s\)/)).toBeVisible({ timeout: 15_000 });
});

test("standards page shows status chips and regulatory controls with unverified handling", async ({ page }) => {
  await page.goto("/standards");
  await expect(page.getByText("EXPERIMENTAL KYM EXTENSION").first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("tab", { name: "Regulatory profiles" }).click();
  await page.getByRole("tab", { name: "Quebec" }).click();
  await expect(page.getByText("QC-CCQ-01")).toBeVisible({ timeout: 20_000 });
});

test("transactions page lists attempted actions and opens a trace", async ({ page }) => {
  await page.goto("/transactions");
  await expect(page.getByTestId("tx-row").first()).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("tx-row").first().click();
  await expect(page.getByTestId("trace")).toBeVisible({ timeout: 15_000 });
});
