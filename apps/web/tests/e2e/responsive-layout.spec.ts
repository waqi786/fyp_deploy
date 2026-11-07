import { expect, test } from "@playwright/test";

const routes = [
  "/",
  "/search",
  "/reader",
  "/comparison",
  "/gaps",
  "/writing",
  "/library",
  "/chat",
  "/multimodal",
  "/collaboration",
  "/personalization",
  "/analytics",
  "/security-mobile",
  "/developer-ai",
  "/assurance",
  "/control",
  "/open-source",
  "/researchers/demo",
  "/institutions/demo",
];

const viewports = [
  { width: 320, height: 568 },
  { width: 360, height: 640 },
  { width: 375, height: 667 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 568, height: 320 },
  { width: 667, height: 375 },
  { width: 768, height: 1024 },
  { width: 820, height: 1180 },
  { width: 1024, height: 768 },
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
];

test("product routes fit phone, tablet, laptop and desktop viewports without page overflow", async ({ page }) => {
  const overflows: Array<{ route: string; width: number; height: number; documentWidth: number; bodyWidth: number }> = [];

  for (const route of routes) {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(route);
    await expect(page.locator("main").first()).toBeVisible();

    for (const { width, height } of viewports) {
      await page.setViewportSize({ width, height });
      const sizes = await page.evaluate(() => ({
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        viewportWidth: window.innerWidth,
      }));
      if (sizes.documentWidth > sizes.viewportWidth + 1 || sizes.bodyWidth > sizes.viewportWidth + 1) {
        overflows.push({ route, width, height, documentWidth: sizes.documentWidth, bodyWidth: sizes.bodyWidth });
      }
    }
  }

  expect(overflows, JSON.stringify(overflows, null, 2)).toEqual([]);
});
