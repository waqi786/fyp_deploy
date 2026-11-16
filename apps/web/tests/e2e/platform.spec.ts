/**
 * Plans & usage (subscriptions, credit packs, sandbox checkout), Teams (create, invite link, shared project,
 * comments, supervisor review) and Research insights (catalog search, analytics, pipeline runs).
 * The API is a small in-memory fake so the flows and the requests they send are realistic. Urdu has no English labels.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const LIMITS = { free: { session: 25, week: 120, month: 300 }, pro: { session: 250, week: 1500, month: 5000 }, team: { session: 300, week: 2000, month: 7000 }, institution: { session: 400, week: 3000, month: 12000 } };
const PLANS = [
  { id: "free", rank: 0, checkout: false, per_seat: false, min_seats: 1, max_seats: 1, trial_days: 0, prices: { usd: { month: 0, year: 0 }, pkr: { month: 0, year: 0 } }, features: ["search", "library"], limits: LIMITS.free },
  { id: "pro", rank: 1, checkout: true, per_seat: false, min_seats: 1, max_seats: 1, trial_days: 7, prices: { usd: { month: 900, year: 9000 }, pkr: { month: 199900, year: 1999000 } }, features: ["everything_free", "research_mode"], limits: LIMITS.pro },
  { id: "team", rank: 2, checkout: true, per_seat: true, min_seats: 3, max_seats: 200, trial_days: 14, prices: { usd: { month: 700, year: 7000 }, pkr: { month: 149900, year: 1499000 } }, features: ["everything_pro", "shared_projects"], limits: LIMITS.team },
  { id: "institution", rank: 3, checkout: false, per_seat: true, min_seats: 25, max_seats: 100000, trial_days: 0, prices: { usd: { month: 0, year: 0 }, pkr: { month: 0, year: 0 } }, features: ["everything_team", "sso"], limits: LIMITS.institution },
];
const window = (scope: string, used: number, limit: number) => ({ scope, used, limit, remaining: limit - used, percent: used / limit, resets_at: "2026-11-15T12:00:00Z" });

async function fakeApi(page: Page) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  const state: any = { plan: "free", sub: null, invoices: [], topup: 0, session: null, teams: [], projects: [], papers: [], comments: [], reviews: [] };
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    // ---- billing
    if (path === "/billing/plans") return json({ plans: PLANS, packs: [{ id: "credits_100", credits: 100, prices: { usd: 300, pkr: 69900 } }], currencies: ["usd", "pkr"], provider: "sandbox", sandbox: true });
    if (path === "/billing/me") {
      const limits = (LIMITS as any)[state.plan];
      return json({ plan: state.plan, seats: 1, subscription: state.sub, usage: { plan: state.plan, pooled: false, windows: [window("session", 5, limits.session), window("week", 20, limits.week), window("month", 40, limits.month)], topup_balance: state.topup }, history: [{ day: "2026-11-14", action: "summary", credits: 4 }, { day: "2026-11-15", action: "chat", credits: 1 }], topup_balance: state.topup, provider: "sandbox", sandbox: true, costs: { search: 0, summary: 2, chat: 1, ask: 1, research: 5, translate_pages: 1 } });
    }
    if (path === "/billing/checkout") {
      state.session = { id: "cs_1", ...body, amount: body.kind === "topup" ? 300 : 9000, status: "open", expires_at: "2026-11-15T13:00:00Z", seats: body.seats || 1 };
      return json({ session_id: "cs_1", url: "/billing/checkout/cs_1", amount: state.session.amount, currency: body.currency });
    }
    if (path === "/billing/checkout/cs_1") return json(state.session);
    if (path === "/billing/sandbox/cs_1/complete") {
      state.session.status = "completed";
      if (state.session.kind === "topup") state.topup += 100;
      else {
        state.plan = state.session.plan;
        state.sub = { id: "sub_1", plan: state.plan, interval: state.session.interval, currency: state.session.currency, seats: 1, status: "trialing", current_period_start: "2026-11-15T00:00:00Z", current_period_end: "2026-11-22T00:00:00Z", trial_end: "2026-11-22T00:00:00Z", cancel_at_period_end: 0, provider: "sandbox" };
      }
      state.invoices.unshift({ id: "inv_1", number: "RS-202611-00001", kind: "topup", description: "100 credits", amount: 300, currency: "usd", status: "paid", created_at: "2026-11-15T00:00:00Z" });
      return json(state.session);
    }
    if (path === "/billing/subscription/cancel") { state.sub.cancel_at_period_end = 1; return json(state.sub); }
    if (path === "/billing/subscription/resume") { state.sub.cancel_at_period_end = 0; return json(state.sub); }
    if (path === "/billing/invoices") return json({ invoices: state.invoices });
    // ---- teams
    if (path === "/teams/notifications/me") return json({ notifications: [{ id: "n1", team_id: "t1", team_name: "Thesis lab", kind: "mention", payload: { by: "Prof Khan", excerpt: "check this" }, is_read: false, created_at: "2026-11-15T00:00:00Z" }] });
    if (path === "/teams/notifications/read") return json({ updated: 1 });
    if (path === "/teams" && request.method() === "GET") return json({ teams: state.teams });
    if (path === "/teams" && request.method() === "POST") {
      state.teams = [{ id: "t1", name: body.name, description: body.description, owner_id: "me", role: "owner", member_count: 2, project_count: 0, unread: 0, updated_at: "2026-11-15T00:00:00Z" }];
      return json({ id: "t1" }, 201);
    }
    const team = { id: "t1", name: state.teams[0]?.name || "Thesis lab", description: null, owner_id: "me", my_role: "owner", my_user_id: "me", members: [{ user_id: "me", role: "owner", display_name: "Rabia", joined_at: "2026-11-15T00:00:00Z" }, { user_id: "khan", role: "supervisor", display_name: "Prof Khan", joined_at: "2026-11-15T00:00:00Z" }], counts: { projects: state.projects.length, papers: state.papers.length, pending_reviews: state.reviews.filter((r: any) => r.status === "pending").length }, subscription: null };
    if (path === "/teams/t1") return json(team);
    if (path === "/teams/t1/invites" && request.method() === "POST") return json({ id: "inv1", role: body.role, token: "tok_abc", expires_at: "2026-11-22T00:00:00Z", max_uses: body.max_uses, uses: 0, revoked: 0, active: true }, 201);
    if (path === "/teams/t1/invites") return json({ invites: [] });
    if (path === "/teams/t1/projects" && request.method() === "POST") { state.projects = [{ id: "p1", name: body.name, paper_count: 0, done_count: 0, comment_count: 0, updated_at: "2026-11-15T00:00:00Z" }]; return json({ id: "p1" }, 201); }
    if (path === "/teams/t1/projects") return json({ projects: state.projects });
    const project = () => ({ ...state.projects[0], papers: state.papers });
    if (path === "/teams/t1/projects/p1/papers") { state.papers = [{ id: "pp1", title: "Attention is all you need", authors: ["A. Vaswani"], year: 2017, status: "to_read", assignee_id: null, added_by: "me", added_at: "2026-11-15T00:00:00Z", comment_count: 0 }]; return json({ added: 1, skipped: 0, project: project() }); }
    if (path === "/teams/t1/projects/p1/papers/pp1") { Object.assign(state.papers[0], body.clear_assignee ? { assignee_id: null } : body); return json(project()); }
    if (path === "/teams/t1/projects/p1") return json(project());
    if (path === "/teams/t1/comments" && request.method() === "POST") { const comment = { id: `c${state.comments.length + 1}`, author_id: "me", author_name: "Rabia", body: body.body, mentions: body.body.includes("@Prof Khan") ? ["khan"] : [], parent_id: body.parent_id || null, created_at: "2026-11-15T00:00:00Z", deleted: 0 }; state.comments.push({ ...comment, target_id: body.target_id }); return json(comment, 201); }
    if (path === "/teams/t1/comments") return json({ comments: state.comments.filter((c: any) => c.target_id === url.searchParams.get("target_id")) });
    if (path === "/teams/t1/reviews" && request.method() === "POST") { state.reviews = [{ id: "r1", document_id: body.document_id, title: "Introduction", requested_by: "me", requester_name: "Rabia", status: "pending", created_at: "2026-11-15T00:00:00Z", round: 1, snapshot: "# Introduction\n\nTransformers changed NLP [1].", can_decide: false }]; return json(state.reviews[0], 201); }
    if (path === "/teams/t1/reviews") return json({ reviews: state.reviews });
    if (path === "/teams/t1/reviews/r1") return json(state.reviews[0]);
    if (path === "/teams/t1/activity") return json({ activity: [{ id: "a1", actor_id: "me", actor_name: "Rabia", action: "team.created", summary: "Thesis lab", created_at: "2026-11-15T00:00:00Z" }] });
    if (path === "/teams/t1/usage") return json({ pooled: false, plan: "free", seats: 1, members: 2, usage: null, subscription: null });
    if (path === "/write/documents") return json([{ id: "d1", kind: "draft", title: "Introduction", style: "introduction", language: "en", updated_at: "2026-11-15T00:00:00Z", summary: { sections: 1, words: 10, sources: 1 } }]);
    if (path === "/library/items") return json([{ id: "i1", paper_key: "k1", title: "Attention is all you need", authors: ["A. Vaswani"], year: 2017, status: "to_read", tags: [], list_ids: [], important: false, read_later: false, source: "search", added_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" }]);
    // ---- research catalog
    if (path === "/catalog/overview") return json({ papers: 62, raw_records: 124, duplicates_merged: 62, duplicate_rate: 0.5, papers_per_source: { openalex: 40, crossref: 31, arxiv: 12, semantic_scholar: 20 }, unique_to_source: { openalex: 10 }, papers_by_source_count: { "1": 20, "2": 30, "3": 12 }, last_run: { run_id: "r1", status: "succeeded", started_at: "2026-11-15T00:00:00Z", finished_at: "2026-11-15T00:01:00Z", engine: "local", params: {}, stats: {} }, running: [], index: { papers: 62, embedder: "hash-v1", faiss: true } });
    if (path === "/catalog/analytics") return json({ paper_count: 62, publication_trends: [{ year: 2023, papers: 10, citations: 50, open_access: 4 }, { year: 2024, papers: 20, citations: 80, open_access: 9 }], topic_trends: [{ topic: "Computer vision", total: 30, by_year: {} }], hot_topics: [{ topic: "Diffusion models", status: "emerging", recent: 12, prior: 0, growth: 13, recent_years: [2024, 2025], prior_years: [2022, 2023] }], citation_patterns: { by_year: [], uncited_share: 0.2, top_decile_share: 0.4, most_cited: [{ paper_id: "rp_1", title: "Scalable transformer", year: 2020, citation_count: 400 }] }, gap_candidates: [{ topics: ["Robotics", "Healthcare"], papers_a: 15, papers_b: 15, together: 0, expected: 7.5, lift: 0, level: "moderate" }], collaboration: { top_authors: [{ name: "Ana Silva", papers: 5, citations: 100 }], top_institutions: [], median_team_size: 3 } });
    if (path === "/catalog/search") return json({ index_ready: true, results: [{ paper_id: "rp_9", title: "Federated learning for medical imaging", authors: [{ name: "Ana Silva" }], year: 2024, venue: "MICCAI", topics: [], citation_count: 33, is_open_access: true, sources: ["openalex", "crossref"], source_records: ["openalex:W1", "crossref:10.1/x"], duplicate_count: 1, match: { score: 0.03, matched: ["keyword", "semantic"] } }] });
    if (path === "/catalog/runs" && request.method() === "POST") return json({ run_id: "r2", status: "running" }, 202);
    if (path === "/catalog/runs") return json({ runs: [{ run_id: "r1", engine: "local", status: "succeeded", started_at: "2026-11-15T00:00:00Z", params: { queries: ["computer vision"] }, stats: { etl: { raw_records: 124, unique_papers: 62, duplicates_merged: 62 } } }] });
    return json({});
  });
  return { calls, state };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("resora-compare-owner", "e2e-owner");
    window.localStorage.setItem("resora-language-source", "settings");
    if (!window.localStorage.getItem("resora-language")) window.localStorage.setItem("resora-language", "en");
  });
});

test("pricing → sandbox checkout → plan active, usage meters, cancel and keep", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: "Plans and pricing", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "PKR", exact: true }).click();
  await expect(page.getByRole("article", { name: "Pro" })).toContainText("19,990");
  await page.getByRole("button", { name: "Monthly", exact: true }).click();
  await page.getByRole("article", { name: "Pro" }).getByRole("button", { name: "Start free trial" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/billing/checkout")?.body).toMatchObject({ kind: "subscription", plan: "pro", interval: "month", currency: "pkr" });
  await expect(page).toHaveURL(/\/billing\/checkout\/cs_1/);
  await page.getByRole("button", { name: "Pay now" }).click();
  await expect(page).toHaveURL(/\/usage/);
  await expect(page.getByRole("status").filter({ hasText: "Payment complete" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Pro/ })).toBeVisible();
  await expect(page.getByText("Free trial ·", { exact: false })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveCount(3);
  await expect(page.getByText("5 of 250 used")).toBeVisible();
  await page.getByRole("button", { name: "Cancel plan" }).click();
  await page.getByRole("button", { name: "Confirm cancel" }).click();
  await expect(page.getByRole("button", { name: "Keep my plan" })).toBeVisible();
  await expect(page.locator("select")).toHaveCount(0);
});

test("credit pack purchase shows the balance and the invoice", async ({ page }) => {
  await fakeApi(page);
  await page.goto("/pricing");
  await page.locator(".pf-pack").getByRole("button", { name: "Buy" }).click();
  await page.getByRole("button", { name: "Pay now" }).click();
  await expect(page).toHaveURL(/\/usage/);
  await expect(page.locator(".pf-stat").filter({ hasText: "Credits from packs" })).toContainText("100");
  await expect(page.locator(".gw-table").last()).toContainText("RS-202611-00001");
});

test("teams: create, invite link, shared project with comments and a supervisor review", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/teams");
  await expect(page.getByText("Prof Khan mentioned you")).toBeVisible();
  await page.getByLabel("Team name").fill("Thesis lab");
  await page.getByLabel("Your name in the team").fill("Rabia");
  await page.getByRole("button", { name: "Create team" }).click();
  await expect(page).toHaveURL(/\/teams\/t1/);
  await expect(page.getByRole("heading", { name: "Thesis lab" })).toBeVisible();

  await page.getByLabel("Project name").fill("Chapter 2");
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByRole("link", { name: "Chapter 2" }).click();
  await page.getByRole("button", { name: "Add from library" }).click();
  await page.getByRole("dialog").getByText("Attention is all you need").click();
  await page.getByRole("button", { name: "Add 1" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Added 1" })).toBeVisible();
  await page.getByRole("button", { name: /^Assigned to:/ }).click();
  await page.getByRole("option", { name: "Prof Khan" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/teams/t1/projects/p1/papers/pp1")?.body).toEqual({ assignee_id: "khan" });
  await page.getByRole("button", { name: "Comments (0)" }).click();
  await page.locator(".pf-paper textarea").fill("@Prof Khan is this the right baseline?");
  await page.locator(".pf-paper").getByRole("button", { name: "Send" }).click();
  await expect(page.locator(".pf-paper .pf-mention")).toHaveText("@Prof Khan");

  await page.getByRole("link", { name: "Reviews" }).click();
  await page.getByRole("button", { name: "Send for review" }).click();
  await expect(page).toHaveURL(/\/teams\/t1\/reviews\/r1/);
  await expect(page.locator(".pf-snapshot")).toContainText("Transformers changed NLP");

  await page.getByRole("link", { name: /Members/ }).click();
  await page.getByRole("button", { name: "Create link" }).click();
  await expect(page.getByLabel("Invite link")).toHaveValue(/\/join\/tok_abc$/);
  await page.getByRole("link", { name: "Activity" }).click();
  await expect(page.getByText("created the team")).toBeVisible();
  await expect(page.locator("select")).toHaveCount(0);
});

test("research insights: catalog stats, hybrid search with match reasons, evidence-based gaps, start a run", async ({ page }) => {
  const api = await fakeApi(page);
  await page.goto("/insights");
  await expect(page.getByRole("heading", { name: "Research insights", level: 1 })).toBeVisible();
  await expect(page.locator(".pf-stat").filter({ hasText: "Duplicates merged" })).toContainText("50%");
  await expect(page.getByText("Diffusion models")).toBeVisible();
  await expect(page.locator(".pf-gap")).toContainText("Robotics");
  await page.getByRole("searchbox", { name: "Search the catalog" }).or(page.getByRole("textbox", { name: "Search the catalog" })).first().fill("federated learning medical imaging");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Federated learning for medical imaging")).toBeVisible();
  await expect(page.locator(".pf-match-badge")).toHaveText(["Keyword match", "Meaning match"]);
  await page.getByRole("textbox", { name: "Topics", exact: true }).fill("graph neural networks");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect.poll(() => api.calls.find((call) => call.path === "/catalog/runs" && call.method === "POST")?.body).toMatchObject({ queries: ["graph neural networks"], engine: "local" });
});

test("Urdu: Pricing, Usage, Teams and Insights show no English labels and are right-to-left", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("resora-language", "ur"));
  await fakeApi(page);
  const allowed = ["Resora", "USD", "PKR", "OpenAlex", "arXiv", "Crossref", "Semantic Scholar", "Thesis lab", "Prof Khan", "Rabia", "Computer vision", "Diffusion models", "Robotics", "Healthcare", "Ana Silva", "Scalable transformer", "computer vision", "check this", "RS-202611-00001", "AI", "PDF", "LaTeX", "BibTeX", "DOI"];
  for (const [path, ready] of [["/pricing", ".pf-plan"], ["/usage", ".pf-meter"], ["/teams", ".pf-teams-home"], ["/insights", ".pf-stat"]] as const) {
    await page.goto(path);
    await expect(page.locator(ready).first()).toBeVisible();
    await expect(page.locator(".pf-page")).toHaveAttribute("dir", "rtl");
    let text = await page.locator(".pf-page").innerText();
    for (const item of [...allowed].sort((a, b) => b.length - a.length)) text = text.split(item).join(" ");
    expect([...new Set(text.match(/[A-Za-z]{3,}/g) || [])], path).toEqual([]);
  }
});

test("mobile: plans and teams fit a phone without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeApi(page);
  for (const path of ["/pricing", "/usage", "/teams", "/insights"]) {
    await page.goto(path);
    await expect(page.locator(".pf-page")).toBeVisible();
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});
