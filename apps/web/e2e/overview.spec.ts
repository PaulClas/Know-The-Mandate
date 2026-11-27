import { expect, test } from "./helpers";

test("overview loads with tagline and verified ledger integrity", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tagline")).toContainText("The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers.");
  const integrity = page.getByTestId("ledger-integrity");
  await expect(integrity).toContainText("VERIFIED");
  await expect(integrity).toContainText("head hash");
  await expect(page.getByText("not compliant or certified").first()).toBeVisible();
  await expect(page.getByTestId("featured-scenario-c")).toBeVisible();
});
