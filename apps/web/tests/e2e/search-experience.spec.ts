import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const paper = {
  paper_id: "fixture-paper-1", title: "Machine learning and deep learning", translated_title: "\u533b\u7597\u5065\u5eb7\u4e2d\u7684\u673a\u5668\u5b66\u4e60",
  abstract: "Machine learning and deep learning: Today, intelligent systems can support clinical decisions.", translated_abstract: "\u673a\u5668\u5b66\u4e60\u53ef\u4ee5\u652f\u6301\u4e34\u5e8a\u51b3\u7b56\u3002",
  translation_status: "translated", year: 2024, venue: "Health Informatics", citation_count: 12,
  is_open_access: true, source: "fixture", all_sources: [], authors: [{ name: "A. Researcher" }],
  result_badges: ["Open Access"], cluster_label: null, ranking_score: 0.9, micro_summary: null,
  datasets: [], methodologies: [], code_repositories: [], peer_review_status: "peer_reviewed", is_preprint: false,
  doi: null, publication_type: "journal-article", pdf_urls: [], external_ids: {}, url: "https://example.org/paper", pdf_url: null,
};
const webResult = {
  ...paper, paper_id: "fixture-web-1", title: "Clinical AI safety guidance", source: "web", all_sources: ["web"],
  venue: "www.example.org", publication_type: "web", url: "https://www.example.org/guidance", authors: [],
  result_badges: ["Web"], citation_count: 0,
};
const response = {
  query: "machine learning", normalized_query: "machine learning", translated_query: null,
  search_mode: "hybrid", query_type: "natural_language", total_results: 1, deduplicated_results: 1,
  papers: [paper, webResult], pagination: { page: 1, total_pages: 1, has_next_page: false, returned_results: 2 },
  suggestions: [], trending_topics: [], clusters: {}, source_coverage: {}, source_failures: [], search_insights: {},
  ranking_explanations: [], lazy_prefetch_window: [], author_network: [], author_disambiguation: [],
  venue_matches: [], institution_matches: [], dataset_matches: [], code_repository_matches: [],
  recommended_papers: [], citation_expansion_titles: [], co_citation_pairs: [], bibliographic_coupling_pairs: [],
  figure_search_matches: [], alert_preview_available: false,
};
const searchStream = [
  "event: search_started\ndata: {}\n\n",
  `event: source_results\ndata: ${JSON.stringify({ source: "scholarly", papers: response.papers })}\n\n`,
  `event: done\ndata: ${JSON.stringify(response)}\n\n`,
].join("");

test("search filters close on outside click and Escape", async ({ page }) => {
  await page.route("**/api/v1/search/stream", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: searchStream }));
  await page.goto("/search");
  await page.locator('input[name="search-query"]').fill("machine learning");
  await page.locator('input[name="search-query"]').press("Enter");
  await expect(page.locator(".rs-card").first()).toBeVisible();
  const panel = page.locator(".rs-filter-panel");
  await page.getByRole("button", { name: "More filters" }).click();
  await expect(panel).toBeVisible();
  await page.getByRole("radio", { name: "Research with Resora" }).click();
  await expect(panel).toBeHidden();
  await page.getByRole("button", { name: "More filters" }).click();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
});

test("empty search restores the voice control and centered starting point", async ({ page }) => {
  await page.addInitScript(() => {
    class FakeSpeechRecognition {
      lang = ""; interimResults = false; maxAlternatives = 1;
      onstart: (() => void) | null = null; onend: (() => void) | null = null; onerror: (() => void) | null = null;
      onresult: ((event: { results: Array<Array<{ transcript: string }>> }) => void) | null = null;
      start() { this.onstart?.(); this.onresult?.({ results: [[{ transcript: "hello research" }]] }); this.onend?.(); }
      stop() { this.onend?.(); }
    }
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, writable: true, value: FakeSpeechRecognition });
  });
  await page.route("**/api/v1/search/stream", async (route) => {
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: searchStream });
  });
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Find research." })).toBeVisible();
  await expect(page.getByText("Search papers, authors and topics in any language.")).toBeVisible();
  const voiceButton = page.getByRole("button", { name: "Search by voice" });
  await expect(voiceButton).toBeVisible();
  await expect(page.getByRole("button", { name: "More filters" })).toHaveCount(0);
  await expect(voiceButton).toBeEnabled();
  await voiceButton.click();
  await expect(page.locator('input[name="search-query"]')).toHaveValue("hello research");
  await expect(page.locator(".rs-card").first()).toBeVisible();
});

test("selecting Chinese searches in English and displays translated results", async ({ page }) => {
  let requestBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/search/stream", async (route) => {
    requestBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: searchStream });
  });
  await page.route("**/api/v1/library/items", (route) => route.fulfill({ json: { items: [{ id: "fixture-library-item", paper_key: paper.paper_id }], already_saved: [] } }));
  await page.goto("/search");
  await page.locator(".rs-language-pill").click();
  await page.locator('.rs-menu-item[lang="zh-Hans"]').click();
  await page.locator('input[name="search-query"]').fill("machine learning healthcare");
  await page.locator('input[name="search-query"]').press("Enter");
  await expect(page.getByRole("button", { name: /\u533b\u7597\u5065\u5eb7/ }).first()).toBeVisible();
  await expect(page.locator(".rs-card")).toHaveCount(2);
  await page.locator(".rs-language-pill").click();
  await page.locator(".rs-switch-row").click();
  await expect(page.locator(".rs-card").first()).toContainText("Today,");
  await expect(page.locator(".rs-card").first()).not.toContainText("Machine learning and deep learning: Today");
  await expect(page.getByRole("group", { name: "Result type" })).toHaveCount(0);
  await expect(page.getByText("Web result", { exact: true })).toHaveCount(0);
  await expect(page.getByText("www.example.org", { exact: true })).toHaveCount(0);
  expect(requestBody?.target_language).toBe("zh-Hans");
  expect(requestBody?.translate_results).toBe(true);
  expect(requestBody?.search_mode).toBe("hybrid");
  const saveAction = page.locator(".rs-card .rs-secondary-actions button[aria-pressed]").first();
  await saveAction.click();
  await expect(saveAction).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "访问网站" })).toBeVisible();
  await expect(page.getByRole("button", { name: "阅读论文" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看详细信息" })).toBeVisible();
});

test("Search results render in both brand themes at desktop and mobile widths", async ({ page }) => {
  await mkdir("test-shots/search-experience", { recursive: true });
  await page.route("**/api/v1/search/stream", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: searchStream }));
  for (const theme of ["light", "dark"] as const) {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.goto("/search");
      await page.evaluate((value) => localStorage.setItem("resora-theme", value), theme);
      await page.reload();
      await page.locator('input[name="search-query"]').fill("machine learning");
      await page.locator('input[name="search-query"]').press("Enter");
      await expect(page.locator(".rs-card").first()).toBeVisible();
      if (width === 390) {
        const moreActions = page.locator(".rs-mobile-more").first();
        await expect(moreActions.getByRole("button")).toBeVisible();
        await moreActions.getByRole("button").click();
        await expect(moreActions.getByRole("menuitem", { name: "Copy APA" })).toBeVisible();
        await moreActions.getByRole("button").click();
      }
      await page.screenshot({ path: `test-shots/search-experience/results-${theme}-${width}.png`, fullPage: true });
    }
  }
});
