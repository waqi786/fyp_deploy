/**
 * Search tab — end-to-end checks for the rules in docs/MASTER_PROMPT (Part 1A, Part 7, Part 11).
 * Every API call is mocked: these tests never touch live sources, AI providers or translators.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const SEARCH_PATH = process.env.E2E_SEARCH_PATH || "/search";

const papers = [
  {
    paper_id: "p1",
    title: "Grounded decoding for reducing object hallucination in vision-language models",
    abstract: "A training-free decoding method that raises POPE F1 from 83.9 to 86.9.",
    year: 2024,
    venue: "CVPR",
    citation_count: 412,
    is_open_access: true,
    pdf_url: "https://example.org/p1.pdf",
    source: "research",
    authors: [{ name: "A. Rahman" }, { name: "L. Chen" }],
    result_badges: [],
    datasets: [],
    methodologies: [],
    code_repositories: [],
    peer_review_status: "peer_reviewed",
    is_preprint: false,
    doi: "10.1000/example.1",
    matched_terms: ["hallucination"],
  },
  {
    paper_id: "p2",
    title: "Aligning vision-language models with human preferences",
    abstract: "Preference optimization on 5.7k pairs improves faithfulness.",
    year: 2025,
    venue: "ICLR",
    citation_count: 58,
    is_open_access: false,
    source: "research",
    authors: [{ name: "J. Park" }],
    result_badges: [],
    datasets: [],
    methodologies: [],
    code_repositories: [],
    peer_review_status: "preprint",
    is_preprint: true,
  },
];

const answer = {
  answer: "Decoding changes raise POPE F1 to 86.9 [1], and preference data helps [2].",
  evidence_ids: ["p1", "p2"],
  approaches: [{ label: "Decoding", paper_ids: ["p1"] }],
  emerging: [],
  conflicting: [],
  gaps: [{ text: "Few studies test video.", paper_ids: [], evidence_level: "hypothesis" }],
  insufficient_evidence: false,
  language: "en",
  credits_used: 5,
};

type MockOptions = { holdSearch?: boolean };

async function mockApi(page: Page, options: MockOptions = {}) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const url = route.request().url();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.includes("/search/research/stream")) {
      const frames = [
        ["step", { step: "understand", status: "done" }],
        ["step", { step: "search", status: "done" }],
        ["papers", { papers, total: 2 }],
        ["answer", answer],
        ["done", {}],
      ];
      return route.fulfill({ contentType: "text/event-stream", body: frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("") });
    }
    if (url.includes("/search/stream")) {
      if (options.holdSearch) return; // leave pending to inspect the loading state
      return json({ query: "q", total_results: 2, papers, pagination: { page: 1, has_next_page: false }, query_understanding: {} });
    }
    if (url.includes("/search/resolve")) return json({ kind: "doi", paper: papers[0] });
    if (url.includes("/search/research/estimate")) return json({ research_credits: 5, ask_credits: 1 });
    if (url.includes("/search/usage")) return json({ plan: "free", windows: [] });
    if (url.includes("/search/entities")) return json({ researchers: [], institutions: [] });
    return json([]);
  });
}

async function open(page: Page, theme: "light" | "dark" = "light") {
  await page.addInitScript((value) => {
    window.localStorage.setItem("resora-theme", value);
    window.localStorage.setItem("resora-language", "en");
    window.localStorage.setItem("resora-language-source", "auto");
  }, theme);
  await mockApi(page);
  await page.goto(SEARCH_PATH);
}

async function search(page: Page, query: string) {
  await page.getByRole("searchbox").first().fill(query);
  await page.keyboard.press("Enter");
}

function luminance(rgb: string) {
  const [r, g, b] = (rgb.match(/\d+(\.\d+)?/g) || ["0", "0", "0"]).slice(0, 3).map(Number).map((value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string) {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

test.describe("Search page", () => {
  test("empty state is calm: heading, one bar, no filters or sort", async ({ page }) => {
    await open(page);
    await expect(page.getByRole("heading", { name: "Find research." })).toBeVisible();
    await expect(page.getByRole("button", { name: /More filters/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Sort by/ })).toHaveCount(0);
    await expect(page.locator("select")).toHaveCount(0);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`accent button text is readable in ${theme} theme (≥ 4.5:1)`, async ({ page }) => {
      await open(page, theme);
      const button = page.locator(".rs-bar-submit");
      const colors = await button.evaluate((element) => {
        const style = getComputedStyle(element);
        return { color: style.color, background: style.backgroundColor, opacity: style.opacity };
      });
      expect(contrast(colors.color, colors.background)).toBeGreaterThanOrEqual(4.5);
      expect(colors.opacity).toBe("1");
    });
  }

  test("loading shows skeletons only — no count, no pagination, button keeps full colour", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("resora-language-source", "auto"));
    await mockApi(page, { holdSearch: true });
    await page.goto(SEARCH_PATH);
    await search(page, "hallucination");
    await expect(page.getByTestId("search-loading-skeletons")).toBeVisible();
    await expect(page.getByText(/About \d+ result/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Show more results|Load more/ })).toHaveCount(0);
    expect(await page.locator(".rs-bar-submit").evaluate((element) => getComputedStyle(element).opacity)).toBe("1");
  });

  test("results never show internal names or diagnostics", async ({ page }) => {
    await open(page);
    await search(page, "hallucination");
    await expect(page.getByText(/About 2 results/)).toBeVisible();
    const text = (await page.locator("body").innerText()).toLowerCase();
    for (const banned of ["openalex", "semantic scholar", "semantic_scholar", "crossref", "temporarily unavailable", "ranking_score", "source status"]) {
      expect(text).not.toContain(banned);
    }
  });

  test("cards use text buttons and the snippet does not repeat the title", async ({ page }) => {
    await open(page);
    await search(page, "hallucination");
    const card = page.locator(".rs-card").first();
    for (const label of ["Save", "Cite", "Compare", "Summarize", "Read paper"]) {
      await expect(card.getByRole("button", { name: label, exact: true })).toBeVisible();
    }
    await expect(card.locator(".rs-card-snippet")).not.toContainText("Grounded decoding for reducing");
  });

  test("popovers close on Escape and on outside click", async ({ page }) => {
    await open(page);
    await search(page, "hallucination");
    await page.getByRole("button", { name: /More filters/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: /Sort by/ }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    await page.getByRole("heading", { level: 3 }).first().click({ position: { x: 2, y: 2 }, force: true });
    await expect(page.getByRole("menu")).toHaveCount(0);
  });

  test("typing in Urdu switches the page to Urdu, right-to-left", async ({ page }) => {
    await open(page);
    await search(page, "مشین لرننگ میں ہیلوسینیشن");
    await expect(page.locator(".rs-search")).toHaveAttribute("dir", "rtl");
    await expect(page.locator(".rs-search")).toHaveAttribute("lang", "ur");
  });

  test("a pinned language is not changed by what the user types", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("resora-language", "en");
      window.localStorage.setItem("resora-language-source", "settings");
    });
    await mockApi(page);
    await page.goto(SEARCH_PATH);
    await search(page, "مشین لرننگ");
    await expect(page.locator(".rs-search")).toHaveAttribute("dir", "ltr");
  });

  test("pasting a DOI opens that paper", async ({ page }) => {
    await open(page);
    await search(page, "10.1000/example.1");
    await expect(page.getByRole("dialog")).toContainText("Grounded decoding");
  });

  test("Research with Resora shows a cited answer whose citations open the paper", async ({ page }) => {
    await open(page);
    await page.getByRole("radio", { name: "Research with Resora" }).click();
    await search(page, "how to reduce hallucination?");
    await expect(page.locator(".rs-answer")).toContainText("Decoding changes raise POPE F1");
    await page.locator(".rs-answer .rs-cite").first().click();
    await expect(page.getByRole("dialog")).toContainText("Grounded decoding");
  });

  test("no horizontal scrolling on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await open(page);
    await search(page, "hallucination");
    await expect(page.getByText(/About 2 results/)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("an Urdu interface shows no English labels and is never rewritten by the app-wide translator", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("resora-language", "ur");
      window.localStorage.setItem("resora-language-source", "settings");
    });
    await mockApi(page);
    await page.goto(SEARCH_PATH);
    await expect(page.locator(".rs-search")).toHaveAttribute("lang", "ur");
    await expect(page.locator(".rs-search")).toHaveAttribute("data-no-translate", "");
    await expect(page.locator(".rs-hero-title")).not.toHaveText("Find research.");
    const text = (await page.locator(".rs-search").innerText()).replace(/Resora|DOI|10\.1038\/s41586-020-2649-2/g, "");
    expect(text.match(/[A-Za-z]{3,}/g) || []).toEqual([]);
  });
});