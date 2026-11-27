import { expect, test } from "./helpers";

const ROUTES = ["/", "/agents", "/studio", "/portal", "/delegation", "/playground", "/sandbox", "/scenarios", "/transactions", "/ledger", "/disputes", "/ontology", "/standards", "/about", "/proof"];

for (const route of ROUTES) {
  test(`page ${route} renders without runtime errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(route);
    await expect(page.locator("h1").first()).toBeVisible();
    await page.waitForTimeout(2500);
    await expect(page.getByText("Application error")).toHaveCount(0);
    if (process.env.PW_SHOTS) await page.screenshot({ path: `test-results/shots${route === "/" ? "/home" : route}.png`, fullPage: true });
    expect(errors).toEqual([]);
  });
}
