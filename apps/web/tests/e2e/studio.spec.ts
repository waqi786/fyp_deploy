/** Paper studio (LaTeX): create from a journal template, edit with autosave + conflict protection, compile with
 * clickable error lines, convert format, upload an image, share with a team, download. API mocked. */
import { expect, test, type Page, type Route } from "@playwright/test";

const MAIN = "\\documentclass{article}\n\\title{My paper}\n\\begin{document}\n\\maketitle\n\\section{Introduction}\nHello.\n\\end{document}\n";

async function fakeApi(page: Page) {
  const calls: Array<{ method: string; path: string; body: any }> = [];
  const state = { version: 1, content: MAIN, template: "ieee", team: null as string | null, compiled: 0, files: [{ path: "main.tex", kind: "text", size: 100, version: 1, updated_by: "me", updated_at: "2026-11-15T00:00:00Z" }, { path: "references.bib", kind: "text", size: 50, version: 1, updated_by: "me", updated_at: "2026-11-15T00:00:00Z" }] as any[] };
  const project = () => ({ id: "sp_1", title: "My paper", template: state.template, team_id: state.team, owner_id: "me", main_file: "main.tex", access: "owner", updated_at: "2026-11-15T00:00:00Z", files: state.files, templates: [{ id: "article", name: "Article", class: "article" }, { id: "ieee", name: "IEEE", class: "IEEEtran" }, { id: "springer", name: "LNCS", class: "llncs" }, { id: "beamer", name: "Slides", class: "beamer" }] });
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^.*\/api\/v1/, "");
    const body = request.postData() && request.headers()["content-type"]?.includes("json") ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
    if (path === "/studio/templates") return json({ templates: project().templates, compiler: true });
    if (path === "/studio/projects" && request.method() === "GET") return json({ projects: [] });
    if (path === "/studio/projects" && request.method() === "POST") { state.template = body.template; return json(project(), 201); }
    if (path === "/studio/projects/sp_1" && request.method() === "PATCH") { state.team = body.clear_team ? null : body.team_id; return json(project()); }
    if (path === "/studio/projects/sp_1") return json(project());
    if (path === "/studio/projects/sp_1/file" && request.method() === "GET") return json({ path: url.searchParams.get("path"), kind: "text", content: state.content, version: state.version });
    if (path === "/studio/projects/sp_1/file" && request.method() === "PUT") {
      if (body.base_version !== state.version) return json({ detail: { code: "conflict", version: state.version, content: state.content } }, 409);
      state.version += 1; state.content = body.content; return json({ path: body.path, version: state.version });
    }
    if (path === "/studio/projects/sp_1/compile") {
      state.compiled += 1;
      return json(state.compiled === 1 ? { ok: false, has_pdf: false, errors: [{ file: "main.tex", line: 6, message: "Undefined control sequence." }], warnings: [], seconds: 1.2 } : { ok: true, has_pdf: true, errors: [], warnings: [{ line: null, message: "Citation undefined" }], seconds: 1.4, pages: 2, exact_class: false });
    }
    if (path === "/studio/projects/sp_1/pdf") return route.fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.5\n%%EOF" });
    if (path === "/studio/projects/sp_1/convert") { state.template = body.template; return json(project()); }
    if (path === "/studio/projects/sp_1/upload") { state.files = [...state.files, { path: "images/fig.png", kind: "binary", size: 10, version: 1, updated_by: "me", updated_at: "2026-11-15T00:00:00Z" }]; return json({ path: "images/fig.png" }, 201); }
    if (path === "/studio/projects/sp_1/export") return route.fulfill({ status: 200, contentType: "application/zip", body: "PK\u0003\u0004" });
    if (path === "/teams") return json({ teams: [{ id: "t1", name: "Thesis lab", role: "owner" }] });
    if (path === "/write/documents") return json([{ id: "d1", title: "Introduction draft" }]);
    return json({});
  });
  return { calls, state };
}

async function setLanguage(page: Page, language = "en") {
  await page.addInitScript((code) => {
    window.localStorage.setItem("resora-language", code);
    window.localStorage.setItem("resora-language-source", "settings");
    window.localStorage.setItem("resora-compare-owner", "me");
  }, language);
}

test("Studio and Teams are main tabs", async ({ page }) => {
  await setLanguage(page);
  await fakeApi(page);
  await page.goto("/search");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("link", { name: "Teams" })).toBeVisible();
  await nav.getByRole("link", { name: "Studio" }).click();
  await expect(page.getByRole("heading", { name: "Paper studio", level: 1 })).toBeVisible();
});

