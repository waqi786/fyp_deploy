import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { addPapersToComparison, comparisonHeaders, deleteSavedComparison, listSavedComparisons, saveComparison, translateComparisonText, type MissingPaper, type SavedComparison } from "./compare/compareApi";
import { COLUMN_TEMPLATES, CompareCopyProvider, SUGGESTED_COLUMNS, isRtl, languageName, makeCompareCopy, useCompareCopy } from "./compare/compareCopy";
import { comparisonXlsx, downloadBlob, printComparisonReport, type ExportTable } from "./compare/compareExport";
import { clearTray, readTray } from "./compare/compareTray";
import { readerApi } from "./reader/readerApi";
import { libraryApi } from "./library/libraryApi";
import { useSearchCopy, type SearchCopyKey } from "./search/copy";
import "./compare/CompareImport.css";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "/api/v1";

type UploadedPdf = { id: string; name: string; pages: number; size: number; sha256: string };
type UploadLimits = { max_files: number; max_bytes: number; max_pages: number };

// The owner header is shared with the Compare tray (Search / Reader), so both talk to the same private comparison.
type ComparisonRow = {
  paper_id: string;
  title: string;
  source_url?: string | null;
  full_text_source_url?: string | null;
  discovery_source?: string | null;
  year?: number | null;
  venue?: string | null;
  citation: string;
  citation_count: number;
  open_access: boolean;
  abstract_available?: boolean;
  full_text_available?: boolean;
  full_text_status?: string;
  full_text_source?: string | null;
  document_type?: string;
  strengths: string[];
  weaknesses: string[];
  extracted_columns?: Record<string, string>;
  evidence: Record<string, string>;
  evidence_source: Record<string, string>;
  confidence_by_column: Record<string, string>;
  similarity_score?: number;
  method_similarity_score?: number;
  dataset_similarity_score?: number;
  result_similarity_score?: number;
  methods: string[];
  datasets: string[];
  result_metrics: Record<string, number>;
  significance_note: string;
  pinned: boolean;
};

type ComparisonResponse = {
  focus: string;
  comparison_count: number;
  max_supported_papers?: number;
  rows: ComparisonRow[];
  auto_suggested_columns: string[];
  custom_columns_resolved: string[];
  leaderboard?: string[];
  grouped_methods: Record<string, string[]>;
  methodology_dendrogram?: Record<string, string[]>;
  dendrogram_edges?: Array<Record<string, string | number>>;
  similarity_heatmap: number[][];
  method_similarity_heatmap: number[][];
  dataset_similarity_heatmap: number[][];
  result_similarity_heatmap: number[][];
  heatmap_labels: string[];
  performance_leaderboard_by_dataset: Record<string, string[]>;
  contradiction_highlights: string[];
  timeline: Array<{ title: string; year: number; methods: string }>;
  best_paper_recommendation: string;
  dataset_overlap: Record<string, string[]>;
  dataset_overlap_matrix?: number[][];
  citation_overlap_venn: Record<string, number>;
  citation_overlap_sets: Record<string, string[]>;
  narrative_summary: string;
  export_markdown?: string;
  export_csv: string;
  export_latex: string;
  export_json?: string;
  literature_review_section: string;
  literature_review_export_job: { job_id?: string; status?: string; target?: string };
  comparison_snapshot_id: string;
  shareable_link_token?: string;
  shareable_url: string;
  snapshot_metadata?: Record<string, string | number | string[]>;
  pinned_row_order: string[];
  paper_profiles?: PaperProfile[];
  insight_run_id?: string | null;
  insights_cached?: boolean;
  insights_model?: {
    version: number;
    takeaway: string;
    takeaway_evidence: Array<{ paper_id: string; field: string; quote: string; page?: number | null }>;
    key_numbers: Array<{ value: string; label: string; source: string; evidence: Array<{ paper_id: string; field: string; quote: string; page?: number | null }> }>;
    head_to_head?: { dataset: string; metric: string; split: string; points: Array<{ paper_id: string; value: number; evidence: { paper_id: string; field: string; quote: string; page?: number | null } }> } | null;
    generated_from_full_text: boolean;
  } | null;
};

type ProfileEvidence = { quote: string; page?: number | null; section?: string };
type PaperProfile = {
  paper_id: string;
  profile_version: number;
  doi?: string | null;
  publication_year?: number | null;
  preprint_notice?: string | null;
  research_questions: ProfileEvidence[];
  motivation: ProfileEvidence[];
  contributions: ProfileEvidence[];
  baselines: ProfileEvidence[];
  experiments: ProfileEvidence[];
  strongest_experiment?: ProfileEvidence | null;
  ablation: ProfileEvidence[];
  datasets_detail: Array<{ name: string; quote?: string; page?: number | null; task?: string | null; size?: string | null; splits?: string[]; access?: string; license?: string | null; link?: string | null }>;
  reproducibility: Record<string, { status: string; quote?: string; page?: number | null }>;
  repo_url?: string | null;
  frameworks: ProfileEvidence[];
  future_work: ProfileEvidence[];
  authors_affiliations: Array<{ name?: string; affiliation?: string | null }>;
  parsed_references: Array<{ text: string; doi?: string | null; page?: number | null }>;
  key_tables: Array<{ caption: string; page?: number | null; headers?: string[]; rows?: string[][] }>;
  key_figures: Array<{ caption: string; page?: number | null }>;
  evidence_pages?: ProfileEvidence[];
};

type CopyValues = Record<string, string | number>;
/** A status line is stored as a catalog key so it re-renders in the right language when the catalog loads or changes. */
type StatusMsg = { key: SearchCopyKey; values?: CopyValues } | { text: string };

/** A failure with a catalog message; `detail` is the API's own (English) explanation, shown only in English. */
class CompareFailure extends Error {
  constructor(public key: SearchCopyKey, public values?: CopyValues, public detail = "") {
    super(detail || key);
  }
}

const DEFAULT_COLUMNS = "method, dataset, model, metric, result, limitation, reproducibility";
const NO_FOCUS = "Research question";

const MISSING_REASON: Record<MissingPaper["reason"], SearchCopyKey> = {
  no_open_pdf: "compareMissingHint",
  not_readable: "compareUnreadable",
  mismatch: "compareMismatch",
  duplicate: "compareMissingHint",
  limit: "compareTrayFull",
};

