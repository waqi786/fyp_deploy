import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const comparisonId = "bfa6a27e-d302-4c8b-8e27-713dbcbfd170";
const papers = [
  { id: "f1b40bab-72d2-4c7a-a31f-0f79fa2d4d01", name: "Paper A.pdf", pages: 8, size: 1024, sha256: "a".repeat(64) },
  { id: "f1b40bab-72d2-4c7a-a31f-0f79fa2d4d02", name: "Paper B.pdf", pages: 11, size: 2048, sha256: "b".repeat(64) },
];
const quoteA = "We evaluate our method on the CIFAR-10 benchmark and report accuracy for the test set.";
const quoteB = "Experiments use the CIFAR-10 dataset and report accuracy on a held-out test set.";
const profile = (paper_id: string, quote: string, year: number) => ({
  paper_id, profile_version: 2, doi: null, publication_year: year, preprint_notice: null,
  research_questions: [{ quote: "We investigate whether the proposed approach improves image classification.", page: 1, section: "Introduction" }],
  motivation: [], contributions: [{ quote: "Our main contribution is a careful evaluation of image classification methods.", page: 1, section: "Introduction" }],
  baselines: [{ quote: "We compare against established baseline methods.", page: 3, section: "Methods" }], experiments: [{ quote, page: 5, section: "Results" }], strongest_experiment: null, ablation: [],
  datasets_detail: [{ name: "CIFAR-10", quote, page: 5, task: "Image classification", size: null, splits: [], access: "not stated", license: null, link: null }],
  reproducibility: { code: { status: "not stated" }, dataset: { status: "reported", quote, page: 5 }, hyperparameters: { status: "not stated" }, experimental_details: { status: "not stated" }, pretrained_model: { status: "not stated" }, license: { status: "not stated" } },
  repo_url: null, frameworks: [], future_work: [], authors_affiliations: [], parsed_references: [], key_tables: [], key_figures: [], evidence_pages: [{ quote, page: 5, section: "Results" }],
});
const response = {
  focus: "Image classification", comparison_count: 2, max_supported_papers: 15,
  rows: papers.map((paper, index) => ({
    paper_id: `pdf:${paper.id}`, title: `Study ${index ? "B" : "A"}: Reliable Classification`, source_url: null, full_text_source_url: null, discovery_source: "uploaded_pdf", year: 2024 + index, venue: "Research Journal", citation: "", citation_count: 0, open_access: true,
    abstract_available: true, full_text_available: true, full_text_status: "available", full_text_source: "uploaded_pdf", document_type: "research_article", strengths: [], weaknesses: [],
    extracted_columns: { method: "Classification", dataset: "CIFAR-10", metric: "Accuracy", result: index ? "Accuracy was 91 percent." : "Accuracy was 90 percent.", limitation: "Evaluation is limited to one benchmark." },
    evidence: { method: "We evaluate image classification methods.", dataset: index ? quoteB : quoteA, metric: index ? quoteB : quoteA, result: index ? quoteB : quoteA, limitation: "Evaluation is limited to one benchmark." },
    evidence_source: { dataset: "Uploaded PDF Â· page 5", result: "Uploaded PDF Â· page 5", limitation: "Uploaded PDF Â· page 6" }, confidence_by_column: { dataset: "high", result: "medium", limitation: "medium" },
    similarity_score: 0.5, method_similarity_score: 0.5, dataset_similarity_score: 1, result_similarity_score: 0.9, methods: ["Classification"], datasets: ["CIFAR-10"], result_metrics: { ACCURACY: index ? 0.91 : 0.9 }, significance_note: "No explicit significance signal", pinned: false,
  })),
  auto_suggested_columns: ["method", "dataset", "result"], custom_columns_resolved: ["method", "dataset", "metric", "result", "limitation"], leaderboard: [], grouped_methods: { Classification: ["pdf:a", "pdf:b"] }, methodology_dendrogram: {}, dendrogram_edges: [],
  similarity_heatmap: [[1, 0.5], [0.5, 1]], method_similarity_heatmap: [[1, 1], [1, 1]], dataset_similarity_heatmap: [[1, 1], [1, 1]], result_similarity_heatmap: [[1, 0.9], [0.9, 1]], heatmap_labels: ["Study A", "Study B"], performance_leaderboard_by_dataset: {}, contradiction_highlights: [], timeline: [{ title: "Study A", year: 2024, methods: "Classification" }], best_paper_recommendation: "No single best paper", dataset_overlap: {}, dataset_overlap_matrix: [[1, 1], [1, 1]], citation_overlap_venn: {}, citation_overlap_sets: {}, narrative_summary: "Two uploaded papers report different evaluation details.", export_markdown: "", export_csv: "", export_latex: "", export_json: "", literature_review_section: "", literature_review_export_job: {}, comparison_snapshot_id: "snapshot-test", shareable_link_token: "test-token", shareable_url: "/comparison/share/test-token", snapshot_metadata: {}, pinned_row_order: [],
  paper_profiles: [profile(`pdf:${papers[0].id}`, quoteA, 2024), profile(`pdf:${papers[1].id}`, quoteB, 2025)], insight_run_id: "run-test", insights_cached: false,
  insights_model: { version: 1, takeaway: "The PDFs use a shared benchmark, but matching test protocols are not verified.", takeaway_evidence: [{ paper_id: `pdf:${papers[0].id}`, field: "full_text", quote: quoteA, page: 5 }], key_numbers: [{ value: "2/2", label: "PDFs with readable full text", source: "Uploaded PDF text", evidence: [{ paper_id: `pdf:${papers[0].id}`, field: "full_text", quote: quoteA, page: 5 }, { paper_id: `pdf:${papers[1].id}`, field: "full_text", quote: quoteB, page: 5 }] }], head_to_head: null, generated_from_full_text: true },
};

