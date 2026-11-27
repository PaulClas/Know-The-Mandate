import { expect, test } from "./helpers";

test("mandate studio compiles the example CNL and SHACL conforms", async ({ page }) => {
  await page.goto("/studio");
  await expect(page.getByTestId("cnl-editor")).toHaveValue(/PERMIT agent\.finance-assistant TO READ_BALANCE/);
  await expect(page.getByTestId("compile-status")).toContainText("Compiles", { timeout: 30_000 });
  await expect(page.getByTestId("compile-status")).toContainText("SHACL conforms");
  await page.getByRole("tab", { name: "SHACL & checks" }).click();
  await expect(page.getByTestId("shacl-conforms")).toHaveText("SHACL: conforms");
  await page.getByRole("tab", { name: "Consent summary" }).click();
  await expect(page.getByTestId("consent-summary")).toContainText("Meridian Bank");
  await page.getByRole("button", { name: "FR", exact: true }).click();
  await expect(page.getByTestId("consent-summary")).toContainText("Meridian Bank autorisera");
});

test("a syntax error is reported with line and column", async ({ page }) => {
  await page.goto("/studio");
  await expect(page.getByTestId("compile-status")).toContainText("Compiles", { timeout: 30_000 });
  await page.getByTestId("cnl-editor").fill("PERMIT agent.finance-assistant READ_BALANCE.");
  await expect(page.getByTestId("parse-errors")).toContainText("line 1", { timeout: 15_000 });
});