function safePaperPageUrl(value?: string | null): string | null {
  try {
    const url = new URL(value || "");
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function ComparisonPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string } = {}) {
  const navigate = useNavigate();
  const t = useSearchCopy(interfaceLanguage);
  const rtl = isRtl(interfaceLanguage);
  const [translated, setTranslated] = useState<Record<string, string>>({});
  const [showTranslated, setShowTranslated] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [savedList, setSavedList] = useState<SavedComparison[]>([]);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState("");
  const copy = useMemo(() => makeCompareCopy(t, interfaceLanguage, showTranslated ? translated : {}), [t, interfaceLanguage, showTranslated, translated]);
  const [missingPapers, setMissingPapers] = useState<MissingPaper[]>([]);
  const [importing, setImporting] = useState(0);
  const trayImportStarted = useRef(false);
  const pendingMissingKey = useRef<string | null>(null);
  const queuedCount = useRef(0);
  const pickerRef = useRef<HTMLInputElement>(null);
  const insightsRestoreStarted = useRef(false);
  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedPdf[]>([]);
  const [uploadLimits, setUploadLimits] = useState<UploadLimits>({ max_files: 15, max_bytes: 50 * 1024 * 1024, max_pages: 120 });
  const [comparisonId, setComparisonId] = useState(() => window.localStorage.getItem("resora-comparison-current-id") || "");
  const [dragging, setDragging] = useState(false);
  const [activeView, setActiveView] = useState<"table" | "insights">(() => new URLSearchParams(window.location.search).get("view") === "insights" ? "insights" : "table");
  const [focus, setFocus] = useState(NO_FOCUS);
  const [customColumns, setCustomColumns] = useState(DEFAULT_COLUMNS);
  const [response, setResponse] = useState<ComparisonResponse | null>(null);
  const [selectedRowId, setSelectedRowId] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<{ paper: string; paperId: string; column: string; value: string; quote: string; source: string; confidence: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState<StatusMsg>({ key: "cmpStatusStart" });
  const say = (key: SearchCopyKey, values?: CopyValues) => setStatusMsg({ key, values });
  const status = "text" in statusMsg ? statusMsg.text : t(statusMsg.key, statusMsg.values);
  const [loading, setLoading] = useState(false);
  const [selectedPaperCount, setSelectedPaperCount] = useState(0);
  const [exportOpen, setExportOpen] = useState(false);
  const [ask, setAsk] = useState("");
  const [askMatches, setAskMatches] = useState<Array<{ paper: string; paperId: string; column: string; value: string; quote: string; source: string; confidence: string }>>([]);
  const [askSubmitted, setAskSubmitted] = useState(false);
  const [customColumnOpen, setCustomColumnOpen] = useState(false);
  const [customColumnName, setCustomColumnName] = useState("");
  const tableColumns = response?.custom_columns_resolved || customColumns.split(",").map((column) => column.trim()).filter(Boolean);

  useEffect(() => {
    const syncViewFromUrl = () => setActiveView(new URLSearchParams(window.location.search).get("view") === "insights" ? "insights" : "table");
    window.addEventListener("popstate", syncViewFromUrl);
    return () => window.removeEventListener("popstate", syncViewFromUrl);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (activeView === "insights") {
      url.searchParams.set("view", "insights");
      if (!url.searchParams.has("tab")) url.searchParams.set("tab", "overview");
    } else {
      url.searchParams.delete("view");
      url.searchParams.delete("tab");
    }
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, [activeView]);

  useEffect(() => {
    if (!selectedEvidence) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setSelectedEvidence(null); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedEvidence]);

  useEffect(() => {
    void fetch(`${apiBaseUrl}/comparison/pdfs/limits`).then((result) => result.ok ? result.json() as Promise<UploadLimits> : null).then((limits) => { if (limits) setUploadLimits(limits); }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!comparisonId) return;
    let cancelled = false;
    void fetch(`${apiBaseUrl}/comparison/pdfs?comparison_id=${encodeURIComponent(comparisonId)}`, { headers: comparisonHeaders() })
      .then(async (result) => {
        if (!result.ok) throw new Error("Could not restore saved PDFs.");
        return result.json() as Promise<{ files: UploadedPdf[] }>;
      })
      .then((saved) => {
        if (cancelled) return;
        setUploadedFiles(saved.files);
        setSelectedPaperCount(saved.files.length + queuedCount.current);
        say(saved.files.length ? "cmpStatusRestored" : "cmpStatusStart");
        if (!insightsRestoreStarted.current && saved.files.length >= 2 && new URLSearchParams(window.location.search).get("view") === "insights") {
          insightsRestoreStarted.current = true;
          window.setTimeout(() => { if (!cancelled) void runComparison(undefined, customColumns, focus, saved.files, true); }, 0);
        }
      })
      .catch(() => { if (!cancelled) { window.localStorage.removeItem("resora-comparison-current-id"); setComparisonId(""); } });
    return () => { cancelled = true; };
  }, [comparisonId]);

  useEffect(() => {
    queuedCount.current = queuedFiles.length;
  }, [queuedFiles]);

  const refreshSaved = () => listSavedComparisons().then((list) => setSavedList(Array.isArray(list) ? list : [])).catch(() => undefined);
  useEffect(() => {
    void refreshSaved();
  }, []);

  // Translated table content belongs to one comparison result in one language.
  useEffect(() => {
    setTranslated({});
    setShowTranslated(false);
  }, [response, interfaceLanguage]);

  // Evidence opened while translation is on: translate that passage too (kept beside the original).
  useEffect(() => {
    const quote = selectedEvidence?.quote;
    if (!showTranslated || !quote || translated[quote] || !comparisonId) return;
    let cancelled = false;
    translateComparisonText(comparisonId, interfaceLanguage, [quote])
      .then(([result]) => { if (!cancelled && result) setTranslated((current) => ({ ...current, [quote]: result })); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [selectedEvidence, showTranslated]);

  // Papers picked in Search or the Reader arrive through the Compare tray (/comparison?from=tray).
  useEffect(() => {
    if (trayImportStarted.current || new URLSearchParams(window.location.search).get("from") !== "tray") return;
    trayImportStarted.current = true;
    const url = new URL(window.location.href);
    url.searchParams.delete("from");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    void importTray();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function importTray() {
    const items = readTray();
    if (!items.length) return;
    setImporting(items.length);
    setResponse(null);
    say("compareImporting", { count: items.length });
    const missing: MissingPaper[] = [];
    const files: File[] = [];
    // Papers open in the Reader with a stored PDF: compare that exact PDF.
    for (const item of items.filter((entry) => entry.reader_doc_id && entry.has_pdf)) {
      try {
        const result = await fetch(readerApi.pdfUrl(item.reader_doc_id as string));
        if (!result.ok) throw new Error(String(result.status));
        const name = `${item.title.replace(/[^\p{L}\p{N} ()._-]/gu, "_").slice(0, 120) || "paper"}.pdf`;
        files.push(new File([await result.blob()], name, { type: "application/pdf" }));
      } catch {
        missing.push({ key: item.key, title: item.title, reason: "no_open_pdf", publisher_url: item.url });
      }
    }
    // Search results: the API fetches each legal open-access PDF and stores it like an upload.
    const byReference = items.filter((entry) => !(entry.reader_doc_id && entry.has_pdf)).map(({ reader_doc_id: _reader, has_pdf: _hasPdf, ...paper }) => paper);
    let added = 0;
    if (byReference.length) {
      try {
        const result = await addPapersToComparison(comparisonId || crypto.randomUUID(), byReference);
        added = result.files.length;
        setUploadedFiles((current) => [...current.filter((file) => !result.files.some((item) => item.id === file.id)), ...result.files]);
        missing.push(...result.unavailable.filter((item) => item.reason !== "duplicate"));
        window.localStorage.setItem("resora-comparison-current-id", result.comparison_id);
        setComparisonId(result.comparison_id);
      } catch {
        missing.push(...byReference.map((paper) => ({ key: paper.key, title: paper.title, reason: "no_open_pdf" as const, publisher_url: paper.url || (paper.doi ? "https://doi.org/" + encodeURIComponent(paper.doi) : null) })));
      }
    }
    if (files.length) setQueuedFiles((current) => [...current, ...files]);
    setSelectedPaperCount((count) => count + files.length + added);
    setMissingPapers((current) => [...current, ...missing.filter((item) => !current.some((other) => other.key === item.key))]);
    clearTray();
    setImporting(0);
    say(files.length + added ? "compareImported" : "compareImportFailed", { count: files.length + added });
  }

  function uploadForMissing(key: string) {
    pendingMissingKey.current = key;
    pickerRef.current?.click();
  }

  const selectedRow = useMemo(
    () => response?.rows.find((row) => row.paper_id === selectedRowId) || response?.rows[0],
    [response, selectedRowId],
  );

  async function runComparison(event?: FormEvent<HTMLFormElement>, columns = customColumns, decision = focus, restoredFiles?: UploadedPdf[], keepInsights = false) {
    event?.preventDefault();
    const currentFiles = restoredFiles || uploadedFiles;
    const count = queuedFiles.length + currentFiles.length;
    if (count < 2 || count > uploadLimits.max_files) {
      if (count < 2) say("cmpStatusNeedTwo");
      else say("cmpStatusMax", { max: uploadLimits.max_files });
      return;
    }
    setLoading(true);
    say("cmpStatusReading");
    try {
      let activeComparisonId = comparisonId || crypto.randomUUID();
      let activeFiles = currentFiles;
      if (queuedFiles.length) {
        const form = new FormData();
        form.append("comparison_id", activeComparisonId);
        queuedFiles.forEach((file) => form.append("files", file, file.name));
        const upload = await fetch(`${apiBaseUrl}/comparison/pdfs/upload`, { method: "POST", headers: comparisonHeaders(), body: form });
        if (!upload.ok) {
          const problem = await upload.json().catch(() => ({}));
          throw new CompareFailure("cmpStatusUploadFailed", undefined, typeof problem.detail === "string" ? problem.detail : "");
        }
        const saved = await upload.json() as { comparison_id: string; files: UploadedPdf[]; stored_notice?: string };
        activeComparisonId = saved.comparison_id;
        activeFiles = [...activeFiles, ...saved.files];
        setUploadedFiles(activeFiles);
        setQueuedFiles([]);
        setComparisonId(activeComparisonId);
        window.localStorage.setItem("resora-comparison-current-id", activeComparisonId);
        say("cmpStatusUploaded");
      }
      const res = await fetch(`${apiBaseUrl}/comparison/pdfs/run`, {
        method: "POST",
        headers: { ...comparisonHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ comparison_id: activeComparisonId, file_ids: activeFiles.map((file) => file.id), focus: decision, custom_columns: columns.split(",").map((item) => item.trim()).filter(Boolean) }),
      });
      if (!res.ok) {
        const problem = await res.json().catch(() => ({}));
        throw new CompareFailure("cmpStatusRunFailed", { status: res.status }, typeof problem.detail === "string" ? problem.detail : "");
      }
      const data = (await res.json()) as ComparisonResponse;
      setResponse(data);
      setActiveView(keepInsights ? "insights" : "table");
      setSelectedPaperCount(data.comparison_count);
      setSelectedRowId(data.rows[0]?.paper_id || "");
      setSelectedEvidence(null);
      say("cmpStatusCompared", { count: data.comparison_count });
      const savedColumns = columns.split(",").map((item) => item.trim()).filter(Boolean);
      void saveComparison(activeComparisonId, { default_name: decision !== NO_FOCUS ? decision : data.rows[0]?.title || "", focus: decision, columns: savedColumns }).then(refreshSaved).catch(() => undefined);
    } catch (error) {
      if (error instanceof CompareFailure) {
        if (error.detail) console.warn("[compare]", error.detail);
        if (error.detail && interfaceLanguage === "en") setStatusMsg({ text: error.detail });
        else say(error.key, error.values);
      } else {
        say("cmpStatusFailed");
      }
    } finally {
      setLoading(false);
    }
  }

  async function uploadManualPapers(files: FileList | null) {
    if (!files?.length) return;
    const incoming = Array.from(files);
    const currentCount = queuedFiles.length + uploadedFiles.length;
    if (currentCount + incoming.length > uploadLimits.max_files) { say("cmpStatusMax", { max: uploadLimits.max_files }); return; }
    const allowed = incoming.filter((file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
    if (allowed.length !== incoming.length) { say("cmpStatusPdfOnly"); return; }
    const tooLarge = allowed.find((file) => file.size > uploadLimits.max_bytes);
    if (tooLarge) { say("cmpStatusTooLarge", { name: tooLarge.name, mb: Math.round(uploadLimits.max_bytes / (1024 * 1024)) }); return; }
    const duplicate = allowed.find((file) => [...queuedFiles, ...incoming.slice(0, incoming.indexOf(file)), ...uploadedFiles.map((item) => ({ name: item.name, size: item.size } as File))].some((other) => other.name === file.name && other.size === file.size));
    if (duplicate) { say("cmpStatusDuplicate", { name: duplicate.name }); return; }
    setQueuedFiles((current) => [...current, ...allowed]);
    setSelectedPaperCount(currentCount + allowed.length);
    if (pendingMissingKey.current) {
      const resolved = pendingMissingKey.current;
      setMissingPapers((current) => current.filter((item) => item.key !== resolved));
      pendingMissingKey.current = null;
    }
    setResponse(null);
    say("cmpStatusSelected", { count: currentCount + allowed.length, max: uploadLimits.max_files });
  }

  function removeQueuedFile(index: number) {
    setQueuedFiles((files) => { const next = files.filter((_, itemIndex) => itemIndex !== index); setSelectedPaperCount(next.length + uploadedFiles.length); return next; });
    setResponse(null);
  }

  function removeUploadedFile(file: UploadedPdf) {
    void fetch(`${apiBaseUrl}/comparison/pdfs/${file.id}`, { method: "DELETE", headers: comparisonHeaders() }).catch(() => undefined);
    const remaining = uploadedFiles.filter((item) => item.id !== file.id);
    setUploadedFiles(remaining);
    setSelectedPaperCount(remaining.length + queuedFiles.length);
    setResponse(null);
    say("cmpStatusRemoved");
    if (remaining.length === 0) window.localStorage.removeItem("resora-comparison-current-id");
  }

  async function openUploadedPdf(paperId: string, page?: number) {
    const fileId = paperId.replace(/^pdf:/, "");
    const preview = window.open("about:blank", "_blank");
    if (preview) preview.opener = null;
    try {
      const result = await fetch(`${apiBaseUrl}/comparison/pdfs/${fileId}`, { headers: comparisonHeaders() });
      if (!result.ok) throw new CompareFailure("cmpOpenPrivateFailed");
      const blobUrl = URL.createObjectURL(await result.blob());
      if (preview) preview.location.href = page ? `${blobUrl}#page=${page}` : blobUrl;
      else throw new CompareFailure("cmpAllowPopups");
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
    } catch (error) {
      preview?.close();
      say(error instanceof CompareFailure ? error.key : "cmpOpenFailed");
    }
  }

  function downloadExport(kind: "csv" | "latex" | "markdown" | "json") {
    if (!response) return;
    const content = kind === "csv" ? response.export_csv : kind === "latex" ? response.export_latex : kind === "json" ? response.export_json || "" : response.export_markdown || "";
    const extension = kind === "latex" ? "tex" : kind === "markdown" ? "md" : kind;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `resora-comparison.${extension}`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    say("cmpExportDone", { kind: kind === "markdown" ? "Markdown" : kind.toUpperCase() });
    setExportOpen(false);
  }

  /** The table exactly as shown (labels in the interface language, values translated when that view is on). */
  function exportTable(): ExportTable | null {
    if (!response) return null;
    const columns = tableColumns.map((key) => ({ key, label: copy.column(key) }));
    return {
      title: copy.label(response.focus) === response.focus && response.focus !== NO_FOCUS ? response.focus : t("cmpHeroTitle"),
      columns,
      rows: response.rows.map((row) => ({
        title: row.title,
        cells: Object.fromEntries(tableColumns.map((column) => {
          const value = row.extracted_columns?.[column] || "Not found";
          const missing = value === "Not found" || value === "Not reported";
          return [column, { value: missing ? t("cmpNotLocated") : copy.content(value), quote: row.evidence?.[column] || "", source: copy.label(row.evidence_source?.[column] || "Uploaded PDF text"), confidence: missing ? "" : copy.label(row.confidence_by_column?.[column] || "low") }];
        })),
      })),
      labels: {
        paper: t("cmpPaper"), column: t("cmpColumnHeader"), value: t("cmpValueHeader"), quote: t("cmpSourcePassage"), source: t("cmpSourceHeader"), confidence: t("cmpConfidenceHeader"),
        sheetTable: t("cmpSheetComparison"), sheetEvidence: t("cmpEvidence"), reportTitle: t("cmpReportTitle"),
        generated: t("cmpReportGenerated", { date: new Intl.DateTimeFormat(interfaceLanguage, { dateStyle: "long" }).format(new Date()) }), note: t("cmpReportNote"),
      },
      rtl,
      language: interfaceLanguage,
    };
  }

  /** Save the compared papers to the Library (title and year as found in each PDF). */
  async function saveRowsToLibrary() {
    setExportOpen(false);
    if (!response) return;
    try {
      await libraryApi.save(response.rows.map((row) => ({ title: row.title, year: row.year ?? null })), { source: "compare" });
      say("savedToLibrary");
    } catch {
      say("saveFailed");
    }
  }

  function exportXlsx() {
    const table = exportTable();
    if (!table) return;
    downloadBlob(comparisonXlsx(table), "resora-comparison.xlsx");
    say("cmpExportDone", { kind: "Excel" });
    setExportOpen(false);
  }

  function exportPdfReport() {
    const table = exportTable();
    if (!table) return;
    printComparisonReport(table);
    say("cmpReportOpened");
    setExportOpen(false);
  }

  function applyTemplate(id: string) {
    const template = COLUMN_TEMPLATES.find((item) => item.id === id);
    if (!template) return;
    const next = template.columns.join(", ");
    setCustomColumns(next);
    say("cmpTemplateApplied", { name: t(template.name) });
    if (response && selectedPaperCount >= 2) void runComparison(undefined, next);
  }

  /** Translate the visible table values and the takeaway (private content; cached per comparison). */
  async function toggleTranslation() {
    if (showTranslated) { setShowTranslated(false); return; }
    if (!response || !comparisonId) return;
    const texts = [...new Set([
      ...response.rows.flatMap((row) => tableColumns.map((column) => row.extracted_columns?.[column] || "")),
      response.insights_model?.takeaway || "",
      ...(response.insights_model?.key_numbers || []).flatMap((item) => [item.label, item.source]),
    ])].filter((text) => text && text !== "Not found" && text !== "Not reported" && !translated[text] && /\p{L}{2}/u.test(text)).slice(0, 300);
    if (!texts.length) { setShowTranslated(true); return; }
    setTranslating(true);
    try {
      const results = await translateComparisonText(comparisonId, interfaceLanguage, texts);
      setTranslated((current) => ({ ...current, ...Object.fromEntries(texts.map((text, index) => [text, results[index] || text])) }));
      setShowTranslated(true);
    } catch {
      say("cmpTranslateFailed");
    } finally {
      setTranslating(false);
    }
  }

  function startNewComparison() {
    window.localStorage.removeItem("resora-comparison-current-id");
    setComparisonId("");
    setUploadedFiles([]);
    setQueuedFiles([]);
    setMissingPapers([]);
    setResponse(null);
    setSelectedEvidence(null);
    setSelectedPaperCount(0);
    setFocus(NO_FOCUS);
    setCustomColumns(DEFAULT_COLUMNS);
    say("cmpStatusStart");
  }

  function openSaved(item: SavedComparison) {
    setRenaming(null);
    setConfirmDelete("");
    if (item.comparison_id === comparisonId) return;
    setResponse(null);
    setQueuedFiles([]);
    setMissingPapers([]);
    setSelectedEvidence(null);
    setFocus(item.focus || NO_FOCUS);
    setCustomColumns(item.columns?.length ? item.columns.join(", ") : DEFAULT_COLUMNS);
    window.localStorage.setItem("resora-comparison-current-id", item.comparison_id);
    setComparisonId(item.comparison_id);
  }

  async function renameSaved(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renaming?.name.trim()) return;
    try {
      await saveComparison(renaming.id, { name: renaming.name.trim() });
      setRenaming(null);
      say("cmpSavedRenamed");
      await refreshSaved();
    } catch {
      say("cmpSavedFailed");
    }
  }

  async function deleteSaved(item: SavedComparison) {
    if (confirmDelete !== item.comparison_id) { setConfirmDelete(item.comparison_id); return; }
    setConfirmDelete("");
    try {
      await deleteSavedComparison(item.comparison_id);
      if (item.comparison_id === comparisonId) startNewComparison();
      say("cmpSavedDeleted");
      await refreshSaved();
    } catch {
      say("cmpSavedFailed");
    }
  }

  function addColumn(columnName: string) {
    const cleaned = columnName.trim();
    if (!cleaned) return;
    const current = customColumns.split(",").map((column) => column.trim()).filter(Boolean);
    if (current.some((column) => column.toLowerCase() === cleaned.toLowerCase())) return;
    const nextColumns = [...current, cleaned].join(", ");
    setCustomColumns(nextColumns);
    if (selectedPaperCount >= 2) void runComparison(undefined, nextColumns);
  }

  function askTable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const terms = ask.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((term) => term.length > 2);
    const fieldMatches = (response?.rows || []).flatMap((row) =>
      tableColumns.flatMap((column) => {
        const value = row.extracted_columns?.[column] || "";
        const quote = row.evidence?.[column] || "";
        const searchable = `${row.title} ${column} ${value} ${quote}`.toLowerCase();
        return value && value !== "Not found" && terms.some((term) => searchable.includes(term))
          ? [{ paper: row.title, paperId: row.paper_id, column, value, quote, source: row.evidence_source?.[column] || "Uploaded PDF", confidence: row.confidence_by_column?.[column] || "low" }]
          : [];
      }),
    );
    const profileMatches = (response?.paper_profiles || []).flatMap((profile) => {
      const paper = response?.rows.find((row) => row.paper_id === profile.paper_id);
      if (!paper) return [];
      return (profile.evidence_pages || []).flatMap((item) => {
        const searchable = `${paper.title} ${item.section || ""} ${item.quote}`.toLowerCase();
        return item.quote && terms.some((term) => searchable.includes(term)) ? [{ paper: paper.title, paperId: paper.paper_id, column: item.section || "Full-paper evidence", value: "Source passage", quote: item.quote, source: `Uploaded PDF${item.page ? ` · page ${item.page}` : ""}`, confidence: "medium" }] : [];
      });
    });
    const matches = [...fieldMatches, ...profileMatches].filter((item, index, all) => all.findIndex((candidate) => candidate.paperId === item.paperId && candidate.quote === item.quote) === index).slice(0, 5);
    setAskMatches(matches);
    setAskSubmitted(true);
  }

  const savedDate = (value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(interfaceLanguage, { dateStyle: "medium" }).format(date);
  };
  const focusTitle = (value?: string) => (!value || value === NO_FOCUS ? "" : value);

  return (
    <CompareCopyProvider value={copy}>
    <section className="comparison-shell" data-no-translate="" lang={interfaceLanguage} dir={rtl ? "rtl" : undefined}>
      <section className="comparison-hero">
        <div>
          <h1 className="comparison-title">{focusTitle(response?.focus) || t("cmpHeroTitle")}</h1>
          <p className="comparison-subtitle">
            {response
              ? t("cmpResultSubtitle", { count: response.comparison_count })
              : t("cmpHeroSubtitle")}
          </p>
          <div className="comparison-action-row">
            {(response || selectedPaperCount > 0) ? <label className="comparison-manual-upload">{t("cmpAddPdfs")}<input type="file" accept="application/pdf,.pdf" multiple disabled={selectedPaperCount >= uploadLimits.max_files || loading} onChange={(event) => { void uploadManualPapers(event.currentTarget.files); event.currentTarget.value = ""; }} /></label> : null}
            {response ? <div className="comparison-export-wrap">
              <button type="button" onClick={() => setExportOpen((open) => !open)} className="resora-button-secondary" aria-haspopup="menu" aria-expanded={exportOpen}>{t("cmpExport")}</button>
              {exportOpen ? <div className="comparison-export-menu" role="menu">
                <button type="button" role="menuitem" onClick={() => void saveRowsToLibrary()}>{t("libSaveToLibrary")}</button>
                <button type="button" role="menuitem" onClick={exportXlsx}>{t("cmpExportXlsx")}</button>
                <button type="button" role="menuitem" onClick={exportPdfReport}>{t("cmpExportPdf")}</button>
                <button type="button" role="menuitem" onClick={() => downloadExport("csv")}>{t("cmpExportCsv")}</button>
                <button type="button" role="menuitem" onClick={() => downloadExport("markdown")}>{t("cmpExportMarkdownShort")}</button>
                <button type="button" role="menuitem" onClick={() => downloadExport("json")}>{t("cmpExportJsonShort")}</button>
              </div> : null}
            </div> : null}
            {response ? <button type="button" onClick={() => navigate(`/gaps?focus=${encodeURIComponent(response.focus)}`)} className="resora-button-secondary">{t("cmpFindGaps")}</button> : null}
            {!response && selectedPaperCount > 0 ? <button type="button" className="resora-button-primary" onClick={() => void runComparison()} disabled={loading || selectedPaperCount < 2}>{loading ? t("cmpComparing") : t("cmpCompare")}</button> : null}
          </div>
        </div>
        <div className="comparison-status-card">
          <p className="resora-label">{t("cmpRunStatus")}</p>
            <strong>{response?.comparison_count ?? selectedPaperCount}</strong>
          <p>{status}</p>
          <div className="comparison-mini-grid">
            <Metric label={t("cmpPapers")} value={response?.comparison_count ?? selectedPaperCount} />
            <Metric label={t("cmpMax")} value={response?.max_supported_papers ?? 15} />
          </div>
        </div>
      </section>

      {!response ? <section className="comparison-upload-page">
        <input ref={pickerRef} className="comparison-file-picker" type="file" accept="application/pdf,.pdf" multiple onChange={(event) => { void uploadManualPapers(event.currentTarget.files); event.currentTarget.value = ""; }} />
        {savedList.length ? <section className="cmp-saved" aria-label={t("cmpSaved")}>
          <div className="cmp-saved-head"><p className="resora-label">{t("cmpSaved")}</p>{comparisonId && (uploadedFiles.length || queuedFiles.length) ? <button type="button" className="cmp-saved-new" onClick={startNewComparison}>+ {t("cmpNewComparison")}</button> : null}</div>
          <ul>
            {savedList.slice(0, 12).map((item) => <li key={item.comparison_id} className={item.comparison_id === comparisonId ? "is-current" : ""}>
              {renaming?.id === item.comparison_id ? <form className="cmp-saved-rename" onSubmit={(event) => void renameSaved(event)}>
                <label className="sr-only" htmlFor={`cmp-rename-${item.comparison_id}`}>{t("cmpSavedNameLabel")}</label>
                <input id={`cmp-rename-${item.comparison_id}`} value={renaming.name} maxLength={160} autoFocus onChange={(event) => setRenaming({ id: item.comparison_id, name: event.target.value })} onKeyDown={(event) => { if (event.key === "Escape") setRenaming(null); }} />
                <button type="submit" disabled={!renaming.name.trim()}>{t("cmpSave")}</button>
                <button type="button" onClick={() => setRenaming(null)}>{t("cmpCancel")}</button>
              </form> : <>
                <button type="button" className="cmp-saved-open" onClick={() => openSaved(item)} aria-current={item.comparison_id === comparisonId ? "true" : undefined}>
                  <strong><bdi>{item.name || t("cmpUntitled")}</bdi></strong>
                  <small>{t("cmpSavedMeta", { count: item.file_count, date: savedDate(item.updated_at) })}{item.comparison_id === comparisonId ? ` · ${t("cmpCurrent")}` : ""}</small>
                </button>
                <button type="button" className="cmp-saved-action" onClick={() => { setConfirmDelete(""); setRenaming({ id: item.comparison_id, name: item.name || "" }); }}>{t("cmpSavedRename")}</button>
                <button type="button" className={`cmp-saved-action${confirmDelete === item.comparison_id ? " is-danger" : ""}`} onClick={() => void deleteSaved(item)} onBlur={() => window.setTimeout(() => setConfirmDelete((current) => (current === item.comparison_id ? "" : current)), 200)}>{confirmDelete === item.comparison_id ? t("cmpSavedConfirmDelete") : t("cmpSavedDelete")}</button>
              </>}
            </li>)}
          </ul>
        </section> : null}
        {importing ? <div className="cmp-import-banner" role="status"><span className="cmp-spinner" aria-hidden="true" />{t("compareImporting", { count: importing })}</div> : null}
        {selectedPaperCount === 0 && !missingPapers.length && !importing ? <button type="button" className={`comparison-dropzone${dragging ? " is-dragging" : ""}`} onClick={() => pickerRef.current?.click()} onPaste={(event) => { if (event.clipboardData.files.length) { event.preventDefault(); void uploadManualPapers(event.clipboardData.files); } }} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void uploadManualPapers(event.dataTransfer.files); }} aria-label={t("cmpDropzoneLabel")}>
          <span className="comparison-upload-icon" aria-hidden="true">↑</span><strong>{t("cmpDropHere")}</strong><span>{t("cmpOr")}</span><em>{t("cmpChoosePdfs")}</em><small>{t("cmpDropLimits", { max: uploadLimits.max_files, mb: Math.round(uploadLimits.max_bytes / (1024 * 1024)), pages: uploadLimits.max_pages })}</small>
        </button> : <div className="comparison-files-card">
          <div className="comparison-files-heading"><div><p className="resora-label">{t("cmpYourPdfs")}</p><span>{t("cmpYourPdfsNote")}</span></div><strong>{t("cmpSelectedOf", { count: selectedPaperCount, max: uploadLimits.max_files })}</strong></div>
          {[...uploadedFiles.map((file) => ({ name: file.name, size: file.size, pages: file.pages, id: file.id, saved: true })), ...queuedFiles.map((file, index) => ({ name: file.name, size: file.size, pages: 0, id: String(index), saved: false }))].map((file) => <div className="comparison-file-row" key={file.id}><span className="comparison-file-icon" aria-hidden="true">PDF</span><div><strong><bdi>{file.name}</bdi></strong><small>{file.pages ? t("cmpFilePages", { count: file.pages }) : t("cmpReadyToUpload")} · {(file.size / (1024 * 1024)).toFixed(1)} MB · {file.saved ? t("cmpStored") : t("cmpReady")}</small></div><button type="button" aria-label={t("cmpRemoveFile", { name: file.name })} onClick={() => file.saved ? removeUploadedFile(uploadedFiles.find((item) => item.id === file.id)!) : removeQueuedFile(Number(file.id))}>×</button></div>)}
          {missingPapers.length ? <ul className="cmp-missing" aria-label={t("compareMissingTitle")}>
            {missingPapers.map((item) => {
              const subscriptionMayBeRequired = item.reason === "no_open_pdf";
              const publisherUrl = subscriptionMayBeRequired ? safePaperPageUrl(item.publisher_url) : null;
              return <li key={item.key} className="cmp-missing-row">
                <span className="cmp-missing-icon" aria-hidden="true">!</span>
                <div>
                  <strong><bdi>{item.title}</bdi></strong>
                  <small>{subscriptionMayBeRequired ? t("compareSubscriptionTitle") + " ? " + t("compareSubscriptionHint") : t("compareMissingTitle") + " ? " + t(MISSING_REASON[item.reason])}</small>
                  {publisherUrl ? <a className="cmp-publisher-link" href={publisherUrl} target="_blank" rel="noreferrer">{t("compareVisitPaper")}</a> : null}
                </div>
                <button type="button" className="cmp-missing-upload" onClick={() => uploadForMissing(item.key)} disabled={selectedPaperCount >= uploadLimits.max_files || loading}>{t("compareUploadPdf")}</button>
                <button type="button" className="cmp-missing-remove" onClick={() => setMissingPapers((current) => current.filter((other) => other.key !== item.key))}>{t("compareRemove")}</button>
              </li>;
            })}
          </ul> : null}
          <button type="button" className="comparison-add-more" onClick={() => pickerRef.current?.click()} disabled={selectedPaperCount >= uploadLimits.max_files || loading}>{t("cmpAddMorePdfs")}</button>
          <div className="comparison-upload-options"><label><span>{t("cmpFocusLabel")}</span><input value={focus === NO_FOCUS ? "" : focus} onChange={(event) => setFocus(event.target.value || NO_FOCUS)} placeholder={t("cmpFocusPlaceholder")} /></label><label><span>{t("cmpExtractionColumns")}</span><input value={customColumns} onChange={(event) => setCustomColumns(event.target.value)} /></label></div>
          <TemplatePicker current={customColumns} onPick={applyTemplate} />
          <div className="comparison-submit-row"><span role="status">{status}</span><button type="button" className="resora-button-primary" onClick={() => void runComparison()} disabled={loading || selectedPaperCount < 2}>{loading ? t("cmpComparing") : t("cmpCompare")}</button></div>
        </div>}
        <p className="comparison-storage-note">{t("cmpStorageNote")}</p>
      </section> : <div className={`comparison-grid${activeView === "insights" ? " is-insights-view" : ""}`}>
        <form id="comparison-controls-form" onSubmit={runComparison} className="comparison-controls">
          <p className="resora-label">{t("cmpControls")}</p>
          <label>
            <span>{t("cmpResearchDecision")}</span>
            <input value={focus === NO_FOCUS ? "" : focus} placeholder={t("cmpResearchQuestion")} onChange={(event) => setFocus(event.target.value || NO_FOCUS)} className="resora-input" />
          </label>
          <label>
            <span>{t("cmpCustomColumns")}</span>
            <textarea value={customColumns} onChange={(event) => setCustomColumns(event.target.value)} className="resora-input min-h-[110px]" />
          </label>
          <TemplatePicker current={customColumns} onPick={applyTemplate} compact />
          <button type="submit" className="resora-button-primary comparison-run-button" disabled={loading}>
            {loading ? t("cmpComparing") : t("cmpCompareSelected")}
          </button>
          {response ? <div className="comparison-snapshot">
            <span>{t("cmpSnapshot")}</span>
            <strong>{response.comparison_snapshot_id}</strong>
            <span>{t("cmpReviewExport")}</span>
            <strong>{response.literature_review_export_job?.job_id || response.literature_review_export_job?.status || t("cmpPreparing")}</strong>
          </div> : null}
        </form>

        <main className="comparison-main">
          <div className="comparison-view-toolbar">
            <div className="comparison-view-switch" role="tablist" aria-label={t("cmpViewLabel")}>
              <button type="button" role="tab" aria-selected={activeView === "table"} className={activeView === "table" ? "active" : ""} onClick={() => setActiveView("table")}>{t("cmpTable")}</button>
              <button type="button" role="tab" aria-selected={activeView === "insights"} className={activeView === "insights" ? "active" : ""} onClick={() => setActiveView("insights")} disabled={!response}>{t("cmpInsights")}</button>
            </div>
            {response && interfaceLanguage !== "en" ? <button type="button" onClick={() => void toggleTranslation()} className={`cmp-translate-toggle${showTranslated ? " is-on" : ""}`} aria-pressed={showTranslated} disabled={translating}><span aria-hidden="true">文A</span>{translating ? t("cmpTranslating") : showTranslated ? t("cmpShowOriginal") : t("cmpTranslateContent", { language: languageName(interfaceLanguage) })}</button> : null}
            {response ? <div className="comparison-confidence-legend" aria-label={t("cmpConfidenceLevels")}>
              <span data-level="high">{t("cmpHigh")}</span><span data-level="medium">{t("cmpMedium")}</span><span data-level="low">{t("cmpLow")}</span>
            </div> : null}
          </div>
          {showTranslated ? <p className="cmp-translated-note" role="note">{t("cmpTranslatedNote")}</p> : null}
          {activeView === "table" ? <section className="comparison-table-card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="resora-label">{t("cmpSideBySide")}</p>
                <h2>{focusTitle(response?.focus || focus) || t("cmpResearchQuestion")}</h2>
              </div>
              {response ? <div className="comparison-action-row">
                <button type="button" onClick={exportXlsx} className="resora-button-secondary">{t("cmpExportXlsx")}</button>
                <button type="button" onClick={() => downloadExport("markdown")} className="resora-button-secondary">{t("cmpExportMarkdown")}</button>
                <button type="button" onClick={() => downloadExport("json")} className="resora-button-secondary">{t("cmpExportJson")}</button>
              </div> : null}
            </div>

            <div className={`comparison-table-wrap${tableColumns.length > 8 ? " has-many-columns" : ""}`}>
              <table>
                <colgroup>
                  <col style={{ width: "18%" }} />
                  {tableColumns.map((column) => <col key={`col-${column}`} style={{ width: `${82 / Math.max(tableColumns.length, 1)}%` }} />)}
                </colgroup>
                <thead>
                  <tr>
                    {["Paper", ...tableColumns].map((head, index) => (
                      <th key={head} scope="col">{index === 0 ? t("cmpPaper") : copy.column(head)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {!response ? <tr><td colSpan={tableColumns.length + 1} className="comparison-empty-state">{t("cmpEmptyTable")}</td></tr> : null}
                  {(response?.rows || []).map((row) => (
                    <tr
                      key={row.paper_id}
                      className={selectedRow?.paper_id === row.paper_id ? "comparison-row-active" : ""}
                      aria-selected={selectedRow?.paper_id === row.paper_id}
                      tabIndex={0}
                      onClick={() => setSelectedRowId(row.paper_id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedRowId(row.paper_id);
                        }
                      }}
                    >
                      <th scope="row" className="comparison-paper-cell">
                        <button type="button" className="comparison-paper-open" onClick={(event) => { event.stopPropagation(); void openUploadedPdf(row.paper_id); }}><bdi>{row.title}</bdi></button>
                        <span>{(() => { const pages = uploadedFiles.find((file) => `pdf:${file.id}` === row.paper_id)?.pages; return pages ? t("cmpPagesUploaded", { pages }) : t("cmpSrcPdf"); })()}</span>
                      </th>
                      {tableColumns.map((column) => {
                        const value = row.extracted_columns?.[column] || "Not found";
                        const quote = row.evidence?.[column];
                        const missing = value === "Not found" || value === "Not reported";
                        const missingLabel = value === "Not applicable: book" ? value : "Not located in extracted PDF text";
                        const confidence = row.confidence_by_column?.[column] || "low";
                        return <td key={`${row.paper_id}-${column}`}>
                          <button type="button" title={quote || (missing ? t("cmpNoConfidentPassage") : copy.content(value))} className={`comparison-cell-value${missing ? " is-missing" : ""}${selectedEvidence?.paperId === row.paper_id && selectedEvidence.column === column ? " is-selected" : ""}`} onClick={() => { setSelectedRowId(row.paper_id); setSelectedEvidence({ paper: row.title, paperId: row.paper_id, column, value: missing ? missingLabel : value, quote: quote || "", source: row.evidence_source?.[column] || "Uploaded PDF text", confidence }); }}>
                            {!missing ? <i className={`comparison-confidence-dot is-${confidence}`} aria-hidden="true" /> : null}<span dir={missing ? undefined : "auto"}>{missing ? t("cmpNotLocated") : copy.content(value)}</span>
                          </button>
                        </td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <footer className="comparison-table-footer">
              <span>{t("cmpAddColumn")}</span>
              {SUGGESTED_COLUMNS.filter((suggestion) => !tableColumns.some((column) => column.toLowerCase() === suggestion.toLowerCase() || (suggestion === "Code available" && column.toLowerCase() === "reproducibility"))).map((suggestion) => <button key={suggestion} type="button" onClick={() => addColumn(suggestion)}>{copy.column(suggestion)}</button>)}
              <button type="button" className="is-custom" aria-expanded={customColumnOpen} onClick={() => setCustomColumnOpen((open) => !open)}>{t("cmpCustom")}</button>
            </footer>
            {customColumnOpen ? <form className="comparison-custom-column" onSubmit={(event) => { event.preventDefault(); addColumn(customColumnName); setCustomColumnName(""); setCustomColumnOpen(false); }}>
              <label htmlFor="comparison-custom-column-name">{t("cmpColumnName")}</label>
              <input id="comparison-custom-column-name" value={customColumnName} onChange={(event) => setCustomColumnName(event.target.value)} placeholder={t("cmpColumnPlaceholder")} maxLength={120} autoFocus />
              <button type="submit" disabled={!customColumnName.trim()}>{t("cmpAddColumn")}</button>
            </form> : null}
          </section> : null}

          {response && activeView === "insights" ? (
            <>
              <ComparisonInsights response={response} comparisonId={comparisonId} columns={tableColumns} onSelectEvidence={(evidence) => { setSelectedRowId(evidence.paperId); setSelectedEvidence(evidence); }} />
            </>
          ) : null}
        </main>

        {selectedEvidence ? <aside className="comparison-side comparison-evidence-panel" aria-label={t("cmpSourceEvidence")}>
          <div className="comparison-side-card">
            <div className="comparison-evidence-heading"><p className="resora-label">{t("cmpEvidence")}</p><button type="button" aria-label={t("cmpCloseEvidence")} onClick={() => setSelectedEvidence(null)}>×</button></div>
            {selectedEvidence ? (
              <>
                <h3>{copy.label(selectedEvidence.column)} · <bdi>{selectedEvidence.paper}</bdi></h3>
                <p className="comparison-evidence-context"><bdi>{selectedEvidence.paper}</bdi>{" \u00B7 "}{copy.label(selectedEvidence.column)}</p>
                <h3 className="comparison-evidence-value" dir="auto">{copy.content(copy.label(selectedEvidence.value))}</h3>
                <p className="comparison-evidence-confidence"><i className={`comparison-confidence-dot is-${selectedEvidence.confidence}`} />{t("cmpConfidence", { level: copy.label(["high", "low"].includes(selectedEvidence.confidence) ? selectedEvidence.confidence : "medium") })}</p>
                {selectedEvidence.quote ? <blockquote><span aria-hidden="true">&ldquo;</span><em dir="auto">{selectedEvidence.quote}</em><small>{showTranslated && translated[selectedEvidence.quote] ? `${t("cmpOriginalPassage")} · ` : ""}{copy.label(selectedEvidence.source)}</small></blockquote> : <p>{selectedEvidence.value.includes("full paper") ? t("cmpNoFullPaperDetail") : selectedEvidence.value.startsWith("Not found") || selectedEvidence.value.startsWith("Not in") ? t("cmpDetailNotFound") : t("cmpNoSourcePassage")}</p>}
                {selectedEvidence.quote && showTranslated && translated[selectedEvidence.quote] ? <blockquote className="cmp-quote-translation"><em>{translated[selectedEvidence.quote]}</em><small>{t("cmpTranslatedPassage")}</small></blockquote> : null}
                {selectedEvidence.quote ? <button type="button" className="resora-button-primary comparison-open-reader" onClick={() => { const page = Number(selectedEvidence.source.match(/page (\d+)/i)?.[1]); void openUploadedPdf(selectedEvidence.paperId, page || undefined); }}>{t("cmpOpenInPdf")}</button> : null}
                <p>{copy.label(selectedEvidence.source)} · {t("cmpConfidence", { level: copy.label(["high", "low"].includes(selectedEvidence.confidence) ? selectedEvidence.confidence : "medium") })}</p>
              </>
            ) : selectedRow ? (
              <>
                <h3><bdi>{selectedRow.title}</bdi></h3>
                <p>{t("cmpSelectCell")}</p>
              </>
            ) : <p>{t("cmpSelectCell")}</p>}
          </div>
          <div className="hidden">
            <p className="resora-label">Feature coverage</p>
            {[
              "10+ paper comparison",
              "custom columns",
              "heatmaps",
              "leaderboards",
              "dendrogram clusters",
              "timeline",
              "contradiction highlighting",
              "dataset overlap",
              "citation Venn",
              "review export",
            ].map((item) => <span key={item} className="comparison-check">{item}</span>)}
          </div>
        </aside> : null}
      </div>}
      {response ? <section className="comparison-ask-area">
        <form className="comparison-ask-bar" onSubmit={askTable}>
          <span className="comparison-ask-sparkle" aria-hidden="true">✧</span>
          <input value={ask} onChange={(event) => setAsk(event.target.value)} placeholder={activeView === "insights" ? t("cmpAskInsights") : t("cmpAskTable")} aria-label={activeView === "insights" ? t("cmpAskInsightsLabel") : t("cmpAskTableLabel")} disabled={!response} />
          <button type="submit" aria-label={t("cmpFindTableEvidence")} disabled={!response || !ask.trim()}><span className="cmp-dir-arrow" aria-hidden="true">→</span></button>
        </form>
        {askSubmitted ? <div className="comparison-ask-results" aria-live="polite">
          <p className="resora-label">{askMatches.length ? t("cmpAskMatches") : t("cmpAskNoMatch")}</p>
          {askMatches.map((match, index) => <button type="button" key={`${match.paperId}-${match.column}-${index}`} onClick={() => { setSelectedRowId(match.paperId); setSelectedEvidence({ paper: match.paper, paperId: match.paperId, column: match.column, value: match.value, quote: match.quote, source: match.source, confidence: match.confidence }); }}>[{String.fromCharCode(65 + Math.max(0, (response?.rows || []).findIndex((item) => item.paper_id === match.paperId)))} · {copy.label(match.column)}] {match.quote || copy.content(copy.label(match.value))}</button>)}
        </div> : null}
      </section> : null}
    </section>
    </CompareCopyProvider>
  );
}

/** Column presets for common study types; the API extracts each named column from the PDFs. */
function TemplatePicker({ current, onPick, compact = false }: { current: string; onPick: (id: string) => void; compact?: boolean }) {
  const { t } = useCompareCopy();
  const normalized = current.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean).join(",");
  return <div className={`cmp-templates${compact ? " is-compact" : ""}`} role="group" aria-label={t("cmpTemplates")}>
    <span>{t("cmpTemplates")}</span>
    {COLUMN_TEMPLATES.map((template) => {
      const active = template.columns.join(",") === normalized;
      return <button type="button" key={template.id} aria-pressed={active} className={active ? "is-on" : ""} onClick={() => onPick(template.id)}>{t(template.name)}</button>;
    })}
  </div>;
}

function LegacyComparisonInsights({
  response,
  comparisonId,
  columns,
  onSelectEvidence,
}: {
  response: ComparisonResponse;
  comparisonId: string;
  columns: string[];
  onSelectEvidence: (evidence: { paper: string; paperId: string; column: string; value: string; quote: string; source: string; confidence: string }) => void;
}) {
  const rows = response.rows;
  const labels = new Map(rows.map((row, index) => [row.paper_id, String.fromCharCode(65 + index)]));
  const fullTextCount = rows.filter((row) => row.full_text_available).length;
  const coverage = columns.map((column) => ({
    column,
    count: rows.filter((row) => {
      const value = row.extracted_columns?.[column] || "";
      return Boolean(value && value !== "Not found" && value !== "Not reported" && !/^(?:not applicable|no named|no single|no empirical|no explicit|no clear|method details not identified|review of prior studies|synthesizes prior findings)/i.test(value));
    }).length,
  }));
  const methodPapers = new Map<string, string[]>();
  for (const row of rows) for (const method of new Set(row.methods || [])) methodPapers.set(method, [...(methodPapers.get(method) || []), row.paper_id]);
  const sharedMethods = [...methodPapers.entries()].filter(([, paperIds]) => paperIds.length > 1).map(([method]) => method);
  const datasetPapers = new Map<string, string[]>();
  for (const row of rows) for (const dataset of new Set(row.datasets || [])) datasetPapers.set(dataset, [...(datasetPapers.get(dataset) || []), row.paper_id]);
  const sharedDatasets = [...datasetPapers.entries()].filter(([, paperIds]) => paperIds.length > 1).map(([dataset]) => dataset);
  const metricComparisons = Object.keys(rows[0]?.result_metrics || {}).flatMap((metric) => {
    const available = rows.filter((row) => row.result_metrics?.[metric] !== undefined);
    if (available.length < 2 || !sharedDatasets.length) return [];
    return sharedDatasets.flatMap((dataset) => {
      const onDataset = available.filter((row) => (row.datasets || []).some((item) => item.toLowerCase() === dataset.toLowerCase()));
      return onDataset.length > 1 ? [{ metric, dataset, rows: onDataset }] : [];
    });
  });
  const uniqueMethodNames = [...methodPapers.keys()];
  const reviewRow = rows.find((row) => row.document_type === "survey");
  const empiricalRows = rows.filter((row) => row.document_type !== "survey" && row.document_type !== "conceptual_article");
  const paperTypeTakeaway = reviewRow && empiricalRows.length
    ? `${reviewRow.title} is a review; ${empiricalRows[0].title} reports original experiments. Their scores cannot be ranked as if they were the same study.`
    : "";
  const takeaway = paperTypeTakeaway || (metricComparisons.length
    ? `The PDFs report comparable ${metricComparisons[0].metric} results on ${metricComparisons[0].dataset}.`
    : sharedMethods.length
      ? `${sharedMethods.join(", ")} appears across the selected papers, but their measured results need a shared benchmark before ranking.`
      : "These papers do not share a named benchmark and metric, so a performance ranking would overstate the evidence.");
  const evidenceFacts = rows.flatMap((row) => columns.flatMap((column) => {
    const value = row.extracted_columns?.[column] || "";
    const quote = row.evidence?.[column] || "";
    if (!quote || value === "Not found" || value === "Not reported" || value.startsWith("Not applicable:")) return [];
    return [{ row, column, value, quote }];
  })).slice(0, 8);
  const coveragePercent = (count: number) => Math.round((count / Math.max(rows.length, 1)) * 100);

  return (
    <div className="comparison-insights-dashboard">
      <header className="comparison-insights-heading">
        <div><p className="resora-label">Full-paper analysis</p><h2>Evidence across {rows.length} PDFs</h2><p>{fullTextCount} of {rows.length} uploaded files had readable full text. Each result below is limited to extracted evidence.</p><small className="comparison-insight-run-status">{response.insights_cached ? "Saved analysis · reused for these PDFs and settings" : "Analysis profile v2 · saved to this comparison"}</small></div>
        <div className="comparison-paper-legend">{rows.map((row) => <span key={row.paper_id}><b>{labels.get(row.paper_id)}</b>{row.title}</span>)}</div>
      </header>

      <section className="comparison-takeaway">
        <div><p className="resora-label">The takeaway</p><h3>{takeaway}</h3><p>Use the source evidence and coverage below to judge what can be compared reliably.</p></div>
        <ol>
          <li><b>01</b><span>{fullTextCount} of {rows.length} PDFs contributed extracted full text.</span></li>
          <li><b>02</b><span>{sharedMethods.length ? `Shared approaches detected: ${sharedMethods.join(", ")}.` : `${uniqueMethodNames.length} approach labels were detected; no common method label was confirmed.`}</span></li>
          <li><b>03</b><span>{sharedDatasets.length ? `Shared named datasets: ${sharedDatasets.join(", ")}.` : rows.some((row) => row.datasets?.length) ? `${rows.filter((row) => row.datasets?.length).map((row) => `${labels.get(row.paper_id)}: ${row.datasets.join(", ")}`).join("; ")}. No dataset is shared across all selected papers.` : "No shared named dataset was confidently identified in the extracted text."}</span></li>
        </ol>
      </section>

      <section className="comparison-insight-grid">
        <article className="comparison-insight-card comparison-insight-coverage">
          <p className="resora-label">Extraction coverage</p><h3>What the PDFs support</h3>
          <p className="comparison-insight-note">Coverage shows how many papers have a usable extracted value for each field.</p>
          <div className="comparison-coverage-list">{coverage.slice(0, 8).map(({ column, count }) => <div key={column}><span>{column}</span><i><b style={{ width: `${coveragePercent(count)}%` }} /></i><strong>{count}/{rows.length}</strong></div>)}</div>
        </article>
        <article className="comparison-insight-card comparison-insight-headtohead">
          <p className="resora-label">Head-to-head</p><h3>{metricComparisons.length ? `${metricComparisons[0].metric} · ${metricComparisons[0].dataset}` : "Comparable scores"}</h3>
          {metricComparisons.length ? metricComparisons[0].rows.map((row) => { const score = row.result_metrics[metricComparisons[0].metric]; return <div className="comparison-score-row" key={row.paper_id}><span><b>{labels.get(row.paper_id)}</b>{row.title}</span><i><b style={{ width: `${Math.max(3, Math.min(100, score * 100))}%` }} /></i><strong>{score <= 1 ? `${(score * 100).toFixed(1)}%` : score.toFixed(2)}</strong></div>; }) : <div className="comparison-no-score"><strong>No fair score comparison yet</strong><p>A score chart appears only when at least two PDFs report the same metric on a shared named dataset. This avoids ranking results from different evaluation settings.</p></div>}
          {metricComparisons.length ? <p className="comparison-insight-note">Only papers with a shared dataset and metric are shown. Check evaluation splits and protocols in the source PDFs.</p> : null}
        </article>
      </section>

      <section className="comparison-insight-card comparison-method-landscape">
        <p className="resora-label">Method landscape</p><h3>Approaches detected in the papers</h3>
        <div>{uniqueMethodNames.length ? uniqueMethodNames.map((method) => <span key={method}><b>{methodPapers.get(method)?.length || 0}</b><strong>{method}</strong><small>{(methodPapers.get(method) || []).map((id) => labels.get(id)).join(" · ")}</small></span>) : <p>No method names were confidently extracted. Inspect the PDF pages or add a method column to focus the extraction.</p>}</div>
      </section>

      <section className="comparison-insight-grid">
        <article className="comparison-insight-card comparison-evidence-findings">
          <p className="resora-label">Evidence</p><h3>Source passages behind the table</h3>
          {evidenceFacts.length ? <div>{evidenceFacts.slice(0, 6).map(({ row, column, value, quote }) => <button type="button" key={`${row.paper_id}-${column}`} onClick={() => onSelectEvidence({ paper: row.title, paperId: row.paper_id, column, value, quote, source: row.evidence_source?.[column] || "Uploaded PDF text", confidence: row.confidence_by_column?.[column] || "medium" })}><span>{labels.get(row.paper_id)} · {column}</span><strong>{value}</strong><q>{quote}</q><small>{row.evidence_source?.[column] || "Uploaded PDF text"} · Open evidence</small></button>)}</div> : <p>No direct passages were matched. Table values without a source excerpt should be checked against the original PDF.</p>}
        </article>
        <article className="comparison-insight-card comparison-reproducibility">
          <p className="resora-label">Reproducibility</p><h3>Can the reported work be rebuilt?</h3>
          <div className="comparison-repro-table"><div><span>Paper</span><span>Full text</span><span>Dataset named</span><span>Code link</span></div>{rows.map((row) => { const code = Object.entries(row.extracted_columns || {}).find(([column]) => /code|reproducibility/i.test(column))?.[1] || "Not found"; const dataset = (row.datasets || []).length > 0; return <div key={row.paper_id}><span><b>{labels.get(row.paper_id)}</b>{row.title}</span><i className={row.full_text_available ? "is-present" : ""} title={row.full_text_available ? "Full text extracted" : "Full text unavailable"} /><i className={dataset ? "is-present" : ""} title={dataset ? "Dataset detected" : "No named dataset detected"} /><i className={code !== "Not found" ? "is-present" : ""} title={code !== "Not found" ? code : "No code link detected"} /></div>})}</div>
          <p className="comparison-insight-note">A missing signal means it was not found by extraction; it does not prove the paper omits it.</p>
        </article>
      </section>

      <section className="comparison-insight-grid comparison-decision-grid">
        <article className="comparison-insight-card comparison-decision-notes"><p className="resora-label">Decision notes</p><h3>Best-supported use</h3><ol>{rows.map((row) => <li key={row.paper_id}><b>{labels.get(row.paper_id)}</b><span><strong>{row.title}</strong><small>{row.extracted_columns?.method && row.extracted_columns.method !== "Not found" ? row.extracted_columns.method : "Method not confidently identified"}{row.extracted_columns?.result && row.extracted_columns.result !== "Not found" ? ` · ${row.extracted_columns.result}` : " · No result statement confidently extracted"}</small></span></li>)}</ol></article>
        <article className="comparison-opportunity-card"><p className="resora-label">Evidence gap</p><h3>{sharedDatasets.length ? "Check the evaluation protocols" : "Build a like-for-like comparison"}</h3><p>{sharedDatasets.length ? `The extracted text names ${sharedDatasets.join(", ")} across papers. Confirm that splits, metrics, and test conditions match before comparing scores.` : "The selected PDFs do not show a shared named dataset. A benchmark-based ranking is not supported yet; compare methods and limitations qualitatively, or add papers that use the same benchmark."}</p><strong>{metricComparisons.length ? "Comparable scores available" : "No comparable score ranking"}</strong></article>
      </section>
      <AdvancedInsights response={response} comparisonId={comparisonId} onSelectEvidence={onSelectEvidence} />
    </div>
  );
}

type InsightsTab = "overview" | "evidence" | "methods" | "reproducibility" | "next";

function ComparisonInsights({ response, comparisonId, columns, onSelectEvidence }: {
  response: ComparisonResponse;
  comparisonId: string;
  columns: string[];
  onSelectEvidence: (evidence: { paper: string; paperId: string; column: string; value: string; quote: string; source: string; confidence: string }) => void;
}) {
  const copy = useCompareCopy();
  const t = copy.t;
  const rows = response.rows;
  const profiles = response.paper_profiles || [];
  const label = (id: string) => String.fromCharCode(65 + Math.max(0, rows.findIndex((row) => row.paper_id === id)));
  const [tab, setTab] = useState<InsightsTab>(() => {
    const params = new URLSearchParams(window.location.search);
    const candidate = params.get("tab");
    return params.get("view") === "insights" && ["overview", "evidence", "methods", "reproducibility", "next"].includes(candidate || "") ? candidate as InsightsTab : "overview";
  });
  const fullText = rows.filter((row) => row.full_text_available).length;
  const byMetric = new Map<string, Set<string>>();
  const byDataset = new Map<string, Set<string>>();
  rows.forEach((row) => {
    Object.keys(row.result_metrics || {}).forEach((metric) => byMetric.set(metric.toLowerCase(), new Set([...(byMetric.get(metric.toLowerCase()) || []), metric])));
    row.datasets.forEach((dataset) => byDataset.set(dataset.toLowerCase(), new Set([...(byDataset.get(dataset.toLowerCase()) || []), row.paper_id])));
  });
  const candidateComparisons = [...byMetric.entries()].flatMap(([metricKey]) => {
    const metric = [...(byMetric.get(metricKey) || [])][0];
    return [...byDataset.entries()].flatMap(([datasetKey]) => {
      const dataset = rows.flatMap((row) => row.datasets).find((name) => name.toLowerCase() === datasetKey) || datasetKey;
      const matching = rows.filter((row) => row.result_metrics?.[metric] !== undefined && Boolean(row.evidence?.result || row.evidence?.[metric]) && row.datasets.some((name) => name.toLowerCase() === datasetKey));
      if (matching.length < 2) return [];
      const splitSignatures = matching.map((row) => profiles.find((profile) => profile.paper_id === row.paper_id)?.datasets_detail.find((item) => item.name.toLowerCase() === datasetKey)?.splits?.map((split) => split.toLowerCase().trim()).filter(Boolean).sort().join("|") || "");
      return [{ metric, dataset, rows: matching, splitsVerified: Boolean(splitSignatures[0]) && splitSignatures.every((signature) => signature === splitSignatures[0]) }];
    });
  });
  const validatedHeadToHead = response.insights_model?.head_to_head;
  const comparisons = validatedHeadToHead ? [{ metric: validatedHeadToHead.metric, dataset: validatedHeadToHead.dataset, rows: validatedHeadToHead.points.map((point) => rows.find((row) => row.paper_id === point.paper_id)).filter((row): row is ComparisonRow => Boolean(row)), splitsVerified: true }] : [];
  const headToHead = comparisons[0];
  const needsSplitReview = !headToHead && candidateComparisons.length > 0;
  const lowerIsBetter = Boolean(headToHead && /error|loss|latency|time|cost|mae|rmse|perplexity/i.test(headToHead.metric));
  const ranked = headToHead ? [...headToHead.rows].sort((a, b) => lowerIsBetter ? a.result_metrics[headToHead.metric] - b.result_metrics[headToHead.metric] : b.result_metrics[headToHead.metric] - a.result_metrics[headToHead.metric]) : [];
  const best = ranked[0];
  const codeCount = profiles.filter((profile) => Boolean(profile.repo_url || profile.reproducibility.code?.status === "reported")).length;
  const preprintCount = profiles.filter((profile) => Boolean(profile.preprint_notice)).length;
  const sharedMethods = [...new Set(rows.flatMap((row) => row.methods))].filter((method) => rows.filter((row) => row.methods.some((item) => item.toLowerCase() === method.toLowerCase())).length > 1);
  const commonWeaknesses = new Map<string, { quote: string; papers: ComparisonRow[] }>();
  rows.forEach((row) => {
    const quote = row.evidence?.limitation || "";
    if (!quote) return;
    const key = quote.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    const entry = commonWeaknesses.get(key) || { quote, papers: [] };
    entry.papers.push(row);
    commonWeaknesses.set(key, entry);
  });
  const commonWeakness = [...commonWeaknesses.values()].filter((item) => item.papers.length >= Math.max(2, Math.ceil(rows.length * 0.6))).sort((a, b) => b.papers.length - a.papers.length)[0];
  const verifiedEvidence = rows.flatMap((row) => columns.flatMap((column) => row.evidence?.[column] ? [{ row, column, quote: row.evidence[column], value: row.extracted_columns?.[column] || "Source passage" }] : []));
  const agreements = [
    ...sharedMethods.flatMap((method) => {
      const members = rows.filter((row) => row.methods.some((item) => item.toLowerCase() === method.toLowerCase()));
      const source = members.map((row) => ({ row, column: Object.keys(row.evidence || {}).find((key) => /method/i.test(key)) || "", quote: Object.entries(row.evidence || {}).find(([key]) => /method/i.test(key))?.[1] || "" })).find((item) => item.column && item.quote);
      return source ? [{ label: t("cmpAppearsIn", { name: method, papers: members.map((row) => label(row.paper_id)).join(", ") }), ...source }] : [];
    }),
    ...[...byDataset.entries()].filter(([, papers]) => papers.size > 1).flatMap(([name, papers]) => {
      const members = rows.filter((row) => papers.has(row.paper_id));
      const source = members.flatMap((row) => (profiles.find((profile) => profile.paper_id === row.paper_id)?.datasets_detail || []).filter((item) => item.name.toLowerCase() === name && item.quote).map((item) => ({ row, column: "Dataset", quote: item.quote || "", page: item.page }))).find((item) => item.quote);
      return source ? [{ label: t("cmpAppearsIn", { name, papers: members.map((row) => label(row.paper_id)).join(", ") }), ...source }] : [];
    }),
  ].slice(0, 5);
  const takeaway = response.insights_model?.takeaway ? copy.content(response.insights_model.takeaway) : t("cmpTakeawayFallback");
  const tabs: Array<{ id: InsightsTab; name: string; show: boolean }> = [
    { id: "overview", name: t("cmpTabOverview"), show: true },
    { id: "evidence", name: t("cmpEvidence"), show: verifiedEvidence.length > 0 || response.contradiction_highlights.length > 0 },
    { id: "methods", name: t("cmpTabMethods"), show: rows.some((row) => row.methods.length || row.datasets.length) || profiles.some((profile) => profile.research_questions.length || profile.datasets_detail.length || profile.key_tables.length || profile.key_figures.length) },
    { id: "reproducibility", name: t("cmpTabRepro"), show: profiles.some((profile) => Object.keys(profile.reproducibility || {}).length || profile.doi || profile.publication_year || profile.preprint_notice) },
    { id: "next", name: t("cmpTabNext"), show: profiles.some((profile) => profile.future_work.length || profile.parsed_references.length) || rows.some((row) => row.evidence?.limitation) },
  ];
  const visibleTabs = tabs.filter((item) => item.show);
  const selectTab = (next: InsightsTab, target?: string) => {
    setTab(next);
    const params = new URLSearchParams(window.location.search);
    params.set("view", "insights"); params.set("tab", next);
    window.history.replaceState(window.history.state, "", `${window.location.pathname}?${params.toString()}${target ? `#${target}` : ""}`);
    if (target) window.setTimeout(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" }), 40);
  };
  useEffect(() => {
    const updateFromUrl = () => {
      const params = new URLSearchParams(window.location.search);
      const value = params.get("tab") as InsightsTab | null;
      if (params.get("view") === "insights" && value && tabs.some((item) => item.id === value && item.show)) setTab(value);
    };
    window.addEventListener("popstate", updateFromUrl);
    return () => window.removeEventListener("popstate", updateFromUrl);
  }, [response]);
  useEffect(() => {
    if (!visibleTabs.some((item) => item.id === tab)) setTab("overview");
  }, [visibleTabs.map((item) => item.id).join("|"), tab]);
  const paperCount = rows.length;
  const numbers = (response.insights_model?.key_numbers || []).slice(0, 3).map((item) => ({
    ...item,
    action: () => {
      const ref = item.evidence[0];
      const paper = rows.find((row) => row.paper_id === ref?.paper_id);
      if (paper && ref) onSelectEvidence({ paper: paper.title, paperId: paper.paper_id, column: ref.field, value: item.value, quote: ref.quote, source: ref.page ? `Uploaded PDF · page ${ref.page}` : "Uploaded PDF text", confidence: "medium" });
    },
  }));
  const pages = new Set(verifiedEvidence.map((item) => evidencePageOf(item.row, item.column, item.quote)).filter(Boolean)).size;
  const moreRows: Array<{ title: string; summary: string; target: InsightsTab; anchor?: string }> = [
    ...(verifiedEvidence.length ? [{ title: t("cmpEvidence"), summary: t("cmpMoreEvidence", { count: verifiedEvidence.length }), target: "evidence" as InsightsTab, anchor: "evidence-passages" }] : []),
    ...(sharedMethods.length || rows.some((row) => row.datasets.length) ? [{ title: t("cmpTabMethods"), summary: t("cmpMoreMethods", { methods: sharedMethods.length, datasets: byDataset.size }), target: "methods" as InsightsTab, anchor: "study-design" }] : []),
    ...(profiles.some((profile) => Object.keys(profile.reproducibility).length || profile.doi) ? [{ title: t("cmpReproTrust"), summary: t("cmpMoreRepro", { count: codeCount, total: paperCount }), target: "reproducibility" as InsightsTab, anchor: "reproducibility-detail" }] : []),
    ...(commonWeakness || profiles.some((profile) => profile.future_work.length || profile.parsed_references.length) ? [{ title: t("cmpTabNext"), summary: t("cmpMoreNext", { count: profiles.filter((profile) => profile.future_work.length).length }), target: "next" as InsightsTab, anchor: "limitations-future" }] : []),
    ...(profiles.some((profile) => profile.key_tables.length || profile.key_figures.length) ? [{ title: t("cmpKeyTables"), summary: t("cmpOpenTables"), target: "methods" as InsightsTab, anchor: "tables-figures" }] : []),
    ...(profiles.some((profile) => profile.parsed_references.length) ? [{ title: t("cmpReadNext"), summary: t("cmpFindShared"), target: "next" as InsightsTab, anchor: "shared-references" }] : []),
    { title: t("cmpClaimChecker"), summary: t("cmpSearchSupporting"), target: "next" as InsightsTab, anchor: "claim-check" },
  ];
  function evidencePageOf(row: ComparisonRow, column: string, quote: string) {
    const profilePage = profiles.find((profile) => profile.paper_id === row.paper_id)?.evidence_pages?.find((item) => item.quote === quote)?.page;
    return profilePage || Number((row.evidence_source?.[column] || "").match(/(?:pdf\s+)?page\s+(\d+)/i)?.[1]) || undefined;
  }
  const evidencePage = (row: ComparisonRow, column: string, quote: string) => {
    const profilePage = profiles.find((profile) => profile.paper_id === row.paper_id)?.evidence_pages?.find((item) => item.quote === quote)?.page;
    const sourcePage = Number((row.evidence_source?.[column] || "").match(/(?:pdf\s+)?page\s+(\d+)/i)?.[1]) || undefined;
    return profilePage || sourcePage;
  };
  const evidenceSource = (row: ComparisonRow, column: string, quote: string) => {
    const page = evidencePage(row, column, quote);
    return page ? `Uploaded PDF · page ${page}` : row.evidence_source?.[column] || "Uploaded PDF";
  };
  const openValue = (row: ComparisonRow, column: string) => {
    const quote = row.evidence?.[column] || "";
    onSelectEvidence({ paper: row.title, paperId: row.paper_id, column, value: row.extracted_columns?.[column] || "Source passage", quote, source: evidenceSource(row, column, quote), confidence: row.confidence_by_column?.[column] || "medium" });
  };
  const openTakeawayEvidence = () => {
    const ref = response.insights_model?.takeaway_evidence[0];
    const paper = rows.find((row) => row.paper_id === ref?.paper_id);
    if (paper && ref) onSelectEvidence({ paper: paper.title, paperId: paper.paper_id, column: ref.field, value: "Takeaway source", quote: ref.quote, source: ref.page ? `Uploaded PDF · page ${ref.page}` : "Uploaded PDF text", confidence: "medium" });
    else if (verifiedEvidence[0]) openValue(verifiedEvidence[0].row, verifiedEvidence[0].column);
  };
  const metricText = (value: number, metric: string) => /accuracy|f1|precision|recall|auc|success rate/i.test(metric) && value <= 1 ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
  const weaknessRows = commonWeakness?.papers || [];

  return <div className="comparison-insights-dashboard comparison-insights-v3" data-tab={tab}>
    <nav className="comparison-insight-tabs" role="tablist" aria-label={t("cmpPaperInsights")}>
      {visibleTabs.map((item) => <button type="button" role="tab" id={`insights-tab-${item.id}`} aria-selected={tab === item.id} aria-controls={`insights-panel-${item.id}`} tabIndex={tab === item.id ? 0 : -1} key={item.id} className={tab === item.id ? "active" : ""} onClick={() => selectTab(item.id)} onKeyDown={(event) => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const current = visibleTabs.findIndex((entry) => entry.id === tab); const step = event.key === "ArrowRight" ? 1 : -1; const next = visibleTabs[(current + step + visibleTabs.length) % visibleTabs.length]; selectTab(next.id); document.getElementById(`insights-tab-${next.id}`)?.focus(); } }}>{item.name}</button>)}
    </nav>
    {tab === "overview" ? <div id="insights-panel-overview" role="tabpanel" aria-labelledby="insights-tab-overview" className="comparison-overview-content">
      <section className="comparison-takeaway comparison-overview-hero"><div><p className="resora-label">{t("cmpTakeawayLabel")}</p><h2><button type="button" className="comparison-takeaway-claim" dir="auto" onClick={openTakeawayEvidence}>{takeaway}</button></h2><button type="button" className="comparison-paper-source-link" onClick={() => selectTab("evidence")}>{t("cmpBasedOn", { papers: best ? label(best.paper_id) : sharedMethods.length ? rows.filter((row) => row.methods.some((method) => sharedMethods.includes(method))).map((row) => label(row.paper_id)).join(", ") : t("cmpPapersCount", { count: paperCount }), evidence: pages ? t("cmpCitedPages", { count: pages }) : t("cmpEvidenceFromPdfs", { count: new Set(verifiedEvidence.map((item) => item.row.paper_id)).size }) })}</button></div></section>
      <section className="comparison-key-numbers" aria-label={t("cmpKeyNumbers")}>{numbers.map((item) => <button type="button" key={`${item.label}-${item.value}`} onClick={item.action}><strong>{item.label === `${headToHead?.metric} · ${headToHead?.dataset}` && best && headToHead ? metricText(best.result_metrics[headToHead.metric], headToHead.metric) : item.value}</strong><b>{copy.content(item.label)}</b><span>{copy.content(item.source)}</span></button>)}</section>
      <section className="comparison-overview-pair">
        <article className="comparison-insight-card comparison-overview-headtohead"><p className="resora-label">{headToHead ? t("cmpHeadToHead") : t("cmpMethodComparison")}</p><h3>{headToHead ? t("cmpMetricOnDataset", { metric: headToHead.metric, dataset: headToHead.dataset }) : t("cmpMethodsAcross")}</h3>
          {headToHead ? <><small>{t("cmpSameSetup")}</small>{ranked.map((row, index) => { const score = row.result_metrics[headToHead.metric]; const topScore = best!.result_metrics[headToHead.metric]; const bar = lowerIsBetter ? (score === 0 ? 100 : Math.abs(topScore / score) * 100) : (topScore === 0 ? 100 : Math.abs(score / topScore) * 100); return <button type="button" className="comparison-score-row" key={row.paper_id} onClick={() => onSelectEvidence({ paper: row.title, paperId: row.paper_id, column: headToHead.metric, value: metricText(score, headToHead.metric), quote: row.evidence?.result || row.evidence?.[headToHead.metric] || "", source: row.evidence_source?.result || "Uploaded PDF", confidence: row.confidence_by_column?.result || "medium" })}><span><b title={row.title}>{label(row.paper_id)}</b><span title={row.title}>{row.title}</span></span><i aria-hidden="true"><b className={index === 0 ? "is-best" : ""} style={{ width: `${Math.max(3, Math.min(100, bar))}%` }} /></i><strong>{metricText(score, headToHead.metric)}</strong></button>; })}</> : [...new Set(rows.flatMap((row) => row.methods))].slice(0, 3).map((method) => <p className="comparison-method-summary" key={method}><b><bdi>{method}</bdi></b><span>{rows.filter((row) => row.methods.includes(method)).map((row) => label(row.paper_id)).join(" · ")}</span></p>)}
        </article>
        <article className="comparison-insight-card comparison-worth-look"><p className="resora-label">{commonWeakness ? t("cmpCommonWeakness") : t("cmpWorthALook")}</p><h3>{commonWeakness ? t("cmpLimitationAcross") : best ? t("cmpCheckConditions") : t("cmpNotComparable")}</h3>
          {commonWeakness ? <><div className="comparison-worth-sides">{weaknessRows.slice(0, 2).map((row) => <button type="button" key={row.paper_id} onClick={() => openValue(row, "limitation")}><b>{label(row.paper_id)}</b><span>{row.evidence.limitation}</span></button>)}</div><small>{t("cmpReportedIn", { count: weaknessRows.length, total: paperCount })}</small><button type="button" className="comparison-text-link" onClick={() => selectTab("evidence", "evidence-passages")}>{t("cmpSeeEvidence")}</button></> : <><p>{needsSplitReview ? t("cmpSplitsUnverified") : best ? t("cmpSplitsMatch") : t("cmpNoSharedMetric")}</p><button type="button" className="comparison-text-link" onClick={() => selectTab("methods", "study-design")}>{t("cmpReviewStudy")}</button></>}
        </article>
      </section>
      {moreRows.length ? <section className="comparison-more-insights"><p className="resora-label">{t("cmpMoreInsights")}</p><div>{moreRows.map((item) => <button type="button" key={`${item.target}-${item.anchor}`} onClick={() => selectTab(item.target, item.anchor)}><span aria-hidden="true">↗</span><b>{item.title}</b><small>{item.summary}</small><strong className="cmp-dir-arrow" aria-hidden="true">→</strong></button>)}</div></section> : null}
    </div> : <div id={`insights-panel-${tab}`} role="tabpanel" aria-labelledby={`insights-tab-${tab}`} className="comparison-insights-detail" data-tab={tab}>
      {tab === "evidence" ? <section id="evidence-passages" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpEvidenceAgreements")}</p><h2>{t("cmpWhatSupport")}</h2>{agreements.length ? <div className="comparison-agreement-list">{agreements.map((item, index) => <button type="button" key={`${item.label}-${index}`} onClick={() => onSelectEvidence({ paper: item.row.title, paperId: item.row.paper_id, column: item.column, value: item.label, quote: item.quote, source: "page" in item && item.page ? `Uploaded PDF · page ${item.page}` : evidenceSource(item.row, item.column, item.quote), confidence: item.row.confidence_by_column?.[item.column] || "medium" })}><span aria-hidden="true">✓</span><strong>{item.label}</strong><small>{t("cmpOpenSource")} · {label(item.row.paper_id)}{"page" in item && item.page ? ` · ${t("cmpPageShort", { page: Number(item.page) })}` : ""}</small></button>)}</div> : null}{verifiedEvidence.length ? <div className="comparison-evidence-list">{verifiedEvidence.slice(0, 8).map(({ row, column, quote, value }) => { const page = evidencePage(row, column, quote); return <button type="button" key={`${row.paper_id}-${column}`} onClick={() => openValue(row, column)}><span><b title={row.title}>{label(row.paper_id)}</b>{copy.column(column)}{page ? ` · ${t("cmpPageShort", { page })}` : ""}</span><strong>{copy.content(copy.label(value))}</strong><q dir="auto">{quote}</q><small>{copy.label(evidenceSource(row, column, quote))} · {t("cmpOpenEvidence")}</small></button>; })}</div> : null}</section> : null}
      <AdvancedInsights response={response} comparisonId={comparisonId} onSelectEvidence={onSelectEvidence} activeTab={tab} />
    </div>}
  </div>;
}

function AdvancedInsights({ response, comparisonId, onSelectEvidence, activeTab = "overview" }: { response: ComparisonResponse; comparisonId: string; onSelectEvidence: (evidence: { paper: string; paperId: string; column: string; value: string; quote: string; source: string; confidence: string }) => void; activeTab?: InsightsTab }) {
  const copy = useCompareCopy();
  const t = copy.t;
  const profiles = response.paper_profiles || [];
  const rows = response.rows;
  const [question, setQuestion] = useState("");
  const [claim, setClaim] = useState("");
  const [consensus, setConsensus] = useState<Array<{ paper: ComparisonRow; stance: string; quote: string }>>([]);
  const [claimResult, setClaimResult] = useState<Array<{ paper: ComparisonRow; quote: string }> | null>(null);
  const [interactionKey, setInteractionMessage] = useState<SearchCopyKey | "">("");
  const [feedbackKey, setFeedbackMessage] = useState<SearchCopyKey | "">("");
  const interactionMessage = interactionKey ? t(interactionKey) : "";
  const feedbackMessage = feedbackKey ? t(feedbackKey) : "";
  const suggestions: Array<{ key: SearchCopyKey; english: string }> = [
    { key: "cmpSuggestImprove", english: "Which papers report an improvement?" },
    { key: "cmpSuggestLimits", english: "What limitations are shared?" },
    { key: "cmpSuggestDatasets", english: "Which datasets are used?" },
  ];
  const sectionName = (key: string) => copy.label(key.replace(/_/g, " "));
  const label = (paperId: string) => String.fromCharCode(65 + Math.max(0, rows.findIndex((row) => row.paper_id === paperId)));
  const openEvidence = (paperId: string, quote: string, page?: number | null, section?: string) => {
    const paper = rows.find((row) => row.paper_id === paperId);
    if (!paper || !quote) return;
    onSelectEvidence({ paper: paper.title, paperId, column: section || "Full-paper evidence", value: page ? `Page ${page}` : "Source passage", quote, source: `Uploaded PDF${page ? ` · page ${page}` : ""}`, confidence: "medium" });
  };
  const sections = [
    { id: "study-design", show: profiles.some((profile) => profile.research_questions.length || profile.contributions.length || profile.baselines.length || profile.experiments.length) },
    { id: "datasets", show: profiles.some((profile) => profile.datasets_detail.length) },
    { id: "reproducibility-detail", show: profiles.some((profile) => Object.keys(profile.reproducibility || {}).length) },
    { id: "limitations-future", show: rows.some((row) => row.evidence?.limitation) || profiles.some((profile) => profile.future_work.length) },
    { id: "tables-figures", show: profiles.some((profile) => profile.key_tables.length || profile.key_figures.length) },
    { id: "shared-references", show: profiles.some((profile) => profile.parsed_references.length) },
    { id: "trust-source", show: profiles.some((profile) => profile.doi || profile.publication_year || profile.preprint_notice) },
    { id: "evolution", show: profiles.some((profile) => profile.publication_year) },
    { id: "relationships", show: rows.some((row) => row.methods.length || row.datasets.length) },
    { id: "research-directions", show: profiles.some((profile) => profile.future_work.length || profile.motivation.length) },
    { id: "gap-signals", show: true },
    { id: "consensus", show: true },
    { id: "claim-check", show: true },
  ].filter((section) => section.show && (
    (activeTab === "methods" && ["study-design", "datasets", "tables-figures", "evolution", "relationships"].includes(section.id)) ||
    (activeTab === "reproducibility" && ["reproducibility-detail", "trust-source"].includes(section.id)) ||
    (activeTab === "next" && ["limitations-future", "shared-references", "research-directions", "gap-signals"].includes(section.id)) ||
    (activeTab === "evidence" && section.id === "consensus")
  ));
  const renderEvidence = (paper: ComparisonRow, entries: ProfileEvidence[], empty = "") => entries.length ? entries.map((item, index) => <button type="button" key={`${paper.paper_id}-${index}-${item.quote.slice(0, 15)}`} className="comparison-profile-evidence" onClick={() => openEvidence(paper.paper_id, item.quote, item.page, item.section)}><b>{label(paper.paper_id)}{item.page ? ` · ${t("cmpPageShort", { page: item.page })}` : ""}</b><span dir="auto">{item.quote}</span></button>) : empty ? <p className="comparison-insight-note">{empty}</p> : null;
  const sectionActions = (key: string, copyText: string, evidence?: { paperId: string; quote: string; page?: number | null; section?: string }) => <div className="comparison-section-actions"><button type="button" onClick={() => { void navigator.clipboard.writeText(copyText).then(() => setFeedbackMessage("cmpSectionCopied")).catch(() => setFeedbackMessage("cmpClipboardUnavailable")); }}>{t("cmpCopy")}</button><button type="button" disabled={!evidence} onClick={() => evidence && openEvidence(evidence.paperId, evidence.quote, evidence.page, evidence.section)}>{t("cmpViewEvidence")}</button><button type="button" disabled={!response.insight_run_id} aria-label={t("cmpMarkUseful", { section: sectionName(key) })} onClick={() => { if (response.insight_run_id) void fetch(`${apiBaseUrl}/comparison/pdfs/insights/${response.insight_run_id}/feedback`, { method: "POST", headers: { ...comparisonHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ section_key: key, value: "useful" }) }).then((saved) => { if (!saved.ok) throw new Error("save failed"); setFeedbackMessage("cmpFeedbackSaved"); }).catch(() => setFeedbackMessage("cmpFeedbackFailed")); }}>👍</button><button type="button" disabled={!response.insight_run_id} aria-label={t("cmpMarkNotUseful", { section: sectionName(key) })} onClick={() => { if (response.insight_run_id) void fetch(`${apiBaseUrl}/comparison/pdfs/insights/${response.insight_run_id}/feedback`, { method: "POST", headers: { ...comparisonHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ section_key: key, value: "not_useful" }) }).then((saved) => { if (!saved.ok) throw new Error("save failed"); setFeedbackMessage("cmpFeedbackSaved"); }).catch(() => setFeedbackMessage("cmpFeedbackFailed")); }}>👎</button><small role="status">{feedbackMessage}</small></div>;
  const sharedReferences = new Map<string, { text: string; papers: string[]; doi?: string | null }>();
  profiles.forEach((profile) => profile.parsed_references.forEach((reference) => {
    const key = (reference.doi || reference.text).toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 120);
    const current = sharedReferences.get(key) || { text: reference.text, papers: [], doi: reference.doi };
    if (!current.papers.includes(profile.paper_id)) current.papers.push(profile.paper_id);
    sharedReferences.set(key, current);
  }));
  const sharedReferenceList = [...sharedReferences.values()].filter((reference) => reference.papers.length > 1).sort((a, b) => b.papers.length - a.papers.length);
  const datasetEvidence = profiles.flatMap((profile) => profile.datasets_detail.flatMap((dataset) => dataset.quote ? [{ paperId: profile.paper_id, quote: dataset.quote, page: dataset.page, section: "Dataset" }] : []))[0];
  const actionableEvidence = rows.flatMap((paper) => Object.entries(paper.evidence || {}).map(([field, quote]) => ({ paper, field, quote })).filter((item) => item.quote));
  const submitConsensus = (event: FormEvent) => {
    event.preventDefault();
    const matchText = suggestions.find((item) => t(item.key) === question)?.english || question;
    const terms = matchText.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((term) => term.length > 3);
    const result = rows.map((paper) => {
      const candidates = actionableEvidence.filter((item) => item.paper.paper_id === paper.paper_id);
      const matched = candidates.map((item) => ({ ...item, score: terms.filter((term) => `${item.field} ${item.quote}`.toLowerCase().includes(term)).length })).sort((a, b) => b.score - a.score)[0];
      if (!matched?.score) return { paper, stance: "Not addressed", quote: "" };
      const text = matched.quote.toLowerCase();
      const opposes = /did not|does not|failed to|no significant|worse than|increased error|not improve|not reduce/.test(text);
      const supports = /improv|reduc|outperform|higher|lower error|increase accuracy|significant/.test(text);
      return { paper, stance: supports && opposes ? "Mixed" : opposes ? "Opposing signal" : supports ? "Supporting signal" : "Evidence found", quote: matched.quote };
    });
    setConsensus(result);
    void fetch(`${apiBaseUrl}/comparison/pdfs/${comparisonId}/insights/consensus_questions`, { method: "POST", headers: { ...comparisonHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ question, result: result.map((item) => ({ paper_id: item.paper.paper_id, stance: item.stance, quote: item.quote })) }) }).then((saved) => { if (!saved.ok) throw new Error("save failed"); setInteractionMessage("cmpQuestionSaved"); }).catch(() => setInteractionMessage("cmpQuestionNotSaved"));
  };
  const submitClaim = (event: FormEvent) => {
    event.preventDefault();
    const terms = claim.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((term) => term.length > 3);
    const result = actionableEvidence.map((item) => ({ paper: item.paper, quote: item.quote, score: terms.filter((term) => item.quote.toLowerCase().includes(term)).length })).filter((item) => item.score > 0).sort((a, b) => b.score - a.score).slice(0, 8);
    setClaimResult(result);
    void fetch(`${apiBaseUrl}/comparison/pdfs/${comparisonId}/insights/claim_checks`, { method: "POST", headers: { ...comparisonHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ claim, result: result.map((item) => ({ paper_id: item.paper.paper_id, quote: item.quote })) }) }).then((saved) => { if (!saved.ok) throw new Error("save failed"); setInteractionMessage("cmpClaimSaved"); }).catch(() => setInteractionMessage("cmpClaimNotSaved"));
  };

  return <>
    {activeTab === "methods" && sections.some((item) => item.id === "study-design") ? <section id="study-design" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpStudyDesign")}</p><h3>{t("cmpWhatEachReports")}</h3>{sectionActions("study_design", response.narrative_summary, profiles[0]?.research_questions[0] ? { paperId: profiles[0].paper_id, ...profiles[0].research_questions[0] } : undefined)}<div className="comparison-profile-grid">{profiles.map((profile) => { const paper = rows.find((row) => row.paper_id === profile.paper_id); if (!paper) return null; return <article key={profile.paper_id}><h4><b>{label(profile.paper_id)}</b>{paper.title}</h4><dl><dt>{t("cmpResearchQuestion")}</dt><dd>{renderEvidence(paper, profile.research_questions.slice(0, 2), t("cmpNotInFullText"))}</dd><dt>{t("cmpMotivation")}</dt><dd>{renderEvidence(paper, [...profile.motivation.slice(0, 1), ...profile.contributions.slice(0, 2)], t("cmpNotInFullText"))}</dd><dt>{t("cmpBaselines")}</dt><dd>{renderEvidence(paper, [...profile.baselines.slice(0, 2), ...profile.experiments.slice(0, 3)], t("cmpNotInFullText"))}</dd><dt>{t("cmpAblation")}</dt><dd>{renderEvidence(paper, profile.ablation.slice(0, 1), t("cmpNotStatedText"))}</dd></dl></article>; })}</div></section> : null}
    {sections.some((item) => item.id === "datasets") ? <section id="datasets" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpDatasetIntel")}</p><h3>{t("cmpDatasetsFound")}</h3>{sectionActions("datasets", profiles.flatMap((profile) => profile.datasets_detail.map((dataset) => `${dataset.name}: ${dataset.quote || ""}`)).join("\n"), datasetEvidence)}<div className="comparison-profile-table-wrap"><table className="comparison-profile-table"><thead><tr><th>{t("cmpColDataset")}</th><th>{t("cmpPaper")}</th><th>{t("cmpEvidence")}</th><th>{t("cmpAccessDetails")}</th></tr></thead><tbody>{profiles.flatMap((profile) => profile.datasets_detail.map((dataset, index) => <tr key={`${profile.paper_id}-${index}`}><td>{dataset.name}</td><td>{label(profile.paper_id)}</td><td>{dataset.quote ? <button type="button" onClick={() => openEvidence(profile.paper_id, dataset.quote || "", dataset.page, "Dataset")}>{dataset.page ? t("cmpPdfPage", { page: dataset.page }) : t("cmpOpenPassage")}</button> : t("cmpNoSupporting")}</td><td>{[dataset.task, dataset.size, dataset.access, dataset.license].filter(Boolean).join(" · ") || t("cmpNotStatedText")}</td></tr>))}</tbody></table></div><p className="comparison-insight-note">{t("cmpDatasetNote")}</p></section> : null}
    {sections.some((item) => item.id === "reproducibility-detail") ? <section id="reproducibility-detail" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpReproChecklist")}</p><h3>{t("cmpReportedSignals")}</h3><div className="comparison-profile-table-wrap"><table className="comparison-profile-table"><thead><tr><th>{t("cmpPaper")}</th><th>{t("cmpCode")}</th><th>{t("cmpData")}</th><th>{t("cmpHyper")}</th><th>{t("cmpExpDetails")}</th><th>{t("cmpPretrained")}</th><th>{t("cmpLicense")}</th></tr></thead><tbody>{profiles.map((profile) => { const paper = rows.find((item) => item.paper_id === profile.paper_id); if (!paper) return null; const keys = ["code", "dataset", "hyperparameters", "experimental_details", "pretrained_model", "license"]; const reported = keys.filter((key) => profile.reproducibility[key]?.status === "reported").length; return <tr key={profile.paper_id}><th>{label(profile.paper_id)} · {paper.title}<small>{t("cmpReportedCount", { count: reported })}</small></th>{keys.map((key) => { const evidence = profile.reproducibility[key]; return <td key={key}>{evidence?.status === "reported" ? <button type="button" className="comparison-check-reported" onClick={() => openEvidence(profile.paper_id, evidence.quote || "", evidence.page, key)}>✓ {t("cmpReported")}{evidence.page ? ` · ${t("cmpPageShort", { page: evidence.page })}` : ""}</button> : <span>{t("cmpNotStated")}</span>}</td>; })}</tr>; })}</tbody></table></div><p className="comparison-insight-note">{t("cmpNotStatedNote")}</p></section> : null}
    {sections.some((item) => item.id === "limitations-future") ? <section id="limitations-future" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpLimitsFuture")}</p><h3>{t("cmpCaveats")}</h3><div className="comparison-profile-grid">{rows.map((paper) => { const profile = profiles.find((item) => item.paper_id === paper.paper_id); const limitation = paper.evidence?.limitation ? [{ quote: paper.evidence.limitation, section: "Limitations" }] : []; const future = profile?.future_work || []; if (!limitation.length && !future.length) return null; return <article key={paper.paper_id}><h4><b>{label(paper.paper_id)}</b>{paper.title}</h4><dl><dt>{t("cmpLimitations")}</dt><dd>{renderEvidence(paper, limitation, t("cmpNotInText"))}</dd><dt>{t("cmpFutureWork")}</dt><dd>{renderEvidence(paper, future.slice(0, 3), t("cmpNotInText"))}</dd></dl></article>; })}</div></section> : null}
    {sections.some((item) => item.id === "tables-figures") ? <section id="tables-figures" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpTablesFigures")}</p><h3>{t("cmpTablesDetected")}</h3><div className="comparison-profile-grid">{profiles.map((profile) => { const paper = rows.find((row) => row.paper_id === profile.paper_id); if (!paper || (!profile.key_tables.length && !profile.key_figures.length)) return null; return <article key={profile.paper_id}><h4><b>{label(profile.paper_id)}</b>{paper.title}</h4>{profile.key_tables.map((item, index) => <div className="comparison-extracted-table" key={`${index}-${item.caption}`}><p>{item.page ? `${t("cmpPdfPage", { page: item.page })} · ` : ""}<span dir="auto">{item.caption}</span></p>{item.headers?.length && item.rows?.length ? <div className="comparison-profile-table-wrap"><table className="comparison-profile-table"><thead><tr>{item.headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{item.rows.map((cells, rowIndex) => <tr key={rowIndex}>{cells.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody></table></div> : <small>{t("cmpCaptionOnly")}</small>}</div>)}{profile.key_figures.map((item, index) => <p className="comparison-profile-caption" key={`fig-${index}`}>{item.page ? `${t("cmpPdfPage", { page: item.page })} · ` : ""}<span dir="auto">{item.caption}</span></p>)}</article>; })}</div></section> : null}
    {sections.some((item) => item.id === "shared-references") && sharedReferenceList.length ? <section id="shared-references" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpReadNext")}</p><h3>{t("cmpSharedRefs")}</h3>{sharedReferenceList.slice(0, 20).map((reference, index) => <div className="comparison-reference-row" key={`${index}-${reference.text}`}><span dir="auto">{reference.text}</span><small>{t("cmpCitedIn", { papers: reference.papers.map(label).join(", "), count: reference.papers.length })}</small>{reference.doi ? <a href={`https://doi.org/${reference.doi}`} target="_blank" rel="noreferrer">{t("cmpResolveDoi")}</a> : null}</div>)}</section> : null}
    {sections.some((item) => item.id === "trust-source") ? <section id="trust-source" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpTrustSource")}</p><h3>{t("cmpSourceTransparency")}</h3><p>{t("cmpTransparencyNote")}</p><div className="comparison-profile-grid">{profiles.map((profile) => { const paper = rows.find((row) => row.paper_id === profile.paper_id); if (!paper || (!profile.doi && !profile.publication_year && !profile.preprint_notice)) return null; return <article key={profile.paper_id}><h4><b>{label(profile.paper_id)}</b>{paper.title}</h4><ul className="comparison-source-facts">{profile.publication_year ? <li>{t("cmpYearFirstPage", { year: profile.publication_year })}</li> : null}{profile.preprint_notice ? <li>{t("cmpPreprintSignal", { notice: profile.preprint_notice })}</li> : null}<li>{t("cmpDoiLabel")} {profile.doi ? <a href={`https://doi.org/${profile.doi}`} target="_blank" rel="noreferrer">{t("cmpDoiUnchecked", { doi: profile.doi })}</a> : t("cmpDoiMissing")}</li><li>{t("cmpFullTextUploaded")}</li><li>{t("cmpPeerReview")}</li></ul></article>; })}</div></section> : null}
    {sections.some((item) => item.id === "evolution") ? <section id="evolution" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpEvolution")}</p><h3>{t("cmpYearsStated")}</h3><div className="comparison-timeline">{profiles.filter((item) => item.publication_year).sort((a, b) => (a.publication_year || 0) - (b.publication_year || 0)).map((profile) => { const paper = rows.find((row) => row.paper_id === profile.paper_id); return paper ? <article key={profile.paper_id}><strong>{profile.publication_year}</strong><span><b>{label(profile.paper_id)}</b>{paper.title}</span><small>{paper.methods.join(" · ") || t("cmpMethodNotDetected")}</small></article> : null; })}</div></section> : null}
    {sections.some((item) => item.id === "relationships") ? <section id="relationships" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpRelationships")}</p><h3>{t("cmpSharedMethodsData")}</h3><div className="comparison-profile-grid">{rows.map((paper) => { const linked = rows.filter((other) => other.paper_id !== paper.paper_id && ([...paper.methods, ...paper.datasets].some((term) => [...other.methods, ...other.datasets].some((otherTerm) => term.toLowerCase() === otherTerm.toLowerCase())))); if (!paper.methods.length && !paper.datasets.length) return null; return <article key={paper.paper_id}><h4><b>{label(paper.paper_id)}</b>{paper.title}</h4><p>{[...paper.methods.map((item) => t("cmpMethodItem", { name: item })), ...paper.datasets.map((item) => t("cmpDatasetItem", { name: item }))].join(" · ") || t("cmpNoSharedTerms")}</p><small>{linked.length ? t("cmpSharesWith", { papers: linked.map((item) => label(item.paper_id)).join(", ") }) : t("cmpNoSharedMethod")}</small></article>; })}</div></section> : null}
    {sections.some((item) => item.id === "research-directions") ? <section id="research-directions" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpDirections")}</p><h3>{t("cmpNextByAuthors")}</h3><p>{t("cmpExcerptsNote")}</p><div className="comparison-profile-grid">{profiles.map((profile) => { const paper = rows.find((item) => item.paper_id === profile.paper_id); if (!paper) return null; const entries = [...profile.future_work, ...profile.motivation].slice(0, 3); return entries.length ? <article key={profile.paper_id}><h4><b>{label(profile.paper_id)}</b>{paper.title}</h4>{renderEvidence(paper, entries)}</article> : null; })}</div></section> : null}
    <section id="gap-signals" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpOpportunity")}</p><h3>{t("cmpCoverageGaps")}</h3><p>{t("cmpGapNote")}</p><ul className="comparison-gap-list">{["Shared dataset", "Explicit sample size", "Ablation evidence", "Future-work direction"].map((criterion) => { const counts = criterion === "Shared dataset" ? profiles.filter((item) => item.datasets_detail.length).length : criterion === "Ablation evidence" ? profiles.filter((item) => item.ablation.length).length : criterion === "Future-work direction" ? profiles.filter((item) => item.future_work.length).length : profiles.filter((item) => item.experiments.some((exp) => /\b\d[\d,]*\s+(?:participants|samples|subjects|records)\b/i.test(exp.quote))).length; return <li key={criterion}><strong>{t(({ "Shared dataset": "cmpGapSharedDataset", "Explicit sample size": "cmpGapSampleSize", "Ablation evidence": "cmpGapAblation", "Future-work direction": "cmpGapFuture" } as Record<string, SearchCopyKey>)[criterion])}</strong><span>{t("cmpGapCount", { count: counts, total: rows.length })}</span><small>{t("cmpLimitedEvidence")}</small></li>; })}</ul></section>
    {activeTab === "evidence" ? <section id="consensus" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpConsensus")}</p><h3>{t("cmpAskAcross")}</h3><div className="comparison-question-suggestions">{suggestions.map((suggestion) => <button type="button" key={suggestion.key} onClick={() => setQuestion(t(suggestion.key))}>{t(suggestion.key)}</button>)}</div><form className="comparison-analysis-form" onSubmit={submitConsensus}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={t("cmpAskResearch")} aria-label={t("cmpResearchQuestion")} required /><button type="submit">{t("cmpFindEvidence")}</button></form>{consensus.length ? <><div className="comparison-consensus-counts">{["Supporting signal", "Opposing signal", "Mixed", "Evidence found", "Not addressed"].map((stance) => <span key={stance}><b>{consensus.filter((item) => item.stance === stance).length}</b>{copy.label(stance)}</span>)}</div><div className="comparison-profile-grid">{consensus.map(({ paper, stance, quote }) => <article key={paper.paper_id}><h4><b>{label(paper.paper_id)}</b>{copy.label(stance)} · <bdi>{paper.title}</bdi></h4>{quote ? <button type="button" className="comparison-profile-evidence" dir="auto" onClick={() => openEvidence(paper.paper_id, quote, undefined, "Matched table evidence")}>{quote}</button> : <p className="comparison-insight-note">{t("cmpNoPassageFields")}</p>}</article>)}</div></> : null}<p className="comparison-insight-note">{t("cmpKeywordNote")}</p>{interactionMessage ? <small className="comparison-interaction-message" role="status">{interactionMessage}</small> : null}</section> : null}
    <section id="claim-check" className="comparison-insight-card comparison-profile-section"><p className="resora-label">{t("cmpClaimCheck")}</p><h3>{t("cmpCheckStatement")}</h3><form className="comparison-analysis-form" onSubmit={submitClaim}><input value={claim} onChange={(event) => setClaim(event.target.value)} placeholder={t("cmpClaimPlaceholder")} aria-label={t("cmpClaimLabel")} required /><button type="submit">{t("cmpFindPassages")}</button></form>{claimResult ? claimResult.length ? <div className="comparison-profile-grid">{claimResult.map((item, index) => <article key={`${item.paper.paper_id}-${index}`}><h4><b>{label(item.paper.paper_id)}</b>{item.paper.title}</h4><button type="button" className="comparison-profile-evidence" dir="auto" onClick={() => openEvidence(item.paper.paper_id, item.quote, undefined, "Matched table evidence")}>{item.quote}</button></article>)}</div> : <p>{t("cmpNoRelated")}</p> : null}<p className="comparison-insight-note">{t("cmpClaimNote")}</p>{interactionMessage ? <small className="comparison-interaction-message" role="status">{interactionMessage}</small> : null}</section>
  </>;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="comparison-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InsightPanel({ title, items, tone = "default" }: { title: string; items: string[]; tone?: "default" | "danger" | "green" }) {
  return (
    <section className={`comparison-insight comparison-insight-${tone}`}>
      <p className="resora-label">{title}</p>
      <div>
        {items.length ? items.map((item) => <span key={item}>{item}</span>) : <span>Run comparison to populate this panel.</span>}
      </div>
    </section>
  );
}

function Heatmap({ title, labels, matrix }: { title: string; labels: string[]; matrix: number[][] }) {
  return (
    <section className="comparison-insight">
      <p className="resora-label">{title}</p>
      <div className="comparison-heatmap" style={{ gridTemplateColumns: `repeat(${Math.max(matrix.length, 1)}, minmax(34px, 1fr))` }}>
        {matrix.flatMap((row, rowIndex) =>
          row.map((value, columnIndex) => (
            <span
              key={`${rowIndex}-${columnIndex}`}
              title={`${labels[rowIndex]} vs ${labels[columnIndex]}: ${value}`}
              style={{ opacity: Math.max(0.22, value) }}
            >
              {Math.round(value * 100)}
            </span>
          )),
        )}
      </div>
    </section>
  );
}

function Score({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <span>{label}</span>
      <strong>{pct}%</strong>
      <em><i style={{ width: `${pct}%` }} /></em>
    </div>
  );
}
