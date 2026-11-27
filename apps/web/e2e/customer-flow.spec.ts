import { adminToken, expect, test } from "./helpers";

test.use({ viewport: { width: 1400, height: 1000 } });

test("customer creates, approves and activates a mandate; two phrasings share a digest", async ({ page, request }) => {
  const r = await request.post("/api/session", { data: { user_id: "customer_001" } });
  const token = (await r.json()).token as string;
  await page.addInitScript(([t]) => {
    window.localStorage.setItem("kym.token", t);
    window.localStorage.setItem("kym.user", "customer_001");
  }, [token]);

  await page.goto("/studio");
  await expect(page.getByTestId("compile-status")).toContainText("Compiles", { timeout: 30_000 });

  await page.getByTestId("two-phrasings").click();
  await page.getByRole("button", { name: "Compile both" }).click();
  await expect(page.getByTestId("digest-match")).toHaveText("Digests are IDENTICAL");
  await page.keyboard.press("Escape");

  await page.getByTestId("create-mandate").click();
  const lifecycle = page.getByTestId("lifecycle");
  await expect(lifecycle).toContainText("PENDING CUSTOMER APPROVAL", { timeout: 20_000 });
  const id = (await lifecycle.locator(".mono").first().innerText()).split(" ")[0];

  await page.goto(`/portal?mandate=${id}`);
  const card = page.getByTestId(`mandate-${id}`);
  await card.getByTestId("approve-mandate").click();
  await card.getByTestId("activate-mandate").click();
  await expect(card).toContainText("ACTIVE", { timeout: 20_000 });
  await expect(card.getByTestId("portal-consent")).toContainText("Meridian Bank");
});

test("admin cannot approve in the customer portal", async ({ page, request }) => {
  await adminToken(request);
  await page.goto("/portal");
  await expect(page.getByText("Bank-controlled interface, independent of the agent")).toBeVisible();
  await expect(page.getByTestId("approve-mandate")).toHaveCount(0);
});
