/**
 * Admin console (role enforced by the server, metrics, users, credit grants, suspension, flags, failed jobs,
 * incidents, audit) and the public website (landing, help, contact, status, legal, invites, cookie notice).
 * Every API call is mocked with a small in-memory fake.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const overview = {
  mrr: { usd: 2700, pkr: 199900 }, revenue_30d: { usd: 9000 }, subscriptions: { active: 3, trialing: 2 }, plans: { pro: 4, team: 1 }, paying: 3, trialing: 2,
  churn_risk: 1, churn_risk_rate: 0.333, signups_30d: 12, activation_rate: 0.5, active_users_7d: 9, active_users_30d: 20,
  credits_by_action_30d: { summary: 120, chat: 40 }, credits_by_day: [], credit_packs_sold: 600,
  traffic: { pageviews: 340, visitors: 120, by_day: [], top_paths: [{ path: "/welcome", views: 90 }], top_referrers: [{ referrer: "google.com", views: 40 }], devices: { desktop: 200 } },
  referrals: { redemptions: 5, codes: 9 }, waitlist: { confirmed: 7, pending: 2 }, open_messages: 1,
};

async function fakeApi(page: Page, options: { admin?: boolean } = { admin: true }) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  const state = { suspended: false, flags: [{ key: "growth.referrals", description: "Referral credits", enabled: true, rollout: 100, allow_users: [], updated_by: "system", updated_at: "2026-11-15T00:00:00Z" }], incidents: [] as any[], deadStatus: "failed", redeemed: null as string | null };
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path.startsWith("/admin/") && !options.admin) return json({ detail: { code: "forbidden" } }, 403);
    if (path === "/admin/me") return json({ user_id: "root", admin: true });
    if (path === "/admin/overview") return json(overview);
    if (path === "/admin/users") return json({ total: 2, users: [
      { user_id: "u-alice", display_name: "Alice", plan: "pro", subscription_status: "active", seats: 1, credits_30d: 80, topup_balance: 0, teams: 1, suspended: false, first_seen: "2026-10-01T00:00:00Z", last_seen: "2026-11-14T00:00:00Z" },
      { user_id: "u-bob", display_name: "", plan: "free", subscription_status: null, seats: 1, credits_30d: 5, topup_balance: 40, teams: 0, suspended: state.suspended, first_seen: null, last_seen: null },
    ].filter((row) => !url.searchParams.get("q") || row.user_id.includes(url.searchParams.get("q")!)) });
    if (path === "/admin/users/u-bob") return json({ user_id: "u-bob", plan: "free", seats: 1, usage: { windows: [{ scope: "session", used: 5, limit: 25, remaining: 20, percent: 0.2, resets_at: "2026-11-15T12:00:00Z" }, { scope: "week", used: 5, limit: 120, remaining: 115, percent: 0.04, resets_at: "2026-11-20T00:00:00Z" }, { scope: "month", used: 5, limit: 300, remaining: 295, percent: 0.02, resets_at: "2026-12-01T00:00:00Z" }], topup_balance: 40 }, history: [{ day: "2026-11-14", action: "summary", credits: 4 }], invoices: [], credit_grants: [], teams: [], suspended: state.suspended, suspension_reason: state.suspended ? "abuse" : null, audit: [] });
    if (path === "/admin/users/u-bob/credits") return json({ user_id: "u-bob", credits: body.credits, balance: 40 + body.credits });
    if (path === "/admin/users/u-bob/suspension") { state.suspended = body.suspended; return json({ user_id: "u-bob", suspended: body.suspended }); }
    if (path === "/admin/providers") return json({ ai: { groq: { configured: true, healthy: true, cooldown_seconds: 0, daily_quota: { limit: 1000, used: 10, remaining: 990 }, last_probe: { checked_at: "2026-11-15T00:00:00Z" } }, gemini: { configured: false, healthy: true, cooldown_seconds: 0, daily_quota: { limit: null, used: 0, remaining: null }, last_probe: {} } }, routes: { summary: ["groq:llama"] }, tts: { engines: { kokoro: { configured: false, healthy: false, failures: 0 } }, metrics: { requests: 0, cache_hits: 0 } }, voices: [] });
    if (path === "/admin/providers/groq/probe") return json({ configured: true, healthy: true, reason: "ok" });
    if (path === "/admin/flags" ) return json({ flags: state.flags });
    if (path.startsWith("/admin/flags/")) { const key = decodeURIComponent(path.split("/").pop()!); const flag = { key, description: body.description || "", enabled: body.enabled, rollout: body.rollout, allow_users: [], updated_by: "root", updated_at: "2026-11-15T00:00:00Z" }; state.flags = [...state.flags.filter((f) => f.key !== key), flag]; return json(flag); }
    if (path === "/admin/jobs") return json({ pipeline_runs: [{ run_id: "run_1", engine: "local", status: "succeeded", started_at: "2026-11-15T00:00:00Z", params: { queries: ["vision"] } }], dead_letters: [{ id: "dl_1", kind: "billing_webhook", source: "stripe", error: "RuntimeError: database is locked", attempts: 1, status: state.deadStatus, created_at: "2026-11-15T00:00:00Z", updated_at: "2026-11-15T00:00:00Z" }] });
    if (path === "/admin/jobs/dead-letters/dl_1/retry") { state.deadStatus = "resolved"; return json({ id: "dl_1", status: "resolved" }); }
    if (path === "/admin/messages") return json({ messages: [{ id: "m1", name: "Sara", email: "sara@example.org", topic: "billing", message: "Please help with my invoice.", language: "en", status: "open", created_at: "2026-11-15T00:00:00Z" }] });
    if (path === "/admin/messages/m1/status") return json({ id: "m1", status: body.status });
    if (path === "/admin/incidents" && request.method() === "POST") { const incident = { id: "inc_1", ...body, created_at: "2026-11-15T00:00:00Z", updated_at: "2026-11-15T00:00:00Z", resolved_at: null }; state.incidents = [incident]; return json(incident, 201); }
    if (path === "/admin/incidents") return json({ incidents: state.incidents });
    if (path === "/admin/audit") return json({ entries: [{ id: "a1", actor_id: "root", action: "user.grant_credits", target: "u-bob", detail: { credits: 25 }, created_at: "2026-11-15T00:00:00Z" }] });
    if (path === "/site/status") return json({ overall: state.incidents.length ? "partial_outage" : "operational", components: { search: "operational", reader: "operational", listen: "operational", billing: "operational", ai: state.incidents.length ? "partial_outage" : "operational", catalog: "operational", website: "operational" }, incidents: state.incidents, checked_at: "2026-11-15T00:00:00Z" });
    if (path === "/site/newsletter") return body.consent ? json({ status: "pending" }) : json({ detail: { code: "consent_required" } }, 422);
    if (path === "/site/contact") return json({ id: "msg_1", status: "received" }, 201);
    if (path === "/site/pageview") return route.fulfill({ status: 204 });
    if (path === "/site/referral") return json({ code: "ABCD2345", invited: 2, rewarded: 2, credits_earned: 100, credits_per_referral: 50, max_rewards: 20, redeemed_code: state.redeemed });
    if (path === "/site/referral/redeem") { if (body.code === "SELF0000") return json({ detail: { code: "referral_self" } }, 409); state.redeemed = body.code; return json({ credits: 50, balance: 50 }); }
    if (path === "/billing/plans") return json({ plans: [{ id: "pro", rank: 1, checkout: true, per_seat: false, min_seats: 1, max_seats: 1, trial_days: 7, prices: { usd: { month: 900, year: 9000 }, pkr: { month: 199900, year: 1999000 } }, features: [], limits: { session: 250, week: 1500, month: 5000 } }], packs: [], currencies: ["usd", "pkr"], provider: "sandbox", sandbox: true });
    return json({});
  });
  return { calls, state };
}

async function setLanguage(page: Page, language = "en", cookieSeen = true) {
  await page.addInitScript(([code, seen]) => {
    window.localStorage.setItem("resora-language", code as string);
    window.localStorage.setItem("resora-language-source", "settings");
    window.localStorage.setItem("resora-compare-owner", "root");
    if (seen) window.localStorage.setItem("resora-cookie-notice", "2026-11-15");
  }, [language, cookieSeen] as const);
}

test("admin console is closed to non-admins (server decides)", async ({ page }) => {
  await setLanguage(page);
  await fakeApi(page, { admin: false });
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Admin access only" })).toBeVisible();
  await expect(page.getByText("Monthly recurring revenue")).toHaveCount(0);
});

test("admin: metrics, users → grant credits and suspend, flags, failed-job retry, incident publishing, audit log", async ({ page }) => {
  await setLanguage(page);
  const { calls } = await fakeApi(page);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Admin console", level: 1 })).toBeVisible();
  await expect(page.locator(".pf-stat").filter({ hasText: "Monthly recurring revenue" })).toContainText("$27");
  await expect(page.locator(".pf-stat").filter({ hasText: "Active users, 7 days" })).toContainText("9");
  await expect(page.getByText("340 page views from 120 visitors", { exact: false })).toBeVisible();

  await page.getByRole("link", { name: "Users" }).click();
  await page.getByLabel("Search by account or name").fill("bob");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("link", { name: "Alice" })).toHaveCount(0);
  await page.getByRole("link", { name: "u-bob" }).click();
  await expect(page.getByRole("progressbar")).toHaveCount(3);
  await page.getByRole("spinbutton", { name: "Credits" }).fill("25");
  await page.getByLabel("Reason").first().fill("Support goodwill");
  await page.getByRole("button", { name: "Grant", exact: true }).click();
  await expect.poll(() => calls.find((call) => call.path === "/admin/users/u-bob/credits")?.body).toEqual({ credits: 25, reason: "Support goodwill" });
  await expect(page.getByRole("status").filter({ hasText: "Credits granted." })).toBeVisible();
  await page.getByRole("button", { name: "Suspend account" }).click();
  await expect.poll(() => calls.find((call) => call.path === "/admin/users/u-bob/suspension")?.body).toMatchObject({ suspended: true });
  await expect(page.getByRole("button", { name: "Restore access" })).toBeVisible();

  await page.getByRole("link", { name: "AI providers" }).click();
  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The provider answered." })).toBeVisible();

  await page.getByRole("link", { name: "Feature flags" }).click();
  await page.getByRole("checkbox").first().uncheck();
  await expect.poll(() => calls.find((call) => call.path === "/admin/flags/growth.referrals")?.body).toMatchObject({ enabled: false, rollout: 100 });
  await page.getByPlaceholder("new.flag_key").fill("beta.compare_v2");
  await page.getByPlaceholder("What it controls").fill("New compare");
  await page.getByRole("button", { name: "Add flag" }).click();
  await expect(page.getByText("beta.compare_v2")).toBeVisible();

  await page.getByRole("link", { name: "Jobs" }).click();
  await expect(page.getByText("database is locked")).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The job ran successfully." })).toBeVisible();

  await page.getByRole("link", { name: "Status" }).click();
  await page.getByLabel("Title").fill("Slow summaries");
  await page.getByRole("radio", { name: "AI answers and summaries" }).click();
  await page.getByRole("radio", { name: "Major" }).click();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect.poll(() => calls.find((call) => call.path === "/admin/incidents" && call.method === "POST")?.body).toMatchObject({ title: "Slow summaries", component: "ai", severity: "major", status: "investigating" });

  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByText("user.grant_credits")).toBeVisible();
  await expect(page.locator("select")).toHaveCount(0);

  await page.goto("/status");
  await expect(page.getByRole("status").filter({ hasText: "Partly unavailable" })).toBeVisible();
  await expect(page.getByText("Slow summaries")).toBeVisible();
});

test("landing: hero search, features, pricing teaser from the plan catalog, FAQ, newsletter consent", async ({ page }) => {
  await setLanguage(page);
  const { calls } = await fakeApi(page);
  await page.goto("/welcome");
  await expect(page.getByRole("heading", { name: "Find, understand and write research — in your language.", level: 1 })).toBeVisible();
  await expect(page.locator(".site-card")).toHaveCount(9);
  await expect(page.locator(".site-pricing-teaser")).toContainText("$9");
  await page.getByRole("button", { name: "What are credits?" }).click();
  await expect(page.getByText("Credits measure AI work", { exact: false })).toBeVisible();
  await page.getByLabel("E-mail").fill("me@uni.edu");
  await page.getByRole("button", { name: "Subscribe" }).click();
  await expect(page.getByRole("alert")).toHaveText("Please tick the box to agree to receive e-mails.");
  await page.getByText("Send me occasional updates", { exact: false }).click();
  await page.getByRole("button", { name: "Subscribe" }).click();
  await expect(page.getByRole("status").filter({ hasText: "check your inbox" })).toBeVisible();
  expect(calls.filter((call) => call.path === "/site/newsletter").at(-1)?.body).toMatchObject({ email: "me@uni.edu", consent: true, source: "landing" });
  await expect.poll(() => calls.some((call) => call.path === "/site/pageview" && call.body?.path === "/welcome")).toBe(true);
  await expect(page).toHaveTitle(/Resora/);
  expect(await page.locator('link[rel="alternate"][hreflang="ur"]').getAttribute("href")).toContain("/welcome?lang=ur");
  await page.getByLabel("Try a topic", { exact: false }).fill("graph neural networks");
  await page.getByRole("button", { name: "Start free" }).first().click();
  await expect(page).toHaveURL(/\/search\?q=graph%20neural%20networks/);
});

test("help center search, contact form (honeypot empty), legal pages, invite credits", async ({ page }) => {
  await setLanguage(page);
  const { calls } = await fakeApi(page);
  await page.goto("/help");
  await page.getByLabel("Search the help center").fill("cancel");
  await expect(page.locator(".site-faq-item")).toHaveCount(1);
  await expect(page.getByText("Your plan stays active until the end", { exact: false })).toBeVisible();

  await page.goto("/contact");
  await page.getByLabel("Your name").fill("Sara");
  await page.getByLabel("E-mail").fill("sara@example.org");
  await page.getByRole("radio", { name: "Billing" }).click();
  await page.getByLabel("Message").fill("Please help with my invoice number 12.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("status").filter({ hasText: "your message was sent" })).toBeVisible();
  expect(calls.find((call) => call.path === "/site/contact")?.body).toMatchObject({ name: "Sara", email: "sara@example.org", topic: "billing", website: "" });

  await page.goto("/legal/privacy");
  await expect(page.getByRole("heading", { name: "Privacy Policy", level: 1 })).toBeVisible();
  await page.getByRole("link", { name: "Refund Policy" }).first().click();
  await expect(page.getByRole("heading", { name: "Refund Policy", level: 1 })).toBeVisible();

  await page.goto("/invite");
  await expect(page.getByRole("textbox", { name: "Your invite link" })).toHaveValue(/\/invite\?code=ABCD2345$/);
  await expect(page.getByText("2 colleagues joined · 100 credits earned")).toBeVisible();
  await page.getByRole("textbox", { name: "Invite code", exact: true }).fill("self0000");
  await page.getByRole("button", { name: "Use code" }).click();
  await expect(page.getByRole("status").filter({ hasText: "You cannot use your own invite code." })).toBeVisible();
  await page.getByRole("textbox", { name: "Invite code", exact: true }).fill("FRIEND22");
  await page.getByRole("button", { name: "Use code" }).click();
  await expect(page.getByText("You joined with code FRIEND22", { exact: false })).toBeVisible();
});

test("cookie notice appears once on public pages and never on the app", async ({ page }) => {
  await setLanguage(page, "en", false);
  await fakeApi(page);
  await page.goto("/search");
  await expect(page.getByRole("dialog", { name: "No tracking cookies." })).toHaveCount(0);
  await page.goto("/welcome");
  const notice = page.getByRole("dialog", { name: "No tracking cookies." });
  await expect(notice).toBeVisible();
  await notice.getByRole("button", { name: "Got it" }).click();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(notice).toHaveCount(0);
  await page.getByRole("button", { name: "Cookie notice" }).click();
  await expect(notice).toBeVisible();
});

test("Urdu: landing, help, status, invite and admin show no English labels and are right-to-left", async ({ page }) => {
  test.setTimeout(90_000);
  await setLanguage(page, "ur");
  await fakeApi(page);
  const allowed = ["Resora", "AI", "PDF", "BibTeX", "English", "Español", "you@university.edu", "groq", "gemini", "summary", "chat", "pro", "team", "google.com", "welcome", "ABCD2345", "llama", "Slow summaries", "kokoro"];
  for (const [path, ready] of [["/welcome", ".site-hero"], ["/help", ".site-faq"], ["/status", ".site-components"], ["/invite", "#ref-link"], ["/admin", ".pf-stat"], ["/admin/providers", ".gw-table"]] as const) {
    await page.goto(path);
    await expect(page.locator(ready).first()).toBeVisible();
    await expect(page.locator(".pf-page").first()).toHaveAttribute("dir", "rtl");
    let text = await page.locator(".pf-page").first().innerText();
    for (const item of [...allowed].sort((a, b) => b.length - a.length)) text = text.split(item).join(" ");
    expect([...new Set(text.match(/[A-Za-z]{3,}/g) || [])], path).toEqual([]);
  }
});

test("phone: public pages and the admin console fit without sideways scrolling", async ({ page }) => {
  test.setTimeout(120_000); // visits eleven pages
  await page.setViewportSize({ width: 390, height: 844 });
  await setLanguage(page);
  await fakeApi(page);
  for (const path of ["/welcome", "/features", "/help", "/contact", "/status", "/changelog", "/legal/terms", "/invite", "/admin", "/admin/flags", "/admin/jobs"]) {
    await page.goto(path);
    await expect(page.locator(".pf-page").first()).toBeVisible();
    await page.waitForTimeout(250);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});
