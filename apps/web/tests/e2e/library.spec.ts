/**
 * Library tab: saved papers (status, filters, bulk), projects, citations (styles, export, import), Ask with sources,
 * Urdu with no English labels, and saving from Search. The API is a small in-memory fake, so flows are realistic.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

type Item = Record<string, unknown> & { id: string; title: string; status: string; tags: string[]; list_ids: string[]; important: boolean; read_later: boolean };

function makeItem(id: string, title: string, extra: Partial<Item> = {}): Item {
  return { id, paper_key: `title:${id}`, title, authors: ["Ayesha Rahman", "Li Wei", "Marta Costa"], year: 2024, venue: "CVPR", doi: null, source: "search", status: "to_read", important: false, read_later: false, tags: [], list_ids: [], added_at: "2026-10-30T10:00:00+00:00", updated_at: "2026-10-30T10:00:00+00:00", ...extra };
}

async function fakeApi(page: Page) {
  const state = {
    items: [
      makeItem("i1", "Grounded decoding reduces object hallucination", { tags: ["decoding"], abstract: "Grounding lowers hallucination." }),
      makeItem("i2", "Contrastive decoding for faithful captions", { year: 2023, venue: "NeurIPS", status: "reading" }),
      makeItem("i3", "Attention Is All You Need", { year: 2017, status: "read", read_later: true, authors: ["Ashish Vaswani"] }),
    ] as Item[],
    lists: [] as Array<Record<string, unknown>>,
    calls: [] as Array<{ method: string; path: string; body: unknown }>,
  };
  const counts = () => ({ saved: state.items.length, to_read: state.items.filter((item) => item.status === "to_read").length, reading: 1, read: 1, important: state.items.filter((item) => item.important).length, read_later: state.items.filter((item) => item.read_later).length, notes: 0, ideas: 0, tasks_open: 0, tasks_overdue: 0, projects: state.lists.length, collections: 0 });
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() ? request.postDataJSON() : null;
    state.calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path === "/library/overview") return json({ counts: counts(), tags: [{ tag: "decoding", count: 1 }] });
    if (path === "/library/items" && request.method() === "GET") return json(state.items);
    if (path === "/library/items" && request.method() === "POST") {
      const added = (body.papers as Array<{ title: string }>).map((paper, index) => makeItem(`n${state.items.length + index}`, paper.title, { source: body.source }));
      state.items.unshift(...added);
      return json({ items: added, already_saved: [] });
    }
    if (path === "/library/items/lookup") return json({ item_ids: (body.papers as unknown[]).map(() => null) });
    if (path === "/library/items/bulk") {
      state.items = state.items.map((item) => (body.ids.includes(item.id) && body.action === "set_status" ? { ...item, status: body.value } : body.ids.includes(item.id) && body.action === "add_to_list" ? { ...item, list_ids: [...item.list_ids, body.value] } : item));
      return json({ updated: body.ids.length });
    }
    const itemMatch = path.match(/^\/library\/items\/(\w+)$/);
    if (itemMatch && request.method() === "PATCH") {
      const index = state.items.findIndex((item) => item.id === itemMatch[1]);
      const { opened: _opened, ...changes } = body;
      state.items[index] = { ...state.items[index], ...changes };
      return json(state.items[index]);
    }
    if (path === "/library/lists" && request.method() === "GET") return json(state.lists);
    if (path === "/library/lists" && request.method() === "POST") {
      const list = { id: `p${state.lists.length + 1}`, kind: body.kind, name: body.name, description: body.description, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", item_count: 0, stats: { papers: 0, to_read: 0, important: 0, notes: 0, ideas: 0, tasks_open: 0 } };
      state.lists.push(list);
      return json(list);
    }
    const listMatch = path.match(/^\/library\/lists\/(\w+)$/);
    if (listMatch) return json({ ...state.lists.find((list) => list.id === listMatch[1]), item_ids: state.items.filter((item) => item.list_ids.includes(listMatch[1])).map((item) => item.id) });
    if (path === "/library/citations/format") {
      const text = body.style === "ieee" ? "[1] A. Rahman, L. Wei, and M. Costa, “Grounded decoding reduces object hallucination,” CVPR, 2024." : "Rahman, A., Wei, L., & Costa, M. (2024). Grounded decoding reduces object hallucination. CVPR.";
      return json({ style: body.style, entries: [{ id: "i1", text, parts: [{ text: text.replace("CVPR.", ""), italic: false }, { text: "CVPR", italic: true }, { text: ".", italic: false }] }] });
    }
    if (path === "/library/citations/export") return json({ content: "@article{rahman2024grounded,\n  title = {{Grounded decoding}}\n}\n", filename: "resora-library.bib", mime: "application/x-bibtex", count: 3 });
    if (path === "/library/citations/import") return json({ format: "ids", added: 1, already_saved: 1, items: [], not_found: ["2301.01234"] });
    if (path === "/library/ask") return json({ mode: "answer", answer: "Grounding image regions lowers hallucination [1].", not_found: false, window_applied: false, credits_used: 1, sources: [{ n: 1, kind: "paper", id: "i1", title: state.items[0].title, snippet: "Grounding lowers hallucination." }] });
    if (path === "/library/notes" || path === "/library/tasks") return json([]);
    if (path.startsWith("/search/")) return json({});
    return json({});
  });
  return state;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("resora-compare-owner", "e2e-owner"));
});

test("saved papers: status, filters and bulk actions", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/library");
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
  await expect(page.locator(".lb-row")).toHaveCount(3);
  await expect(page.getByRole("link", { name: /Saved/ })).toHaveClass(/is-active/);

  // Change one paper's status from its pill.
  const first = page.locator(".lb-row").filter({ hasText: "Grounded decoding" });
  await first.getByRole("button", { name: "To read" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Read", exact: true }).click();
  await expect(first.getByRole("button", { name: "Read" })).toBeVisible();
  expect(api.calls.find((call) => call.method === "PATCH")?.body).toEqual({ status: "read" });

  // Filter by status.
  await page.getByRole("group", { name: "Reading status" }).getByRole("button", { name: "Reading", exact: true }).click();
  await expect(page.locator(".lb-row")).toHaveCount(1);
  await page.getByRole("group", { name: "Reading status" }).getByRole("button", { name: "All" }).click();

  // Bulk: select two, mark as read.
  await page.getByLabel("Select Contrastive decoding for faithful captions").check();
  await page.getByLabel("Select Attention Is All You Need").check();
  const bulk = page.getByRole("region", { name: "Selected papers" });
  await expect(bulk.getByText("2 selected")).toBeVisible();
  await bulk.getByRole("button", { name: "Mark as" }).click();
  await page.getByRole("menuitem", { name: "Reading" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/library/items/bulk")?.body).toEqual({ ids: ["i2", "i3"], action: "set_status", value: "reading" });

  // Read later tab shows only queued papers.
  await page.getByRole("link", { name: /Read later/ }).click();
  await expect(page).toHaveURL(/\/library\/read-later$/);
  await expect(page.locator(".lb-row")).toHaveCount(1);
});

test("projects: create one and land on its overview", async ({ page }) => {
  await fakeApi(page);
  await page.goto("/library/projects");
  await expect(page.getByText("No projects yet")).toBeVisible();
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Project name").fill("Hallucination thesis");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/library\/projects\/p1$/);
  await expect(page.getByRole("heading", { name: "Hallucination thesis" })).toBeVisible();
  await expect(page.getByLabel("Overview").getByText("Open tasks")).toBeVisible();
  await expect(page.getByText("No papers in this project yet")).toBeVisible();
});

test("citations: switch style, export a file, import identifiers", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/library/citations");
  await expect(page.locator(".lb-bibliography li").first()).toContainText("Rahman, A., Wei, L., & Costa, M. (2024).");
  await expect(page.locator(".lb-bibliography i").first()).toHaveText("CVPR");
  await page.getByRole("button", { name: "IEEE" }).click();
  await expect(page.locator(".lb-bibliography li").first()).toContainText("[1] A. Rahman");

  await page.getByRole("button", { name: "Export" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "BibTeX (.bib)" }).click();
  expect((await download).suggestedFilename()).toBe("resora-library.bib");
  expect(api.calls.find((call) => call.path === "/library/citations/export")?.body).toEqual({ format: "bibtex", style: "ieee" });

  await page.locator(".lb-toolbar").getByRole("button", { name: "Import" }).click();
  const dialog = page.getByRole("dialog", { name: "Import references" });
  await dialog.getByLabel("Or paste DOIs / arXiv IDs, one per line").fill("10.1038/nature12373\n2301.01234");
  await dialog.getByRole("button", { name: "Import", exact: true }).click();
  await expect(dialog.getByText("Already in your library: 1")).toBeVisible();
  await expect(dialog.getByText("Could not find: 2301.01234")).toBeVisible();
});

test("ask your library: grounded answer with numbered sources that open the paper", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/library");
  await page.getByLabel("Ask your library").fill("Which paper reduces hallucination?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const answer = page.getByRole("region", { name: "Answer from your library" });
  await expect(answer.getByText("Grounding image regions lowers hallucination")).toBeVisible();
  await expect(answer.getByText("Based only on your saved papers and notes.")).toBeVisible();
  await answer.getByRole("button", { name: /^Open source 1/ }).click();
  // The paper opens in the Reader with its saved details (title, authors, abstract).
  await expect.poll(() => api.calls.some((call) => call.path.startsWith("/reader") && JSON.stringify(call.body || "").includes("Grounded decoding reduces object hallucination"))).toBe(true);
});

test("Urdu: every Library label is Urdu and the layout is right-to-left", async ({ page }) => {
  await page.addInitScript(() => { window.localStorage.setItem("resora-language", "ur"); window.localStorage.setItem("resora-language-source", "settings"); });
  await fakeApi(page);
  await page.goto("/library?lang=ur");
  await expect(page.getByRole("heading", { name: "لائبریری" })).toBeVisible();
  await expect(page.locator(".lb-library")).toHaveAttribute("dir", "rtl");
  const text = await page.locator(".lb-library").innerText();
  const content = ["Grounded decoding reduces object hallucination", "Contrastive decoding for faithful captions", "Attention Is All You Need", "Ayesha Rahman", "Ashish Vaswani", "CVPR", "NeurIPS", "decoding"];
  let rest = text;
  for (const item of content) rest = rest.split(item).join(" ");
  expect([...new Set(rest.match(/[A-Za-z]{3,}/g) || [])]).toEqual([]);
});

test("saving a paper in Search puts it in the Library", async ({ page }) => {
  const api = await fakeApi(page);
  await page.route("**/api/v1/search/stream**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ query: "q", total_results: 1, papers: [{ paper_id: "s1", title: "A searched paper", abstract: "Abstract text that is long enough.", year: 2025, venue: "ACL", citation_count: 3, source: "research", authors: [{ name: "Sara Ali" }], result_badges: [], datasets: [], methodologies: [], code_repositories: [], matched_terms: [] }], pagination: { page: 1, has_next_page: false } }) }));
  await page.goto("/search");
  await page.getByRole("searchbox").first().fill("captions");
  await page.keyboard.press("Enter");
  await expect(page.locator(".rs-card")).toHaveCount(1);
  await page.locator(".rs-card").getByRole("button", { name: /^Save/ }).first().click();
  await expect.poll(() => api.calls.find((call) => call.path === "/library/items" && call.method === "POST")?.body).toMatchObject({ source: "search", papers: [{ title: "A searched paper", authors: ["Sara Ali"], year: 2025 }] });
});