async function openInsights(page: Page, theme: "light" | "dark") {
  await page.addInitScript(({ theme, comparisonId }) => {
    localStorage.setItem("resora-theme", theme);
    localStorage.setItem("resora-comparison-current-id", comparisonId);
  }, { theme, comparisonId });
  await page.route("**/api/v1/comparison/pdfs/limits", (route) => route.fulfill({ json: { max_files: 15, max_bytes: 50_000_000, max_pages: 120 } }));
  await page.route("**/api/v1/comparison/pdfs?comparison_id=**", (route) => route.fulfill({ json: { files: papers } }));
  await page.route("**/api/v1/comparison/pdfs/run", (route) => route.fulfill({ json: response }));
  await page.goto("/comparison?view=insights&tab=overview");
  await expect(page.getByRole("heading", { name: "Image classification" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Image classification" })).toBeVisible();
  await page.getByRole("tab", { name: "Insights" }).click();
  await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
}

test("overview stays concise, evidence-linked, and theme-safe", async ({ page }) => {
  await mkdir("test-shots/insights", { recursive: true });
  for (const theme of ["light", "dark"] as const) {
    await openInsights(page, theme);
    const overview = page.locator(".comparison-overview-content");
    await expect(overview.locator(".comparison-overview-hero")).toBeVisible();
    await expect(overview.locator(":scope > section")).toHaveCount(4);
    await expect(overview.locator(".comparison-key-numbers button")).toHaveCount(1);
    await expect(overview.locator(".comparison-overview-pair article")).toHaveCount(2);
    await expect(overview.locator(".comparison-more-insights")).toBeVisible();
    await expect(page.locator(".comparison-takeaway-claim")).toContainText(response.insights_model.takeaway);
    await page.screenshot({ path: `test-shots/insights/overview-${theme}.png`, fullPage: true });
  }
});

test("each subtab is isolated and its URL can be reloaded", async ({ page }) => {
  await openInsights(page, "dark");
  const tabs = [{ name: "Evidence", slug: "evidence" }, { name: "Methods & data", slug: "methods" }, { name: "Reproducibility", slug: "reproducibility" }, { name: "Next steps", slug: "next" }];
  await mkdir("test-shots/insights", { recursive: true });
  for (const { name, slug } of tabs) {
    await page.getByRole("tab", { name }).click();
    await expect(page).toHaveURL(new RegExp(`tab=${slug}`));
    if (slug === "evidence") {
      await page.reload();
      await expect(page.getByRole("tab", { name, selected: true })).toBeVisible();
    }
    const visibleBlocks = page.locator(".comparison-insights-detail > section:visible");
    expect(await visibleBlocks.count(), `${name} should show content`).toBeGreaterThan(0);
    expect(await visibleBlocks.count(), `${name} should have at most four visible blocks`).toBeLessThanOrEqual(4);
    await page.screenshot({ path: `test-shots/insights/${slug}-desktop.png`, fullPage: true });
  }
});

test("all tabs fit mobile width without page-level horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openInsights(page, "dark");
  const tabs = ["Overview", "Evidence", "Methods & data", "Reproducibility", "Next steps"];
  await mkdir("test-shots/insights", { recursive: true });
  for (const name of tabs) {
    await page.getByRole("tab", { name }).click();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `test-shots/insights/mobile-${name.toLowerCase().replaceAll(" & ", "-").replaceAll(" ", "-")}.png`, fullPage: true });
  }
});


