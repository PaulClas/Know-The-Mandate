import { expect, test } from "./helpers";

test("scenarios page runs Scenario C and it passes", async ({ page }) => {
  await page.goto("/scenarios");
  const card = page.getByTestId("scenario-C");
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card).toContainText("Valid OAuth token, invalid mandate");
  await page.getByTestId("run-C").click();
  await expect(card.getByTestId("scenario-passed")).toHaveText("PASSED", { timeout: 40_000 });
  await expect(card).toContainText("BENEFICIARY_NOT_AUTHORIZED");
});
