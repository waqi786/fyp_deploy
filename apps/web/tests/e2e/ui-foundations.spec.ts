import { mkdir } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("development UI gallery exposes brand components in both themes and directions", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("resora-theme", "dark"));
  await page.goto("/dev/ui");
  await expect(page.getByRole("heading", { name: "UI foundations" })).toBeVisible();
  await mkdir("test-shots/ui-gallery", { recursive: true });
  await page.screenshot({ path: "test-shots/ui-gallery/gallery-dark-ltr.png", fullPage: true });
  await page.getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("body")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ path: "test-shots/ui-gallery/gallery-light-ltr.png", fullPage: true });
  await page.getByRole("button", { name: "RTL", exact: true }).click();
  await expect(page.locator("main[dir]")).toHaveAttribute("dir", "rtl");
  await page.screenshot({ path: "test-shots/ui-gallery/gallery-light-rtl.png", fullPage: true });
  await expect(page.getByRole("button", { name: "Dark", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Dialog", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Bottom sheet", exact: true })).toBeVisible();
});

test("shared popovers close on Escape, outside click, another popover, and route change", async ({ page }) => {
  await page.goto("/dev/ui");
  const trigger = page.getByRole("button", { name: "Open popover", exact: true });
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Filter options" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Filter options" })).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await trigger.click();
  await page.getByRole("button", { name: "More options", exact: true }).click();
  await expect(page.getByRole("menu", { name: "More options" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Filter options" })).toHaveCount(0);
  await page.getByRole("menuitem", { name: "First action" }).click();
  await expect(page.getByRole("menu", { name: "More options" })).toHaveCount(0);

  await trigger.click();
  await page.getByRole("heading", { name: "UI foundations" }).click();
  await expect(page.getByRole("dialog", { name: "Filter options" })).toHaveCount(0);
  await trigger.click();
  await page.getByRole("link", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/\/search$/);
});


test("mobile shell keeps primary tabs fixed and exposes overflow navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Mobile navigation" });
  await expect(nav).toBeVisible();
  await expect(nav.getByRole("link", { name: "Home" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Search" })).toBeVisible();
  await nav.getByRole("button", { name: "More" }).click();
  await expect(page.getByRole("menu", { name: "More navigation" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Compare" }).click();
  await expect(page).toHaveURL(/\/comparison$/);
  await expect(page.getByRole("menu", { name: "More navigation" })).toHaveCount(0);
  await page.goto("/");
  const more = page.getByRole("button", { name: "More" });
  await more.click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu", { name: "More navigation" })).toHaveCount(0);
  await expect(more).toBeFocused();
  await more.click();
  await page.getByRole("heading", { name: /Research|Resora/i }).first().click();
  await expect(page.getByRole("menu", { name: "More navigation" })).toHaveCount(0);
});


test("admin language readiness reports actual catalog coverage and tiers", async ({ page }) => {
  await page.route("**/admin/ai-router/health", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      providers: { groq: { configured: true, healthy: true, cooldown_seconds: 0 } },
      metrics: { groq: { calls: 7, errors: 1, rate_limits: 1, failovers: 1, latency_p50_ms: 40, latency_p95_ms: 90 } },
    }),
  }));
  await page.goto("/developer-ai");
  await page.getByRole("button", { name: "Admin", exact: true }).click();
  await expect(page.getByRole("table", { name: /Configured AI providers/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /groq/ })).toContainText("40 / 90 ms");
  const table = page.getByRole("table", { name: /Language catalog coverage/ });
  await expect(table).toBeVisible();
  await expect(table.getByRole("row", { name: /Marathi/ })).toContainText("PLANNED");
  await expect(table.getByRole("row", { name: /Arabic/ })).toContainText("BETA");
  await expect(page.getByText("PRODUCTION 0 ? BETA 16 ? PLANNED 31")).toBeVisible();
});
