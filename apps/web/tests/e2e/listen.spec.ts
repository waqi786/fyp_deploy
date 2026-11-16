/**
 * Listen (Part 12A): the persistent mini-player. A fake device voice records every utterance, so the tests check
 * what is spoken, in which language and at which speed, without audio. Every API call is mocked.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const doc = {
  id: "c1f680d4c8347439b98d6b8c", title: "Grounded decoding for vision-language models", authors: ["A. Rahman", "L. Chen"], year: 2024, venue: "CVPR",
  doi: "10.1000/example.1", url: null, abstract: "A training-free decoding method.", source: "upload", has_pdf: false, page_count: 3, word_count: 900,
  reading_minutes: 4, scanned_pages: [], captions: [], is_open_access: true, citation_count: 412,
};
const pages = [
  { page: 1, text: "Abstract\n\nWe propose grounded decoding. It needs no training." },
  { page: 2, text: "3 Method\n\nTokens are re-weighted by visual evidence." },
  { page: 3, text: "5 Results\n\nOn POPE, F1 rises from 83.9 to 86.9.\n\nReferences\n[1] Someone. A paper. 2020." },
];
// What the server's listening-script builder returns for this paper (references skipped, sections detected).
const script = {
  language: "en", characters: 220, minutes: 0.2, kind: "paper",
  sections: [
    { title: "", sentences: ["Grounded decoding for vision-language models.", "A. Rahman, L. Chen."], pages: [] },
    { title: "Abstract", sentences: ["We propose grounded decoding.", "It needs no training."], pages: [1] },
    { title: "Method", sentences: ["Tokens are re-weighted by visual evidence.", ...Array.from({ length: 40 }, (_, index) => `Method detail number ${index + 1}.`)], pages: [2] },
    { title: "Results", sentences: ["On POPE, F1 rises from 83.9 to 86.9.", ...Array.from({ length: 40 }, (_, index) => `Result detail number ${index + 1}.`)], pages: [3] },
  ],
};
const summary = {
  tldr: { text: "A training-free decoding method reduces hallucination.", pages: [1] },
  key_points: [{ text: "F1 rises on POPE.", pages: [3] }, { text: "No training is needed.", pages: [1] }],
  sections: {}, level: "student", language: "en", basis: "upload", basic: false, credits_used: 2,
};

type Spoken = { text: string; lang: string; rate: number };

async function fakeVoice(page: Page, voices: Array<{ lang: string; name: string }>) {
  await page.addInitScript((list) => {
    const spoken: Array<{ text: string; lang: string; rate: number }> = [];
    let timers: number[] = [];
    const synth = {
      speaking: false, paused: false, pending: false,
      getVoices: () => list.map((voice) => ({ ...voice, voiceURI: voice.name, localService: true, default: false })),
      speak(utterance: SpeechSynthesisUtterance) {
        spoken.push({ text: utterance.text, lang: utterance.lang, rate: utterance.rate });
        timers.push(window.setTimeout(() => utterance.onend?.(new Event("end") as SpeechSynthesisEvent), 120));
      },
      cancel() { timers.forEach((timer) => window.clearTimeout(timer)); timers = []; },
      pause() {}, resume() {},
      addEventListener() {}, removeEventListener() {},
    };
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: synth });
    (window as unknown as { __spoken: typeof spoken }).__spoken = spoken;
  }, voices);
}

const spoken = (page: Page) => page.evaluate(() => (window as unknown as { __spoken: Spoken[] }).__spoken);

async function mockApi(page: Page, options: { neural?: boolean } = {}) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  const queue: any[] = [];
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path === "/listen/script") {
      if (body.kind === "paper") return json(script);
      return json({ language: body.language, characters: 60, minutes: 0.1, sections: [{ title: "", sentences: body.texts, pages: [] }] });
    }
    if (path.startsWith("/listen/voices")) return json(options.neural ? { language: "en", neural_available: true, voices: [{ id: "neural:af_heart", name: "Heart — English (US)", language: "en", locale: "en-US", gender: "female", tier: "neural", default: true }], browser: { id: "browser", tier: "browser" } } : { language: "en", neural_available: false, voices: [], browser: { id: "browser", tier: "browser" } });
    if (path === "/listen/estimate") return json({ minutes: 0.2, credits: 1, tier: "neural" });
    if (path === "/listen/sessions") return json({ session_id: "ls_1", minutes: 0.2, credits: 1, tier: "neural" }, 201);
    if (path.endsWith("/speak")) return json({ detail: { code: "voice_unavailable" } }, 503);
    if (path.endsWith("/finish")) return json({ charged: 0, status: "refunded" });
    if (path.startsWith("/listen/progress")) return json(request.method() === "PUT" ? body : { items: [] });
    if (path === "/listen/queue" && request.method() === "POST") { queue.push({ id: `lq_${queue.length}`, ...body, position: queue.length, added_at: "2026-11-15T00:00:00Z" }); return json({ items: queue }, 201); }
    if (path === "/listen/queue") return json({ items: queue });
    if (path.endsWith("/reader/open")) return json(doc);
    if (path.includes("/pages")) return json({ pages });
    if (path.endsWith("/summary")) return json(summary);
    if (path.endsWith("/ask")) return json({ answer: "An answer.", citations: [], confidence: "high", not_found: false, language: "en", credits_used: 1 });
    if (path.includes(`/reader/${doc.id}`)) return json(doc);
    if (path.includes("/search/stream")) return json({ query: "q", total_results: 0, papers: [], pagination: { page: 1, has_next_page: false } });
    return json({});
  });
  return calls;
}

async function setLanguage(page: Page, language: string) {
  await page.addInitScript((code) => {
    window.localStorage.setItem("resora-language", code);
    window.localStorage.setItem("resora-language-source", "settings");
    window.localStorage.setItem("resora-compare-owner", "e2e-owner");
  }, language);
}

test("Listen → Whole paper: clean script, section names, keeps playing on another tab, speed and sections", async ({ page }) => {
  await setLanguage(page, "en");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }]);
  const calls = await mockApi(page);
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await expect(page.getByRole("heading", { name: doc.title })).toBeVisible();
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await page.getByRole("menuitem", { name: "Whole paper" }).click();
  const player = page.getByRole("region", { name: "Now listening" });
  await expect(player).toBeVisible();
  await expect(player).toContainText(doc.title);
  await expect.poll(async () => (await spoken(page)).map((item) => item.text)).toEqual(expect.arrayContaining(["Grounded decoding for vision-language models.", "We propose grounded decoding."]));
  const request = calls.find((call) => call.path === "/listen/script")!.body;
  expect(request).toMatchObject({ kind: "paper", read_references: false, read_citations: false, authors: doc.authors });
  expect((await spoken(page)).every((item) => item.lang.startsWith("en"))).toBe(true);
  expect((await spoken(page)).some((item) => item.text.includes("Someone"))).toBe(false);
  await expect(page.locator(".ls-follow")).toBeVisible();

  // Leave the Reader: the player stays and keeps speaking.
  await page.getByRole("link", { name: "Search" }).first().click();
  await expect(page).toHaveURL(/\/search/);
  await expect(player).toBeVisible();
  const before = (await spoken(page)).length;
  await expect.poll(async () => (await spoken(page)).length).toBeGreaterThan(before);

  // Speed is applied to the next sentence (device voice), sections can be jumped to.
  await player.getByRole("button", { name: "Speed" }).click();
  await page.getByRole("menuitemradio", { name: "1.5×" }).click();
  await player.getByRole("button", { name: "Show sections and queue" }).click();
  await page.getByRole("dialog", { name: "Now listening" }).getByRole("button", { name: /^Method/ }).click();
  await expect.poll(async () => (await spoken(page)).some((item) => item.text === "Tokens are re-weighted by visual evidence." && item.rate === 1.5)).toBe(true);
  await expect(player.locator(".ls-section")).toHaveText("Method");
  await expect(page.locator("select")).toHaveCount(0);
});

test("the position is saved and restored after a reload; L toggles play / pause", async ({ page }) => {
  await setLanguage(page, "en");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }]);
  const calls = await mockApi(page);
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await page.getByRole("menuitem", { name: "Whole paper" }).click();
  const player = page.getByRole("region", { name: "Now listening" });
  await expect(player.locator(".ls-section")).toHaveText(/Abstract|Method|Results/, { timeout: 5000 });
  await page.keyboard.press("l");
  await expect(player.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  const section = await player.locator(".ls-section").innerText();
  await expect.poll(() => calls.some((call) => call.path === "/listen/progress" && call.method === "PUT")).toBe(true);
  await page.reload();
  await expect(player).toBeVisible();
  await expect(player.locator(".ls-section")).toHaveText(section);
  await expect(player.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  await page.keyboard.press("l");
  await expect(player.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
  await player.getByRole("button", { name: "Close the player" }).click();
  await expect(player).toHaveCount(0);
});

test("asking in Urdu “خلاصہ سناؤ” reads the summary instead of asking the AI; “پیپر پڑھ کر سناؤ” reads the paper", async ({ page }) => {
  await setLanguage(page, "ur");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }, { lang: "ur-PK", name: "Fake Urdu" }]);
  const calls = await mockApi(page);
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await page.locator(".rd-chat-input textarea, .rd-chat-input input").first().fill("خلاصہ سناؤ");
  await page.keyboard.press("Enter");
  const player = page.getByRole("region", { name: "اب سن رہے ہیں" });
  await expect(player).toBeVisible();
  await expect.poll(async () => (await spoken(page)).map((item) => item.text)).toContain("A training-free decoding method reduces hallucination.");
  expect(calls.find((call) => call.path === "/listen/script")?.body).toMatchObject({ kind: "summary" });
  await expect(player).toHaveAttribute("dir", "rtl");
  await page.getByRole("tab", { name: "سوال جواب" }).click();
  await page.locator(".rd-chat-input textarea, .rd-chat-input input").first().fill("پیپر پڑھ کر سناؤ");
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await spoken(page)).map((item) => item.text)).toContain("We propose grounded decoding.");
  expect(calls.some((call) => call.path.endsWith("/ask"))).toBe(false);
});

test("a language without a voice is never read with a wrong-language voice", async ({ page }) => {
  await setLanguage(page, "en");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }]);
  await mockApi(page);
  await page.route(/\/api\/v1\/reader\/.+\/pages/, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ pages: [{ page: 1, text: "یہ ایک اردو مقالہ ہے۔ اس کا دوسرا جملہ۔" }] }) }));
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await page.getByRole("menuitem", { name: "Whole paper" }).click();
  await expect(page.getByText("Your device has no voice for this language", { exact: false }).first()).toBeVisible();
  expect((await spoken(page)).length).toBe(0);
});

test("natural voice: choosing it shows the credit estimate and starts a metered session; failures fall back to the device voice", async ({ page }) => {
  await setLanguage(page, "en");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }]);
  const calls = await mockApi(page, { neural: true });
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await page.getByRole("menuitem", { name: "Whole paper" }).click();
  const player = page.getByRole("region", { name: "Now listening" });
  await player.getByRole("button", { name: "Voice" }).click();
  await page.getByRole("menuitemradio", { name: /Heart — English/ }).click();
  await expect.poll(() => calls.find((call) => call.path === "/listen/sessions")?.body).toMatchObject({ voice: "neural:af_heart", language: "en" });
  await expect(player.getByText("Resora continues with your device voice", { exact: false })).toBeVisible();
  await expect.poll(async () => (await spoken(page)).length).toBeGreaterThan(0);
});

test("Listen later adds the paper to the queue shown in the player sheet", async ({ page }) => {
  await setLanguage(page, "en");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }]);
  const calls = await mockApi(page);
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await page.getByRole("menuitem", { name: "Listen later" }).click();
  await expect.poll(() => calls.find((call) => call.path === "/listen/queue" && call.method === "POST")?.body).toMatchObject({ item_id: `${doc.id}:paper`, kind: "paper", title: doc.title });
});

test("phone: the mini-player sits above the bottom navigation and nothing scrolls sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setLanguage(page, "en");
  await fakeVoice(page, [{ lang: "en-US", name: "Fake English" }]);
  await mockApi(page);
  await page.goto(`/reader/${doc.id}?tab=chat`);
  await page.locator(".rd-head-actions").getByRole("button", { name: "Listen", exact: true }).click();
  await page.getByRole("menuitem", { name: "Whole paper" }).click();
  const player = page.getByRole("region", { name: "Now listening" });
  await expect(player).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const playerBox = await player.boundingBox();
  const navBox = await page.locator(".mobile-bottom-nav").boundingBox();
  if (playerBox && navBox) expect(playerBox.y + playerBox.height).toBeLessThanOrEqual(navBox.y + 1);
});
