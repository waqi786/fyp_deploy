/**
 * Write tab: a review built from Library papers (outline, write a section from sources, citation insert, autosave,
 * check, export), screening with decisions, reasons and live PRISMA counts, claim checks with evidence and safer
 * wording, and Urdu with no English labels. The API is a small in-memory fake, so the requests are realistic.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const ITEMS = [
  { id: "i1", paper_key: "k1", title: "Grounded decoding reduces object hallucination", authors: ["Ayesha Rahman"], year: 2024, venue: "CVPR", abstract: "Grounding lowers hallucination on POPE.", status: "to_read", tags: [], list_ids: ["proj1"], important: false, read_later: false, source: "search", added_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" },
  { id: "i2", paper_key: "k2", title: "Contrastive decoding for faithful captions", authors: ["Noah Park"], year: 2023, venue: "NeurIPS", abstract: "Contrastive decoding lowers hallucination on CHAIR.", status: "to_read", tags: [], list_ids: ["proj1"], important: false, read_later: false, source: "search", added_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" },
];

const emptyPrisma = { identified: 2, duplicates: 0, screened: 2, screen_excluded: 0, screen_pending: 2, full_text_assessed: 0, full_text_excluded: 0, full_text_pending: 0, full_text_reasons: [], included: 0 };

async function fakeApi(page: Page) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  const doc: any = {
    id: "d1", kind: "review", title: "", style: "thematic", language: "en", citation_style: "apa", project_id: "proj1", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
    sources: ITEMS.map((item) => ({ item_id: item.id, title: item.title, authors: item.authors, year: item.year, abstract: item.abstract })),
    sections: [
      { id: "s1", heading: "Introduction", purpose: "introduction", papers: [1, 2], text: "", status: "empty", unsupported: [] },
      { id: "s2", heading: "Decoding methods", purpose: "theme", papers: [1, 2], text: "", status: "empty", unsupported: [] },
    ],
  };
  let created = false;
  const records = ITEMS.map((item, index) => ({ id: `r${index + 1}`, title: item.title, authors: item.authors, year: item.year, abstract: item.abstract, ta_decision: null, ft_decision: null }));
  const prisma = { ...emptyPrisma };
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path === "/library/items") return json(ITEMS);
    if (path === "/library/lists") return json([{ id: "proj1", kind: "project", name: "Thesis chapter 2", item_count: 2 }]);
    if (path === "/write/documents" && request.method() === "GET") return json(created ? [{ id: "d1", kind: "review", title: doc.title, style: "thematic", language: "en", updated_at: doc.updated_at, summary: { sections: 2, words: 0, sources: 2 } }] : []);
    if (path === "/write/documents" && request.method() === "POST") { created = true; doc.title = body.title; return json(doc); }
    if (path === "/write/documents/d1" && request.method() === "GET") return json(doc);
    if (path === "/write/documents/d1" && request.method() === "PATCH") { Object.assign(doc, body); return json(doc); }
    if (path === "/write/documents/d1/sections/s1/write") {
      doc.sections[0] = { ...doc.sections[0], status: "generated", text: "Grounded decoding lowers hallucination on POPE [1]. Contrastive decoding lowers it on CHAIR [2]. It also removes every error.", unsupported: ["It also removes every error."] };
      return json(doc);
    }
    if (path === "/write/documents/d1/themes") return json({ themes: [
      { label: "Image captioning", kind: "task", papers: [1, 2], evidence: "mixed", quotes: [{ n: 1, text: "Grounding lowers hallucination on POPE." }] },
      { label: "POPE", kind: "dataset", papers: [1], evidence: "consistent", quotes: [] },
    ] });
    if (path === "/write/documents/d1/outline") {
      doc.sections = [doc.sections[0], ...body.themes.map((theme: any, index: number) => ({ id: `t${index}`, heading: theme.label, purpose: "theme", papers: theme.papers, text: "", status: "empty", unsupported: [] }))];
      return json(doc);
    }
    if (path === "/write/documents/d1/check") return json({ broken_markers: [], uncited_sources: [], unsupported: [{ section_id: "s1", sentences: doc.sections[0].unsupported }] });
    if (path === "/write/documents/d1/export") return json({ filename: "review.md", mime: "text/markdown", content: "# Review\n" });
    if (path === "/write/screenings" && request.method() === "GET") return json({ screenings: [{ id: "sc1", name: "Systematic review", criteria: "", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", prisma }] });
    if (path === "/write/screenings/sc1") return json({ id: "sc1", name: "Systematic review", criteria: "Peer-reviewed", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", prisma, records });
    const decide = path.match(/^\/write\/screenings\/sc1\/records\/(r\d)$/);
    if (decide) {
      const record: any = records.find((entry) => entry.id === decide[1]);
      Object.assign(record, body);
      prisma.screen_excluded = records.filter((entry: any) => entry.ta_decision === "exclude").length;
      prisma.full_text_assessed = records.filter((entry: any) => entry.ta_decision === "include").length;
      prisma.screen_pending = records.filter((entry: any) => !entry.ta_decision).length;
      return json({ record, prisma: { ...prisma } });
    }
    if (path === "/write/claims") {
      return json({ mode: "ai", credits_used: 1, sources: [{ n: 1, item_id: "i1", title: ITEMS[0].title, year: 2024, authors: ["Ayesha Rahman"] }], claims: [
        { claim: "Grounding removes all hallucination.", verdict: "mixed", strength: "moderate", evidence: [{ n: 1, quote: "Grounding lowers hallucination on POPE." }], safer: "Grounding lowers hallucination on POPE." },
        { claim: "Decoding is solved.", verdict: "not_found", evidence: [] },
      ] });
    }
    return json({});
  });
  return { calls, doc, prisma };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("resora-compare-owner", "e2e-owner"));
});

test("review: create from a project, write a section from sources, cite, autosave, check and export", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/writing/reviews");
  await expect(page.getByRole("heading", { name: "Write", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "New review" }).first().click();
  await page.getByLabel("Title").fill("Hallucination review");
  await page.getByRole("button", { name: /^Sources:/ }).click();
  await page.getByRole("option", { name: "Project: Thesis chapter 2" }).click();
  await expect(page.getByText("2 papers chosen")).toBeVisible();
  await page.getByRole("button", { name: "Create review" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/write/documents" && call.method === "POST")?.body).toMatchObject({ kind: "review", title: "Hallucination review", style: "thematic", project_id: "proj1", item_ids: ["i1", "i2"] });
  await expect(page).toHaveURL(/\/writing\/doc\/d1/);

  const intro = page.getByRole("region", { name: "Introduction" });
  await intro.getByRole("button", { name: "Write with sources" }).click();
  await expect(intro.locator(".gw-section-text")).toHaveValue(/\[1\]/);
  await expect(intro.getByText("Unsupported sentences (1)")).toBeVisible();

  const second = page.getByRole("region", { name: "Decoding methods" });
  await second.locator(".gw-section-text").fill("Both methods decode differently");
  await page.getByRole("button", { name: /Insert citation \[2\]/ }).click();
  await expect(second.locator(".gw-section-text")).toHaveValue("Both methods decode differently [2]");
  await expect.poll(() => api.calls.some((call) => call.method === "PATCH" && JSON.stringify(call.body).includes("decode differently [2]")), { timeout: 5000 }).toBe(true);
  await expect(page.locator(".gw-save-state")).toHaveText("Saved");

  await page.getByRole("button", { name: "Check", exact: true }).click();
  await expect(page.getByText("1 sentences are not backed by a source")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("menuitem", { name: "Markdown" }).click();
  expect((await download).suggestedFilename()).toBe("review.md");
});

test("review path: themes become the outline, claims are checked inside a section, coverage per source", async ({ page }) => {
  const api = await fakeApi(page);
  api.doc.title = "Hallucination review";
  await page.goto("/writing/doc/d1");
  const steps = page.getByRole("list", { name: "Review steps" });
  await expect(steps).toContainText("Collect");
  await expect(steps).toContainText("0/2");
  await steps.getByRole("button", { name: /Themes/ }).click();
  const dialog = page.getByRole("dialog", { name: "Choose themes" });
  await expect(dialog.getByText("Mixed results", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Use 2 themes as outline" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/write/documents/d1/outline")?.body).toMatchObject({ style: "thematic", themes: [{ label: "Image captioning", papers: [1, 2] }, { label: "POPE", papers: [1] }] });
  await expect(page.getByRole("region", { name: "Image captioning" })).toBeVisible();

  const intro = page.getByRole("region", { name: "Introduction" });
  await intro.getByRole("button", { name: "Write with sources" }).click();
  await expect(page.locator(".gw-coverage").first()).toHaveText("Cited in 1 sections");
  await intro.getByRole("button", { name: "Check claims" }).click();
  await expect(intro.getByText("Claims in this section")).toBeVisible();
  await expect(intro.locator(".gw-verdict-mixed")).toHaveText("Partly supported");
  expect(api.calls.find((call) => call.path === "/write/claims")?.body).toMatchObject({ document_id: "d1" });
});

test("screening: decisions with reasons update the PRISMA counts", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/writing/screening/sc1");
  await expect(page.getByRole("img", { name: "PRISMA flow" })).toBeVisible();
  await expect(page.locator(".gw-record")).toHaveCount(2);
  await page.locator(".gw-record").first().getByRole("button", { name: "Include" }).click();
  await page.locator(".gw-record").nth(1).getByRole("button", { name: "Exclude" }).click();
  await page.locator(".gw-record").nth(1).getByRole("button", { name: /^Reason:/ }).click();
  await page.getByRole("option", { name: "Wrong study design" }).click();
  await expect.poll(() => api.calls.filter((call) => call.path === "/write/screenings/sc1/records/r2").map((call) => call.body)).toContainEqual({ ta_reason: "Wrong study design" });
  await expect(page.getByText("Excluded at screening: 1")).toBeVisible();
  await expect(page.locator("select")).toHaveCount(0);
  await expect(page.getByText("Full texts assessed: 1")).toBeVisible();
  await page.getByRole("tab", { name: /Full text/ }).click();
  await expect(page.locator(".gw-record")).toHaveCount(1);
});

test("claim check: verdicts, evidence and safer wording", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/writing/claims");
  await page.getByLabel("Text to check").fill("Grounding removes all hallucination. Decoding is solved.");
  await page.getByRole("button", { name: "Check claims" }).last().click();
  await expect(page.locator(".gw-claim")).toHaveCount(2);
  await expect(page.locator(".gw-verdict-mixed")).toHaveText("Partly supported");
  await expect(page.locator(".gw-verdict-not_found")).toHaveText("No evidence found");
  await expect(page.getByText("Safer wording:")).toBeVisible();
  await expect(page.getByText("None of your papers addresses this claim.")).toBeVisible();
  expect(api.calls.find((call) => call.path === "/write/claims")?.body).toMatchObject({ language: "en", item_ids: [] });
});

test("Urdu: every Write label is Urdu and the layout is right-to-left", async ({ page }) => {
  await page.addInitScript(() => { window.localStorage.setItem("resora-language", "ur"); window.localStorage.setItem("resora-language-source", "settings"); });
  await fakeApi(page);
  const content = ["Systematic review", "Peer-reviewed", "PRISMA", "PDF", "PNG", "SVG", "APA", "MLA", "Chicago", "Harvard", "IEEE", "Vancouver", "BibTeX", "Thesis chapter 2", "Introduction", "Decoding methods", ...ITEMS.flatMap((item) => [item.title, item.authors[0], item.venue])];
  for (const [path, ready] of [["/writing/screening/sc1?lang=ur", ".gw-record"], ["/writing/doc/d1?lang=ur", ".gw-section"], ["/writing/claims?lang=ur", ".gw-create"], ["/writing/reviews?lang=ur", ".lb-section"]] as const) {
    await page.goto(path);
    if (!path.includes("/doc/")) await expect(page.getByRole("heading", { name: "تحریر", level: 1 })).toBeVisible();
    await expect(page.locator(ready).first()).toBeVisible();
    await expect(page.locator(".gw-page")).toHaveAttribute("dir", "rtl");
    let rest = await page.locator(".gw-page").innerText();
    for (const item of [...content].sort((a, b) => b.length - a.length)) rest = rest.split(item).join(" ");
    expect([...new Set(rest.match(/[A-Za-z]{3,}/g) || [])], path).toEqual([]);
  }
});
