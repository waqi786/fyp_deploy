/**
 * Compare in the reader's language + Part 14 tools: column templates, saved comparisons, XLSX / PDF-report export,
 * and machine translation of table values (original passages kept). Every API call is mocked.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const comparisonId = "bfa6a27e-d302-4c8b-8e27-713dbcbfd170";
const files = [
  { id: "f1b40bab-72d2-4c7a-a31f-0f79fa2d4d01", name: "grounded-decoding.pdf", pages: 9, size: 2_000_000, sha256: "a".repeat(64) },
  { id: "0c6f0f8e-5d55-4a8e-9b3f-6a3b5c1d2e10", name: "contrastive-decoding.pdf", pages: 12, size: 3_000_000, sha256: "b".repeat(64) },
];
const titles = ["Grounded Decoding Reduces Hallucination", "Contrastive Decoding for Vision Models"];
const values = [
  { method: "Grounded decoding", dataset: "POPE", result: "Accuracy 86.9" },
  { method: "Contrastive decoding", dataset: "POPE", result: "Accuracy 85.1" },
];
const quotes = [
  "We propose grounded decoding, a training-free method that reduces hallucination.",
  "We introduce contrastive decoding and evaluate it on the POPE benchmark.",
];

const row = (index: number) => ({
  paper_id: `pdf:${files[index].id}`,
  title: titles[index],
  citation: titles[index],
  citation_count: 0,
  open_access: false,
  full_text_available: true,
  strengths: [],
  weaknesses: [],
  extracted_columns: values[index],
  evidence: { method: quotes[index], dataset: `We evaluate on POPE (paper ${index + 1}).` },
  evidence_source: { method: "Uploaded PDF · page 2", dataset: "Uploaded PDF · page 4" },
  confidence_by_column: { method: "high", dataset: "medium", result: "low" },
  methods: [values[index].method],
  datasets: ["POPE"],
  result_metrics: {},
  significance_note: "",
  pinned: false,
});
const profile = (index: number) => ({
  paper_id: `pdf:${files[index].id}`,
  profile_version: 1,
  publication_year: 2023 + index,
  research_questions: [{ quote: `Can decoding alone reduce hallucination (paper ${index + 1})?`, page: 1 }],
  motivation: [],
  contributions: [],
  baselines: [],
  experiments: [],
  ablation: [],
  datasets_detail: [{ name: "POPE", quote: `We evaluate on POPE (paper ${index + 1}).`, page: 4 }],
  reproducibility: { code: { status: "reported", quote: "Code is available on GitHub.", page: 7 } },
  frameworks: [],
  future_work: [{ quote: `Future work will test video models (paper ${index + 1}).`, page: 8 }],
  authors_affiliations: [],
  parsed_references: [],
  key_tables: [],
  key_figures: [],
  evidence_pages: [],
});
const result = {
  focus: "Research question",
  comparison_count: 2,
  max_supported_papers: 15,
  rows: [row(0), row(1)],
  auto_suggested_columns: [],
  custom_columns_resolved: ["method", "dataset", "result"],
  grouped_methods: {},
  similarity_heatmap: [],
  method_similarity_heatmap: [],
  dataset_similarity_heatmap: [],
  result_similarity_heatmap: [],
  heatmap_labels: [],
  performance_leaderboard_by_dataset: {},
  contradiction_highlights: [],
  timeline: [],
  best_paper_recommendation: "",
  dataset_overlap: {},
  citation_overlap_venn: {},
  citation_overlap_sets: {},
  narrative_summary: "Two decoding methods evaluated on POPE.",
  export_markdown: "| Paper |",
  export_csv: "Paper",
  export_latex: "",
  export_json: "{}",
  literature_review_section: "",
  literature_review_export_job: { status: "ready" },
  comparison_snapshot_id: "snap-1234",
  shareable_url: "",
  pinned_row_order: [],
  paper_profiles: [profile(0), profile(1)],
  insights_model: { version: 1, takeaway: "Both methods reduce hallucination on POPE.", takeaway_evidence: [], key_numbers: [], head_to_head: null, generated_from_full_text: true },
};

type Calls = { saved: Array<{ method: string; url: string; body: unknown }>; translate: string[][]; uploaded: boolean };

async function mock(page: Page, saved: unknown[] = []) {
  const calls: Calls = { saved: [], translate: [], uploaded: false };
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = request.url();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.includes("/comparison/pdfs/limits")) return json({ max_files: 15, max_bytes: 50_000_000, max_pages: 120 });
    if (url.includes("/comparison/pdfs/saved")) {
      calls.saved.push({ method: request.method(), url, body: request.postData() ? request.postDataJSON() : null });
      if (request.method() === "GET") return json({ comparisons: saved });
      if (request.method() === "DELETE") { saved.splice(0, saved.length); return route.fulfill({ status: 204 }); }
      return json({ ...(saved[0] as object || {}), ...(request.postDataJSON() as object) });
    }
    if (url.includes("/comparison/pdfs/upload")) { calls.uploaded = true; return json({ comparison_id: comparisonId, files }); }
    if (url.includes("/comparison/pdfs/run")) return json(result);
    if (url.includes("/translate")) {
      const texts = (request.postDataJSON() as { texts: string[] }).texts;
      calls.translate.push(texts);
      return json({ translations: texts.map((text) => `[ur] ${text}`), credits_used: 1 });
    }
    if (url.includes("/comparison/pdfs?comparison_id=")) return json({ comparison_id: comparisonId, files: request.method() === "GET" && calls.uploaded ? files : [] });
    return json({});
  });
  return calls;
}

async function runComparison(page: Page, compareLabel: string) {
  await page.locator(".comparison-file-picker").setInputFiles(files.map((file) => ({ name: file.name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%fake\n") })));
  await page.getByRole("button", { name: compareLabel, exact: true }).last().click();
  await expect(page.locator(".comparison-table-card table tbody tr")).toHaveCount(2);
}

/** Visible text of the Compare page with paper content removed: what is left must contain no English words. */
async function leftoverEnglish(page: Page) {
  const text = await page.locator(".comparison-shell").innerText();
  const content = [...titles, ...quotes, ...values.flatMap((item) => Object.values(item)), ...files.map((file) => file.name), "snap-1234", "ready", "Code is available on GitHub.", result.insights_model.takeaway, "POPE", "pope", "Resora", "PDF", "CSV", "JSON", "Markdown", "Excel", "xlsx", "DOI", "MB"];
  let rest = text;
  for (const item of content.sort((a, b) => b.length - a.length)) rest = rest.split(item).join(" ");
  rest = rest.replace(/\[ur\]/g, " ").replace(/\(paper \d\)/g, " ").replace(/We evaluate on|Can decoding alone reduce hallucination|Future work will test video models/g, " ");
  return [...new Set(rest.match(/[A-Za-z]{3,}/g) || [])];
}

