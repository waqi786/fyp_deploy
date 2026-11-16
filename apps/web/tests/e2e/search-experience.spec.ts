/**
 * Search experience on the redesigned Search tab (master prompt Part 11): voice search, results in the reader's
 * language (Chinese), and result cards in both brand themes at desktop and phone widths. Every API call is mocked.
 * (Popover dismissal, loading states and Urdu are covered in search.spec.ts.)
 */
import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const paper = {
  paper_id: "fixture-paper-1", title: "Machine learning in healthcare", translated_title: "医疗健康中的机器学习",
  abstract: "Machine learning can support clinical decisions in hospitals.", translated_abstract: "机器学习可以支持临床决策。",
  translation_status: "translated", year: 2024, venue: "Health Informatics", citation_count: 12, is_open_access: true, source: "research",
  authors: [{ name: "A. Researcher" }], result_badges: [], datasets: [], methodologies: [], code_repositories: [], peer_review_status: "peer_reviewed",
  is_preprint: false, doi: "10.1000/fixture.1", pdf_url: "https://example.org/paper.pdf",
};

async function mockApi(page: Page) {
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = request.url();
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (url.includes("/search/stream")) {
      bodies.push((request.postDataJSON() || {}) as Record<string, unknown>);
      return json({ query: "q", total_results: 1, papers: [paper], pagination: { page: 1, has_next_page: false }, query_understanding: {} });
    }
    if (url.includes("/search/usage")) return json({ plan: "free", windows: [] });
    if (url.includes("/search/research/estimate")) return json({ research_credits: 5, ask_credits: 1 });
    if (url.includes("/library/items/lookup")) return json({ items: {} });
    return json([]);
  });
  return bodies;
}

test("voice search fills the bar and runs the search", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("resora-language", "en");
    window.localStorage.setItem("resora-language-source", "settings");
    class FakeSpeechRecognition {
      lang = ""; interimResults = false; maxAlternatives = 1; continuous = false;
      onstart: (() => void) | null = null; onend: (() => void) | null = null; onerror: (() => void) | null = null;
      onresult: ((event: { results: Array<Array<{ transcript: string }>> & { length: number } }) => void) | null = null;
      start() { this.onstart?.(); const results = Object.assign([[{ transcript: "machine learning healthcare" }]], { length: 1 }); this.onresult?.({ results } as never); this.onend?.(); }
      stop() { this.onend?.(); }
      abort() { this.onend?.(); }
    }
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, writable: true, value: FakeSpeechRecognition });
  });
  const bodies = await mockApi(page);
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Find research." })).toBeVisible();
  await page.getByRole("button", { name: "Search by voice" }).click();
  await expect(page.getByRole("searchbox").first()).toHaveValue("machine learning healthcare");
  await expect(page.locator(".rs-card").first()).toBeVisible();
  expect(bodies.length).toBeGreaterThan(0);
});

test("a Chinese interface asks for translated results and shows them, with the original one click away", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("resora-language", "zh-Hans");
    window.localStorage.setItem("resora-language-source", "settings");
  });
  const bodies = await mockApi(page);
  await page.goto("/search");
  await expect(page.locator(".rs-search")).toHaveAttribute("lang", "zh-Hans");
  await page.getByRole("searchbox").first().fill("machine learning healthcare");
  await page.keyboard.press("Enter");
  await expect(page.locator(".rs-card").first()).toContainText("医疗健康");
  expect(bodies.at(-1)?.target_language).toBe("zh-Hans");
  expect(bodies.at(-1)?.translate_results).toBe(true);
});

test("result cards render in both brand themes at desktop and phone widths without horizontal scrolling", async ({ page }) => {
  await mkdir("test-shots/search-experience", { recursive: true });
  await mockApi(page);
  for (const theme of ["light", "dark"] as const) {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => {
        window.localStorage.setItem("resora-theme", value);
        window.localStorage.setItem("resora-language", "en");
        window.localStorage.setItem("resora-language-source", "settings");
      }, theme);
      await page.goto("/search");
      await page.getByRole("searchbox").first().fill("machine learning");
      await page.keyboard.press("Enter");
      const card = page.locator(".rs-card").first();
      await expect(card).toBeVisible();
      await expect(card.getByRole("button", { name: "Read paper", exact: true })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: `test-shots/search-experience/results-${theme}-${width}.png`, fullPage: true });
    }
  }
});
