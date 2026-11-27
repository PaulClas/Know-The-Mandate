import { ensureActiveMandate, expect, test } from "./helpers";

test.beforeAll(async ({ request }) => {
  await ensureActiveMandate(request);
});

test("valid token but invalid mandate is DENIED; a valid payment is ALLOWED", async ({ page }) => {
  await page.goto("/playground");
  const central = page.getByTestId("preset-token_ok_mandate_bad");
  await expect(central).toBeEnabled({ timeout: 20_000 });
  await central.click();
  const pill = page.getByTestId("decision-pill");
  await expect(pill).toHaveAttribute("data-decision", "DENY");
  await expect(page.getByTestId("result")).toContainText("BENEFICIARY_NOT_AUTHORIZED");
  await expect(page.getByText("Token checks passed — the denial comes from the mandate")).toBeVisible();

  await page.getByTestId("preset-valid_payment").click();
  await expect(pill).toHaveAttribute("data-decision", "ALLOW");

  await page.getByTestId("preset-expired").click();
  await expect(pill).toHaveAttribute("data-decision", "DENY");
});