test("Urdu: every Compare label comes from the catalog, in the table and every Insights tab", async ({ page }) => {
  await mock(page);
  await page.goto("/comparison?lang=ur");
  await expect(page.getByRole("heading", { name: "اپنے مقالات کا موازنہ کریں۔" })).toBeVisible();
  expect(await leftoverEnglish(page)).toEqual([]);
  await expect(page.locator(".comparison-shell")).toHaveAttribute("dir", "rtl");

  await runComparison(page, "موازنہ کریں");
  await expect(page.getByRole("columnheader", { name: "طریقہ" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "ڈیٹا سیٹ" })).toBeVisible();
  await expect(page.getByText("9 صفحات · اپ لوڈ شدہ ماخذ")).toBeVisible();
  expect(await leftoverEnglish(page)).toEqual([]);

  await page.getByRole("tab", { name: "بصیرتیں" }).click();
  for (const tab of ["جائزہ", "ثبوت", "طریقے اور ڈیٹا", "دہرائے جانے کی صلاحیت", "اگلے اقدامات"]) {
    const control = page.getByRole("tablist", { name: "مقالات کی بصیرتیں" }).getByRole("tab", { name: tab });
    if (!(await control.count())) continue;
    await control.click();
    await expect(control).toHaveAttribute("aria-selected", "true");
    const left = await leftoverEnglish(page);
    expect(left, `English left on tab ${tab}`).toEqual([]);
  }
});