test("create an IEEE paper, autosave, compile errors jump to the line, fix, PDF, convert, image, share, download", async ({ page }) => {
  await setLanguage(page);
  const { calls, state } = await fakeApi(page);
  await page.goto("/studio");
  await page.getByLabel("Paper title").fill("My paper");
  await page.getByRole("radio", { name: "IEEE conference" }).click();
  await page.getByRole("button", { name: "Create paper" }).click();
  await expect(page).toHaveURL(/\/studio\/sp_1/);
  expect(calls.find((call) => call.path === "/studio/projects" && call.method === "POST")?.body).toMatchObject({ title: "My paper", template: "ieee" });
  const editor = page.getByLabel("LaTeX source of main.tex");
  await expect(editor).toHaveValue(/\\section\{Introduction\}/);

  await editor.click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type("% note");
  await expect.poll(() => calls.find((call) => call.method === "PUT")?.body, { timeout: 6000 }).toMatchObject({ path: "main.tex", base_version: 1 });
  await expect(page.locator(".stu-save")).toHaveText("Saved");

  await page.getByRole("button", { name: "Compile PDF" }).click();
  await expect(page.getByText("The PDF could not be built. Errors: 1")).toBeVisible();
  await page.getByRole("button", { name: /Line 6/ }).click();
  expect(await editor.evaluate((node: HTMLTextAreaElement) => node.value.slice(node.selectionStart, node.selectionEnd))).toBe("Hello.");
  await page.getByRole("button", { name: "Compile PDF" }).click();
  await expect(page.getByText("PDF ready · pages: 2", { exact: false })).toBeVisible();
  await expect(page.getByTitle("PDF preview")).toBeVisible();
  await expect(page.getByText("close preview layout", { exact: false })).toBeVisible();

  await page.getByText("Format: IEEE conference").click();
  await page.getByRole("menuitemradio", { name: "Springer LNCS" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Converted to Springer LNCS." })).toBeVisible();
  expect(state.template).toBe("springer");

  await page.locator(".stu-upload input").setInputFiles({ name: "fig.png", mimeType: "image/png", buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47]) });
  await expect(page.getByRole("button", { name: "images/fig.png", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Figure" }).click();
  await expect(editor).toHaveValue(/\\includegraphics/);

  await page.getByRole("button", { name: "Share", exact: true }).click();
  await page.getByRole("button", { name: "Share", exact: true }).last().click();
  await expect.poll(() => calls.find((call) => call.method === "PATCH")?.body).toEqual({ team_id: "t1" });

  const downloadPromise = page.waitForEvent("download");
  await page.getByText("Download", { exact: true }).click();
  await page.getByRole("menuitem", { name: "LaTeX source (.zip)" }).click();
  expect((await downloadPromise).suggestedFilename()).toBe("My-paper.zip");
  await expect(page.locator("select")).toHaveCount(0);
});

test("a teammate's newer save is never overwritten silently", async ({ page }) => {
  await setLanguage(page);
  const { state } = await fakeApi(page);
  await page.goto("/studio/sp_1");
  const editor = page.getByLabel("LaTeX source of main.tex");
  await expect(editor).toHaveValue(/Introduction/);
  state.version = 5; // a teammate saved meanwhile
  state.content = MAIN.replace("Hello.", "Teammate text.");
  await editor.click();
  await page.keyboard.type("x");
  await expect(page.getByRole("alert").filter({ hasText: "A teammate saved this file" })).toBeVisible({ timeout: 6000 });
  await page.getByRole("button", { name: "Load their version" }).click();
  await expect(editor).toHaveValue(/Teammate text\./);
});

test("Urdu studio has no English labels and phones do not scroll sideways", async ({ page }) => {
  await setLanguage(page, "ur");
  await fakeApi(page);
  await page.goto("/studio");
  await expect(page.locator(".stu-new")).toBeVisible();
  let text = await page.locator(".pf-page").first().innerText();
  for (const item of ["Resora", "LaTeX", "PDF", "IEEE", "ACM", "Springer LNCS", "Elsevier", "APA", "Introduction draft"]) text = text.split(item).join(" ");
  expect([...new Set(text.match(/[A-Za-z]{3,}/g) || [])]).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/studio/sp_1");
  await expect(page.locator(".stu-code textarea")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
