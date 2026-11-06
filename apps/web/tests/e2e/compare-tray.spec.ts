/**
 * Search → Compare: papers picked on result cards go to the Compare tray, then into a private comparison.
 * The existing upload → table → Insights flow is covered by compare-insights.spec.ts and must keep passing.
 * Every API call is mocked.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const paper = (id: string, title: string, pdf: boolean) => ({
  paper_id: id,
  title,
  abstract: `${title} abstract with enough words to show a snippet in the card.`,
  year: 2024,
  venue: "CVPR",
  citation_count: 10,
  is_open_access: pdf,
  pdf_url: pdf ? `https://example.org/${id}.pdf` : null,
  source: "research",
  authors: [{ name: "A. Rahman" }],
  result_badges: [],
  datasets: [],
  methodologies: [],
  code_repositories: [],
  peer_review_status: "peer_reviewed",
  is_preprint: false,
  matched_terms: [],
});
const papers = [paper("p1", "Grounded decoding for vision-language models", true), paper("p2", "A closed-access study of captions", false)];
const comparisonId = "bfa6a27e-d302-4c8b-8e27-713dbcbfd170";
const stored = { id: "f1b40bab-72d2-4c7a-a31f-0f79fa2d4d01", name: "Grounded decoding for vision-language models.pdf", pages: 9, size: 2_000_000, sha256: "a".repeat(64) };

async function mock(page: Page) {
  const addRequests: unknown[] = [];
  await page.route("**/api/v1/**", async (route: Route) => {
    const url = route.request().url();
    const json = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    if (url.includes("/search/stream")) return json({ query: "q", total_results: 2, papers, pagination: { page: 1, has_next_page: false } });
    if (url.includes("/search/usage")) return json({ plan: "free", windows: [] });
    if (url.includes("/search/entities")) return json({ researchers: [], institutions: [] });
    if (url.includes("/comparison/pdfs/limits")) return json({ max_files: 15, max_bytes: 50_000_000, max_pages: 120 });
    if (url.includes("/comparison/pdfs/add-papers")) {
      addRequests.push(route.request().postDataJSON());
      return json({ comparison_id: comparisonId, files: [stored], unavailable: [{ key: "p2", title: papers[1].title, reason: "no_open_pdf", publisher_url: "https://publisher.example.org/paper/p2" }] });
    }
    if (url.includes("/comparison/pdfs?comparison_id=")) return json({ comparison_id: comparisonId, files: [stored] });
    return json([]);
  });
  return addRequests;
}

test("papers picked in Search arrive in Compare; papers without an open PDF explain subscription access and link to the paper page", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("resora-language", "en");
    window.localStorage.setItem("resora-language-source", "settings");
    window.localStorage.removeItem("resora-compare-tray");
  });
  const addRequests = await mock(page);
  await page.goto("/search");
  await page.getByRole("searchbox").first().fill("hallucination");
  await page.keyboard.press("Enter");
  const cards = page.locator(".rs-card");
  await expect(cards).toHaveCount(2);

  await cards.nth(0).getByRole("button", { name: "Compare", exact: true }).click();
  await expect(cards.nth(0).getByRole("button", { name: "In Compare" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("1 paper to compare")).toBeVisible();
  await cards.nth(1).getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByText("2 papers to compare")).toBeVisible();

  await page.locator(".ct-open").click();
  await expect(page).toHaveURL(/\/comparison/);
  await expect(page.getByText(stored.name)).toBeVisible();
  await expect(page.getByText("No legal open-access PDF was found. The publisher may require a paid subscription.", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Visit paper page" })).toHaveAttribute("href", "https://publisher.example.org/paper/p2");
  await expect(page.getByRole("button", { name: "Upload PDF" })).toBeVisible();
  expect((addRequests[0] as { papers: Array<{ key: string }> }).papers.map((item) => item.key)).toEqual(["p1", "p2"]);
  // The tray is emptied once its papers are in the comparison.
  expect(await page.evaluate(() => window.localStorage.getItem("resora-compare-tray"))).toBe("[]");
});

test("Compare on a card toggles; removing from the tray updates the card", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.removeItem("resora-compare-tray"));
  await mock(page);
  await page.goto("/search");
  await page.getByRole("searchbox").first().fill("hallucination");
  await page.keyboard.press("Enter");
  const card = page.locator(".rs-card").first();
  await card.getByRole("button", { name: "Compare", exact: true }).click();
  await page.getByRole("button", { name: /^Remove Grounded decoding/ }).click();
  await expect(page.locator(".ct-bar")).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Compare", exact: true })).toHaveAttribute("aria-pressed", "false");
});