test("Urdu: table values can be shown in Urdu; the source passage stays original with its translation beside it", async ({ page }) => {
  const calls = await mock(page);
  await page.goto("/comparison?lang=ur");
  await runComparison(page, "موازنہ کریں");
  await page.getByRole("button", { name: /اردو میں دکھائیں/ }).click();
  await expect(page.getByText("[ur] Grounded decoding", { exact: true })).toBeVisible();
  expect(calls.translate[0]).toEqual(expect.arrayContaining(["Grounded decoding", "Accuracy 86.9", "Both methods reduce hallucination on POPE."]));
  await expect(page.getByRole("button", { name: "اصل متن دکھائیں" })).toHaveAttribute("aria-pressed", "true");

  await page.getByText("[ur] Grounded decoding", { exact: true }).click();
  const panel = page.getByRole("complementary", { name: "ماخذ کا ثبوت" });
  await expect(panel.getByText(quotes[0], { exact: true })).toBeVisible();
  await expect(panel.getByText(`[ur] ${quotes[0]}`)).toBeVisible();
  await expect(panel.getByText("اپ لوڈ شدہ PDF · صفحہ 2").first()).toBeVisible();

  await page.getByRole("button", { name: "اصل متن دکھائیں" }).click();
  await expect(page.getByText("Grounded decoding", { exact: true }).first()).toBeVisible();
});

test("column templates set the extraction columns", async ({ page }) => {
  await mock(page);
  await page.goto("/comparison?lang=en");
  await page.locator(".comparison-file-picker").setInputFiles(files.map((file) => ({ name: file.name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n") })));
  await page.getByRole("button", { name: "Clinical study" }).click();
  await expect(page.getByRole("button", { name: "Clinical study" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Extraction columns")).toHaveValue(/study design, population, sample size, intervention/);
  await expect(page.getByRole("status").filter({ hasText: "Clinical study columns applied." })).toBeVisible();
});

test("exports: Excel workbook and a printable PDF report", async ({ page }, testInfo) => {
  await mock(page);
  await page.goto("/comparison?lang=en");
  await runComparison(page, "Compare");
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Excel (.xlsx)" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("resora-comparison.xlsx");
  const path = testInfo.outputPath("comparison.xlsx");
  await download.saveAs(path);
  const bytes = require("fs").readFileSync(path) as Buffer;
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  if (process.env.XLSX_COPY) require("fs").copyFileSync(path, process.env.XLSX_COPY);

  await page.getByRole("button", { name: "Export", exact: true }).click();
  await page.getByRole("menuitem", { name: "PDF report" }).click();
  const report = page.frameLocator("#cmp-print-frame");
  // The report frame is invisible on screen; it exists only for the browser's print dialog ("Save as PDF").
  await expect(report.locator("h1")).toHaveText("Resora comparison report");
  await expect(report.locator("tbody th").first()).toHaveText(titles[0]);
  await expect(report.locator("thead th")).toHaveText(["Paper", "Method", "Dataset", "Result"]);
  await expect(report.locator("blockquote").first()).toHaveText(quotes[0]);
});

test("saved comparisons: listed, renamed and deleted (two-step)", async ({ page }) => {
  const saved = [{ comparison_id: comparisonId, name: "Hallucination decoding", focus: null, columns: ["method"], file_count: 2, updated_at: "2026-10-30T10:00:00Z" }];
  const calls = await mock(page, saved);
  await page.goto("/comparison?lang=en");
  const list = page.getByRole("region", { name: "Saved comparisons" });
  await expect(list.getByText("Hallucination decoding")).toBeVisible();
  await expect(list.getByText(/2 PDFs ·/)).toBeVisible();

  await list.getByRole("button", { name: "Rename" }).click();
  await list.getByLabel("Comparison name").fill("My decoding review");
  await list.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => calls.saved.find((call) => call.method === "PUT")?.body).toEqual({ name: "My decoding review" });

  await list.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(list.getByRole("button", { name: "Delete with its PDFs" })).toBeVisible();
  await list.getByRole("button", { name: "Delete with its PDFs" }).click();
  await expect.poll(() => calls.saved.some((call) => call.method === "DELETE" && call.url.endsWith(comparisonId))).toBe(true);
  await expect(page.getByText("Comparison deleted with its stored PDFs.").first()).toBeAttached();
  await expect(list).toHaveCount(0);
});
