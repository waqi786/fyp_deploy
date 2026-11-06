/**
 * Reader tab — end-to-end checks (Master Prompt Part 12). Every API call is mocked: no AI, no network.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const doc = {
  id: "c1f680d4c8347439b98d6b8c",
  title: "Grounded decoding for vision-language models",
  authors: ["A. Rahman", "L. Chen"],
  year: 2024,
  venue: "CVPR",
  doi: "10.1000/example.1",
  url: null,
  abstract: "A training-free decoding method that raises POPE F1 from 83.9 to 86.9.",
  source: "abstract",
  has_pdf: false,
  page_count: 3,
  word_count: 900,
  reading_minutes: 4,
  scanned_pages: [],
  captions: [{ kind: "figure", number: 1, page: 2, caption: "Overview of the pipeline." }],
  is_open_access: true,
  citation_count: 412,
};
const pages = [
  { page: 1, text: "Abstract\n\nWe propose grounded decoding." },
  { page: 2, text: "3 Method\n\nTokens are re-weighted by visual evidence.\n\nFigure 1: Overview of the pipeline." },
  { page: 3, text: "5 Results\n\nOn POPE, F1 rises from 83.9 to 86.9." },
];
const summary = {
  tldr: { text: "A training-free decoding method reduces hallucination.", pages: [1] },
  key_points: [{ text: "F1 rises from 83.9 to 86.9 on POPE.", pages: [3] }, { text: "No training is needed.", pages: [1] }],
  sections: { results: { text: "POPE F1 86.9.", pages: [3] } },
  level: "student",
  language: "en",
  basis: "upload",
  basic: false,
  credits_used: 2,
};

type Options = { summaryLimit?: boolean };

async function mockReader(page: Page, options: Options = {}) {
  const calls: string[] = [];
  await page.route("**/api/v1/**", async (route: Route) => {
    const url = route.request().url();
    calls.push(url);
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.endsWith("/reader/open")) return json(doc);
    if (url.includes("/pages")) return json({ pages });
    if (url.endsWith("/summary")) {
      if (options.summaryLimit) return json({ detail: { code: "limit_reached", scope: "session", resets_at: new Date(Date.now() + 3600e3).toISOString() } }, 402);
      return json(summary);
    }
    if (url.endsWith("/ask")) {
      return json({ answer: "F1 rises to 86.9 [p.3].", citations: [{ page: 3, quote: "F1 rises from 83.9 to 86.9" }], confidence: "high", not_found: false, language: "en", credits_used: 1 });
    }
    if (url.endsWith("/translate")) {
      return json({ language: "es", credits_used: 1, pages: [{ page: 1, paragraphs: ["Resumen"], original: ["Abstract"] }] });
    }
    if (url.includes(`/reader/${doc.id}`)) return json(doc);
    return json({});
  });
  return calls;
}

async function start(page: Page, language = "en") {
  await page.addInitScript((code) => {
    window.localStorage.setItem("resora-language", code);
    window.localStorage.setItem("resora-language-source", "settings");
    window.sessionStorage.setItem("resora-reader-handoff:p1", JSON.stringify({ title: "Grounded decoding", authors: ["A. Rahman"], abstract: "x" }));
  }, language);
}

test.describe("Reader", () => {
  test("the empty Reader offers upload and link, nothing else", async ({ page }) => {
    await start(page);
    await mockReader(page);
    await page.goto("/reader");
    await expect(page.getByRole("heading", { name: "Read any paper." })).toBeVisible();
    await expect(page.getByRole("button", { name: "Choose a PDF" })).toBeVisible();
    await expect(page.getByPlaceholder("Paste a DOI, arXiv ID or PDF link")).toBeVisible();
    await expect(page.locator("select")).toHaveCount(0);
  });

  test("Summarize from Search opens the Reader and starts the summary with page links", async ({ page }) => {
    await start(page);
    await mockReader(page);
    await page.goto("/reader?paper=p1&tab=summary&auto=1");
    await expect(page).toHaveURL(new RegExp(`/reader/${doc.id}`));
    await expect(page.locator(".rd-tldr")).toContainText("training-free decoding");
    await page.getByRole("button", { name: "Go to page 3" }).first().click();
    await expect(page.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
  });

  test("Read paper does not spend credits until the user asks", async ({ page }) => {
    await start(page);
    const calls = await mockReader(page);
    await page.goto("/reader?paper=p1&tab=summary");
    await expect(page.getByRole("button", { name: "Summarize" })).toBeVisible();
    expect(calls.some((url) => url.endsWith("/summary"))).toBe(false);
  });

  test("chat answers quote their page and figures can be explained", async ({ page }) => {
    await start(page);
    await mockReader(page);
    await page.goto(`/reader/${doc.id}?tab=figures`);
    await page.getByRole("button", { name: "Explain" }).click();
    await expect(page.getByRole("tab", { name: "Chat" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".rd-quotes")).toContainText("F1 rises from 83.9 to 86.9");
    await expect(page.getByText("High confidence")).toBeVisible();
  });

  test("a usage limit shows when it resets instead of a generic error", async ({ page }) => {
    await start(page);
    await mockReader(page, { summaryLimit: true });
    await page.goto(`/reader/${doc.id}?tab=summary`);
    await page.getByRole("button", { name: "Summarize" }).click();
    await expect(page.getByRole("alert")).toContainText("usage limit");
  });

  test("the whole Reader is in Urdu, right-to-left, with no English labels", async ({ page }) => {
    await start(page, "ur");
    await mockReader(page);
    await page.goto(`/reader/${doc.id}?tab=summary`);
    const reader = page.locator(".rd-reader");
    await expect(reader).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("button", { name: "خلاصہ بنائیں" })).toBeVisible();
    const labels = await page.locator(".rd-tabs, .rd-toolbar, .rd-start, .rd-head-actions, .rd-back").allInnerTexts();
    const english = labels.join(" ").replace(/PDF|Resora/g, "").match(/[A-Za-z]{3,}/g) || [];
    expect(english).toEqual([]);
  });

  test("no horizontal scrolling on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await start(page);
    await mockReader(page);
    await page.goto(`/reader/${doc.id}?tab=summary`);
    await expect(page.getByRole("tab", { name: "Paper" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("an API without the Reader routes is not reported as a missing document", async ({ page }) => {
    await start(page);
    await page.route("**/api/v1/**", (route) => route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not Found" }) }));
    await page.goto("/reader?paper=p1&tab=summary");
    await expect(page.getByRole("alert")).toContainText("could not be opened");
    await expect(page.getByText("no longer available")).toHaveCount(0);
  });
});