test("project 'For you': suggestions with a checkable reason, saved into the project; no native selects", async ({ page }) => {
  const api = await fakeApi(page);
  api.lists.push({ id: "p9", kind: "project", name: "Hallucination", description: "", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", item_count: 2, stats: { papers: 2, to_read: 2, important: 0, notes: 0, ideas: 0, tasks_open: 0 } });
  api.items[0].list_ids = ["p9"];
  api.items[1].list_ids = ["p9"];
  const searched: unknown[] = [];
  await page.route("**/api/v1/search/", async (route) => {
    searched.push(route.request().postDataJSON());
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ papers: [{ paper_id: "r1", title: "Region grounding for faithful captions", abstract: "Grounding on POPE.", year: 2025, venue: "ICLR", authors: [{ name: "Hana Kim" }] }] }) });
  });
  let recommendBody: any = null;
  await page.route("**/api/v1/gap/recommendations", async (route) => {
    recommendBody = route.request().postDataJSON();
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ recommendations: [{ paper_id: "r1", reason: { kind: "same_dataset", paper_title: "Grounded decoding reduces object hallucination", label: "POPE" } }] }) });
  });
  await page.goto("/library/projects/p9");
  await page.getByRole("tab", { name: "For you" }).click();
  await expect(page.getByText("Region grounding for faithful captions")).toBeVisible();
  await expect(page.getByText("Uses POPE, like “Grounded decoding reduces object hallucination”")).toBeVisible();
  expect(recommendBody.saved.map((paper: { id: string }) => paper.id).sort()).toEqual(["i1", "i2"]);
  expect(searched.length).toBeGreaterThan(0);
  await page.locator(".lb-rec").getByRole("button", { name: "Save" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/library/items" && call.method === "POST")?.body).toMatchObject({ list_id: "p9", papers: [{ title: "Region grounding for faithful captions" }] });

  // Dropdowns are token-styled listboxes, never native <select>.
  await page.getByRole("tab", { name: "Tasks" }).click();
  await page.goto("/library/notes");
  await expect(page.locator("select")).toHaveCount(0);
});
