/**
 * Gaps tab: evidence-levelled signals with the papers behind every count, saving / dismissing / turning a signal into
 * a Library idea, AI hypotheses, consensus, trends as a table, datasets, and Urdu with no English labels.
 * The API is a small in-memory fake, so the flows and requests are realistic.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const PAPERS = [
  { paper_id: "p1", title: "Grounded decoding for image captioning", abstract: "Grounded decoding reduces hallucination on POPE. A limitation is that evaluation uses only English data.", year: 2022, venue: "CVPR", citation_count: 120, authors: [{ name: "Ayesha Rahman", institution: "LUMS" }], datasets: ["POPE"] },
  { paper_id: "p2", title: "Contrastive decoding for faithful captions", abstract: "Contrastive decoding lowers hallucination on CHAIR. Evaluation uses only English data.", year: 2023, venue: "NeurIPS", citation_count: 80, authors: [{ name: "Noah Park" }], datasets: ["CHAIR"] },
  { paper_id: "p3", title: "Retrieval-augmented generation for visual question answering", abstract: "RAG improves accuracy on VQA but does not reduce hallucination.", year: 2024, venue: "ACL", citation_count: 30, authors: [{ name: "Sara Ali" }], datasets: ["VQA"] },
  { paper_id: "p4", title: "Grounding vision-language models with region features", abstract: "Region grounding reduces hallucination on POPE.", year: 2025, venue: "ICLR", citation_count: 5, authors: [{ name: "Ayesha Rahman" }], datasets: ["POPE"] },
];

const SIGNALS = [
  { id: "s-limit", kind: "repeated_limitation", level: "strong", a: { kind: "theme", label: "English" }, counts: { a: 2 }, papers: { a: ["p1", "p2"] }, quotes: [{ paper_id: "p1", text: "A limitation is that evaluation uses only English data." }, { paper_id: "p2", text: "Evaluation uses only English data." }] },
  { id: "s-combo", kind: "combination_untested", level: "moderate", a: { kind: "method", label: "RAG" }, b: { kind: "dataset", label: "POPE" }, counts: { a: 1, b: 2, both: 0 }, papers: { a: ["p3"], b: ["p1", "p4"], both: [] }, quotes: [] },
  { id: "s-h2h", kind: "head_to_head", level: "limited", a: { kind: "method", label: "Contrastive learning" }, b: { kind: "method", label: "RAG" }, shared: ["Hallucination"], counts: { a: 1, b: 1, both: 0 }, papers: { a: ["p2"], b: ["p3"], both: [] }, quotes: [] },
];

async function fakeApi(page: Page) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  const states: Record<string, string> = {};
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path === "/search/") return json({ papers: body.page === 1 ? PAPERS : [] });
    if (path === "/library/lists") return json([{ id: "proj1", kind: "project", name: "Thesis chapter 2", item_count: 2 }]);
    if (path === "/library/items") return json([]);
    if (path === "/library/notes") return json([{ id: "n1", kind: "idea", title: "Test grounding on Urdu captions", body: "", status: "exploring", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" }]);
    if (path === "/gap/signals") {
      return json({
        scope_key: "topic:hallucination", paper_count: body.papers.length, signals: SIGNALS, states,
        trends: { years: [{ year: 2022, papers: 1, citations: 120 }, { year: 2023, papers: 1, citations: 80 }, { year: 2024, papers: 1, citations: 30 }, { year: 2025, papers: 1, citations: 5 }], series: { method: [{ label: "Contrastive learning", total: 1, by_year: { 2023: 1 } }], dataset: [{ label: "POPE", total: 2, by_year: { 2022: 1, 2025: 1 } }], task: [] }, keywords: [{ label: "decoding", count: 2 }] },
        people: { researchers: [{ name: "Ayesha Rahman", papers: 2, citations: 125, first_year: 2022, last_year: 2025, collaborators: [], suggested: [{ name: "Noah Park", shared: ["Contrastive learning", "Hallucination"] }], paper_ids: ["p1", "p4"] }], institutions: [{ name: "LUMS", papers: 1 }] },
        datasets: [{ name: "POPE", papers: 2, paper_ids: ["p1", "p4"], tasks: ["Hallucination"], methods: [], metrics: ["Accuracy"], first_year: 2022, last_year: 2025, open_access_papers: 0, quote: "Grounded decoding reduces hallucination on POPE." }],
      });
    }
    const stateMatch = path.match(/^\/gap\/states\/([\w-]+)(\/idea)?$/);
    if (stateMatch && stateMatch[2]) { states[stateMatch[1]] = "idea"; return json({ idea_id: "n2" }); }
    if (stateMatch) { if (body.state) states[stateMatch[1]] = body.state; else delete states[stateMatch[1]]; return route.fulfill({ status: 204 }); }
    if (path === "/gap/consensus") {
      return json({ mode: "keywords", credits_used: 0, counts: { supports: 3, opposes: 1, mixed: 0, not_addressed: 0 }, rows: [
        { paper_id: "p1", stance: "supports", reason: "", quote: "Grounded decoding reduces hallucination on POPE." },
        { paper_id: "p2", stance: "supports", reason: "", quote: "Contrastive decoding lowers hallucination on CHAIR." },
        { paper_id: "p4", stance: "supports", reason: "", quote: "Region grounding reduces hallucination on POPE." },
        { paper_id: "p3", stance: "opposes", reason: "", quote: "RAG improves accuracy on VQA but does not reduce hallucination." },
      ] });
    }
    if (path === "/gap/hypotheses") return json({ credits_used: 1, hypotheses: [{ id: "h1", kind: "ai_hypothesis", level: "hypothesis", a: { kind: "idea", label: "Test grounded decoding on non-English captions" }, detail: "Every evaluation so far uses English data only.", counts: { a: 2 }, papers: { a: ["p1", "p2"] }, quotes: [] }] });
    return json({});
  });
  return { calls, states };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { window.localStorage.setItem("resora-compare-owner", "e2e-owner"); window.sessionStorage.clear(); });
});

test("signals: evidence levels, the papers behind counts, save, idea and dismiss", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/gaps");
  await expect(page.getByRole("heading", { name: "Gaps", level: 1 })).toBeVisible();
  await page.getByLabel("Topic to analyze").fill("hallucination");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.locator(".gw-signal")).toHaveCount(3);
  await expect(page.getByText("Signals describe the evidence in these 4 papers.", { exact: false })).toBeVisible();
  const first = page.locator(".gw-signal").first();
  await expect(first.getByText("A limitation repeated across papers: English")).toBeVisible();
  await expect(first.locator(".gw-level")).toHaveText("Strong");
  await expect(page.getByText("RAG: 1 papers · POPE: 2 papers · together: 0")).toBeVisible();

  await first.getByRole("button", { name: "Papers behind this" }).click();
  await expect(first.locator(".gw-paper-link")).toHaveCount(2);

  await first.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/gap/states/s-limit" && call.method === "PUT")?.body).toMatchObject({ state: "saved", scope_key: "topic:hallucination" });
  await first.getByRole("button", { name: "Turn into idea" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Added to your ideas in the Library." })).toBeVisible();

  await page.locator(".gw-signal").nth(2).getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Dismiss" }).click();
  await expect(page.locator(".gw-signal")).toHaveCount(2);
  await page.getByRole("button", { name: "Show hidden (1)" }).click();
  await expect(page.locator(".gw-signal")).toHaveCount(3);

  await page.getByRole("button", { name: "Moderate" }).click();
  await expect(page.locator(".gw-signal")).toHaveCount(1);
  await page.getByRole("button", { name: "All" }).click();
  await page.getByRole("button", { name: "Suggest AI hypotheses" }).click();
  await expect(page.getByText("Test grounded decoding on non-English captions")).toBeVisible();
  await expect(page.locator(".gw-level-hypothesis")).toHaveText("AI hypothesis");
});

test("consensus, trends, people, datasets and ideas", async ({ page }) => {
  await fakeApi(page);
  await page.goto("/gaps/consensus?topic=hallucination");
  await page.getByLabel("Research question").fill("Does grounding reduce hallucination?");
  await page.getByRole("button", { name: "Check consensus" }).click();
  await expect(page.locator(".gw-stance-legend")).toContainText("Supports 3");
  await expect(page.locator(".gw-stance-legend")).toContainText("Opposes 1");
  await expect(page.getByText("A written judgement is not available right now", { exact: false })).toBeVisible();

  await page.getByRole("link", { name: "Trends" }).click();
  await expect(page.getByText("Papers per year")).toBeVisible();
  await page.getByRole("button", { name: "View as table" }).click();
  await expect(page.locator(".gw-table").first()).toContainText("2024");

  await page.getByRole("link", { name: "People" }).click();
  await expect(page.getByText("Ayesha Rahman").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Possible collaborators" })).toBeVisible();
  await expect(page.getByText("Noah Park (shared: Contrastive learning, Hallucination)")).toBeVisible();
  await page.getByRole("link", { name: "Datasets" }).click();
  await expect(page.locator(".gw-table")).toContainText("POPE");
  await expect(page.locator(".gw-table")).toContainText("Not stated");
  await page.getByRole("link", { name: "Ideas" }).click();
  await expect(page.getByText("Test grounding on Urdu captions")).toBeVisible();
});

test("Urdu: every Gaps label is Urdu and the layout is right-to-left", async ({ page }) => {
  await page.addInitScript(() => { window.localStorage.setItem("resora-language", "ur"); window.localStorage.setItem("resora-language-source", "settings"); });
  await fakeApi(page);
  await page.goto("/gaps/signals?lang=ur&topic=hallucination");
  await expect(page.getByRole("heading", { name: "تحقیقی خلا", level: 1 })).toBeVisible();
  await expect(page.locator(".gw-signal")).toHaveCount(3);
  await expect(page.locator(".gw-page")).toHaveAttribute("dir", "rtl");
  const text = await page.locator(".gw-page").innerText();
  const content = ["hallucination", "English", "RAG", "POPE", "Contrastive learning", "Hallucination", "A limitation is that evaluation uses only English data.", "Grounded decoding for image captioning"];
  let rest = text;
  for (const item of [...content].sort((a, b) => b.length - a.length)) rest = rest.split(item).join(" ");
  expect([...new Set(rest.match(/[A-Za-z]{3,}/g) || [])]).toEqual([]);
});
