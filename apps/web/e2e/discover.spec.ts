import { expect, test } from "@playwright/test";

test("about page exposes the canonical definition and FAQPage structured data", async ({ page }) => {
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: /About KYM/ })).toBeVisible();
  await expect(page.getByText("experimental framework that lets a bank represent, enforce and prove").first()).toBeVisible();
  const ld = await page.locator('script[type="application/ld+json"]').first().textContent();
  const types = (JSON.parse(ld ?? "[]") as { "@type": string }[]).map((x) => x["@type"]);
  expect(types).toEqual(["SoftwareApplication", "FAQPage"]);
  expect(await page.title()).toContain("About KYM");
});

test("robots, sitemap and llms.txt are served", async ({ request }) => {
  const robots = await (await request.get("/robots.txt")).text();
  expect(robots).toContain("Disallow: /api/");
  expect(robots).toContain("Sitemap:");
  expect(await (await request.get("/sitemap.xml")).text()).toContain("/about");
  const llms = await (await request.get("/llms.txt")).text();
  expect(llms).toContain("# KYM (Know Your Mandate)");
  expect(llms).toContain("does NOT prevent harm from actions that stay inside the mandate");
});

test("proof page runs the red-team harness; KYM blocks everything except the documented honest gap", async ({ page }) => {
  await page.goto("/proof");
  await page.getByTestId("run-redteam").click();
  await expect(page.getByTestId("redteam-report")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("tally-kym")).toHaveText("22/22");
  await expect(page.getByTestId("tally-scope_only")).toHaveText("0/10");
  await expect(page.getByTestId("attack-in_mandate_malicious")).toContainText("succeeded");
});
