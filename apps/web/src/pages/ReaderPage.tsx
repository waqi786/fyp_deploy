/**
 * Reader — one place to read a paper: PDF viewer or clean text on the left; Summary · Chat · Figures ·
 * Translate · Info on the right; "Listen" everywhere. Opens from Search (Summarize / Read paper), from an
 * uploaded PDF, or from a DOI / arXiv / PDF link. Every word follows the one app language (Master Prompt Part 7, 12).
 */
import { type ChangeEvent, type DragEvent, type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { getResearchLanguage, researchLanguages } from "../i18n/languages";
import { hasSearchCatalog, type SearchCopyKey, useSearchCopy } from "./search/copy";
import { CreditLimitError, type UsageLimit } from "./search/researchApi";
import { PdfViewer, type PdfViewerHandle } from "./reader/PdfViewer";
import {
  forgetRecent,
  type Level,
  type PaperHandoff,
  readerApi,
  ReaderError,
  type ReaderAnswer,
  type ReaderDocument,
  type ReaderSummary,
  type RecentDocument,
  type TranslatedPage,
  readHandoff,
  readRecent,
  rememberRecent,
} from "./reader/readerApi";
import { useSpeech } from "./reader/useSpeech";
import { CompareTrayBar } from "./compare/CompareTrayBar";
import { toggleTray, useTray } from "./compare/compareTray";
import { libraryApi, type PaperInput } from "./library/libraryApi";
import "./SearchPage.css";
import "./ReaderPage.css";

type T = ReturnType<typeof useSearchCopy>;
type PanelTab = "summary" | "chat" | "figures" | "translate" | "info";
type MobilePane = "paper" | PanelTab;
type ChatMessage = { id: number; role: "user" | "assistant"; text: string; answer?: ReaderAnswer; failed?: boolean };

const MAX_MB = 40;
// Default credit costs (Master Prompt Part 9); the server is the source of truth and charges 0 for cached results.
const SUMMARY_CREDITS = Number(import.meta.env.VITE_CREDITS_SUMMARY || 2);
const CHAT_CREDITS = Number(import.meta.env.VITE_CREDITS_CHAT || 1);
const PANEL_TABS: PanelTab[] = ["summary", "chat", "figures", "translate", "info"];
const LEVELS: Level[] = ["expert", "student", "simple"];
const SECTION_LABELS: Record<string, SearchCopyKey> = {
  problem: "readerSectionProblem",
  research_questions: "readerSectionResearchQuestions",
  motivation: "readerSectionMotivation",
  contributions: "readerSectionContributions",
  method: "readerSectionMethod",
  data: "readerSectionData",
  baselines: "readerSectionBaselines",
  experiments: "readerSectionExperiments",
  metrics: "readerSectionMetrics",
  results: "readerSectionResults",
  strongest_experiment: "readerSectionStrongest",
  limitations: "readerSectionLimitations",
  future_work: "readerSectionFuture",
  availability: "readerSectionAvailability",
};
const SUGGESTIONS: SearchCopyKey[] = [
  "readerSuggestProblem", "readerSuggestContribution", "readerSuggestMethod", "readerSuggestData",
  "readerSuggestResults", "readerSuggestLimitations", "readerSuggestImprove",
];
const ERROR_KEYS: Record<string, SearchCopyKey> = {
  not_pdf: "readerErrorNotPdf",
  too_large: "readerErrorTooLarge",
  unreadable: "readerErrorUnreadable",
  no_full_text: "readerErrorNoFullText",
  not_found: "readerErrorNotFound",
};

const languages = researchLanguages.filter((item) => hasSearchCatalog(item.code));

function directionOf(code: string) {
  return getResearchLanguage(code)?.direction === "rtl" ? "rtl" : "ltr";
}

function nativeName(code: string) {
  return getResearchLanguage(code)?.nativeName || code;
}

/** Best guess of a text's language for the speech voice (papers are usually English). */
function guessLanguage(text: string) {
  const sample = text.slice(0, 600);
  if (/[؀-ۿ]/.test(sample)) return /[ٹڈڑںےۓ]/.test(sample) ? "ur" : "ar";
  if (/[一-鿿]/.test(sample)) return "zh-CN";
  if (/[぀-ヿ]/.test(sample)) return "ja";
  if (/[가-힯]/.test(sample)) return "ko";
  if (/[Ѐ-ӿ]/.test(sample)) return "ru";
  if (/[ऀ-ॿ]/.test(sample)) return "hi";
  return "en";
}

function formatWhen(iso: string, language: string, withDate: boolean) {
  try {
    return new Intl.DateTimeFormat(language, withDate ? { dateStyle: "medium" } : { timeStyle: "short" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function limitText(limit: UsageLimit, language: string, t: T) {
  if (limit.scope === "session") return t("limitReachedSession", { time: formatWhen(limit.resets_at, language, false) });
  return t(limit.scope === "week" ? "limitReachedWeek" : "limitReachedMonth", { date: formatWhen(limit.resets_at, language, true) });
}

function errorText(error: unknown, t: T, language: string) {
  if (error instanceof CreditLimitError) return limitText(error.limit, language, t);
  if (error instanceof ReaderError && ERROR_KEYS[error.code]) return t(ERROR_KEYS[error.code], { size: MAX_MB });
  // Development builds show the technical reason so problems can be fixed; production users never see it.
  if (import.meta.env.DEV && error instanceof ReaderError) {
    return `${t("readerErrorGeneric")} [dev: ${error.status ? `HTTP ${error.status}` : "network/CORS — request blocked"} · ${error.code}]`;
  }
  return t("readerErrorGeneric");
}

function apa(document: ReaderDocument) {
  const authors = document.authors.length > 6 ? `${document.authors.slice(0, 6).join(", ")}, et al.` : document.authors.join(", ");
  return [authors, document.year ? `(${document.year}).` : "", `${document.title}.`, document.venue ? `${document.venue}.` : "", document.doi ? `https://doi.org/${document.doi}` : ""]
    .filter(Boolean)
    .join(" ");
}

function useIsNarrow() {
  const query = "(max-width: 960px)";
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setNarrow(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return narrow;
}

/* ========================================================================== */

export function ReaderPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { docId } = useParams();
  const t = useSearchCopy(interfaceLanguage);
  return (
    <section className="rs-search rd-reader" dir={directionOf(interfaceLanguage)} lang={interfaceLanguage} data-no-translate="">
      {docId ? <ReaderWorkspace key={docId} docId={docId} language={interfaceLanguage} t={t} /> : <ReaderHome language={interfaceLanguage} t={t} />}
    </section>
  );
}

/* ========================================================================== */
/*  Home: upload, link, recent                                                */
/* ========================================================================== */

function ReaderHome({ language, t }: { language: string; t: T }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [busy, setBusy] = useState<"opening" | "uploading" | null>(null);
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const [dragging, setDragging] = useState(false);
  const [recent, setRecent] = useState<RecentDocument[]>(() => readRecent());
  const fileRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const finish = useCallback((document: ReaderDocument, tab: string, auto: boolean) => {
    rememberRecent(document);
    const query = new URLSearchParams({ tab });
    if (auto) query.set("auto", "1");
    navigate(`/reader/${document.id}?${query.toString()}`, { replace: true });
  }, [navigate]);

  const open = useCallback(async (payload: { paper?: PaperHandoff; link?: string }, tab = "summary", auto = false) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy("opening");
    setError("");
    try {
      finish(await readerApi.open(payload, controller.signal), tab, auto);
    } catch (caught) {
      if ((caught as Error)?.name === "AbortError") return;
      setError(errorText(caught, t, language));
      setBusy(null);
    }
  }, [finish, language, t]);

  // Arrivals from Search ("Summarize" / "Read paper") and old /summaries links.
  useEffect(() => {
    const key = params.get("paper");
    const tab = params.get("tab") || "summary";
    if (key) {
      const paper = readHandoff(key);
      if (paper) void open({ paper }, tab, params.get("auto") === "1");
      return;
    }
    const title = params.get("title");
    if (title) {
      void open({
        paper: { title, abstract: params.get("content") || null, authors: [], pdf_url: params.get("pdf_url") || null, url: params.get("url") || null },
      }, "summary", params.get("auto_read") !== "1");
    }
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function upload(file: File | undefined) {
    if (!file) return;
    if (file.type && file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError(t("readerErrorNotPdf"));
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(t("readerErrorTooLarge", { size: MAX_MB }));
      return;
    }
    setBusy("uploading");
    setError("");
    try {
      finish(await readerApi.upload(file), "summary", false);
    } catch (caught) {
      setError(errorText(caught, t, language));
      setBusy(null);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void upload(event.dataTransfer.files?.[0]);
  }

  function onSubmitLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (link.trim()) void open({ link: link.trim() });
  }

  return (
    <div className="rd-home">
      <div className="rd-home-glow" aria-hidden="true" />
      <h1 className="rd-home-title">{t("readerTitle")}</h1>
      <p className="rd-home-subtitle">{t("readerSubtitle")}</p>

      <div
        className={`rd-drop${dragging ? " is-dragging" : ""}${busy ? " is-busy" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {busy ? (
          <div className="rd-drop-busy" role="status">
            <span className="rd-spinner" aria-hidden="true" />
            {busy === "uploading" ? t("readerUploading") : t("readerOpening")}
          </div>
        ) : (
          <>
            <span className="rd-drop-icon" aria-hidden="true"><FileGlyph /></span>
            <p className="rd-drop-title">{t("readerDrop")}</p>
            <button type="button" className="rd-button rd-button-primary" onClick={() => fileRef.current?.click()}>{t("readerChoose")}</button>
            <p className="rd-drop-note"><LockGlyph />{t("readerPrivateNote")}</p>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            void upload(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>

      <div className="rd-or" aria-hidden="true"><span>{t("readerOr")}</span></div>

      <form className="rd-link" onSubmit={onSubmitLink}>
        <LinkGlyph />
        <input value={link} onChange={(event) => setLink(event.target.value)} placeholder={t("readerLinkPlaceholder")} aria-label={t("readerLinkPlaceholder")} dir="auto" disabled={Boolean(busy)} />
        <button type="submit" className="rd-button rd-button-quiet" disabled={!link.trim() || Boolean(busy)}>{t("readerOpenLink")}</button>
      </form>

      {error ? <p className="rd-alert" role="alert">{error}</p> : null}

      {recent.length ? (
        <section className="rd-recent" aria-label={t("readerRecent")}>
          <h2>{t("readerRecent")}</h2>
          <ul>
            {recent.map((item) => (
              <li key={item.id}>
                <button type="button" className="rd-recent-row" onClick={() => navigate(`/reader/${item.id}`)}>
                  <span className="rd-recent-icon" aria-hidden="true"><FileGlyph small /></span>
                  <span className="rd-recent-text">
                    <bdi className="rd-recent-title">{item.title}</bdi>
                    <span className="rd-recent-sub">{sourceLabel(item.source, t)}</span>
                  </span>
                </button>
                <button
                  type="button"
                  className="rd-icon-button"
                  aria-label={t("readerRemoveRecent")}
                  title={t("readerRemoveRecent")}
                  onClick={() => {
                    forgetRecent(item.id);
                    setRecent(readRecent());
                  }}
                >
                  <CloseGlyph />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function sourceLabel(source: ReaderDocument["source"], t: T) {
  return source === "upload" ? t("readerSourceUpload") : source === "open_access" ? t("readerSourceOpen") : t("readerSourceAbstract");
}

/* ========================================================================== */
/*  Workspace: viewer + panel                                                 */
/* ========================================================================== */

function ReaderWorkspace({ docId, language, t }: { docId: string; language: string; t: T }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const narrow = useIsNarrow();
  const speech = useSpeech();
  const trayItems = useTray();
  const viewerRef = useRef<PdfViewerHandle | null>(null);
  const textRef = useRef<HTMLDivElement | null>(null);

  const [document, setDocument] = useState<ReaderDocument | null>(null);
  const [loadError, setLoadError] = useState<string>("");
  const [libraryId, setLibraryId] = useState<string | null>(null);
  const [savingToLibrary, setSavingToLibrary] = useState(false);
  const [pages, setPages] = useState<string[]>([]);
  const [view, setView] = useState<"pdf" | "text">("pdf");
  const [pdfFailed, setPdfFailed] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [darkPages, setDarkPages] = useState(() => {
    try {
      return window.localStorage.getItem("resora-reader-dark-pages") === "1";
    } catch {
      return false;
    }
  });
  const [currentPage, setCurrentPage] = useState(1);
  const [find, setFind] = useState("");
  const [findIndex, setFindIndex] = useState(0);
  const [notice, setNotice] = useState("");
  const [toast, setToast] = useState("");
  const [selection, setSelection] = useState<{ text: string; x: number; y: number } | null>(null);
  const credits = { summary: SUMMARY_CREDITS, chat: CHAT_CREDITS };

  const tabParam = params.get("tab") as PanelTab | null;
  const tab: PanelTab = tabParam && PANEL_TABS.includes(tabParam) ? tabParam : "summary";
  const [mobilePane, setMobilePane] = useState<MobilePane>(tabParam && PANEL_TABS.includes(tabParam) ? tabParam : "paper");

  const setTab = useCallback((next: PanelTab) => {
    setParams((current) => {
      const copy = new URLSearchParams(current);
      copy.set("tab", next);
      copy.delete("auto");
      return copy;
    }, { replace: true });
    setMobilePane(next);
  }, [setParams]);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  }, []);

  // Load the document and its page texts.
  const libraryPaper = useCallback((doc: ReaderDocument): PaperInput => ({
    title: doc.title, authors: doc.authors, year: doc.year ?? null, venue: doc.venue ?? null, doi: doc.doi ?? null, url: doc.url ?? null,
    abstract: doc.abstract ?? null, reader_doc_id: doc.has_pdf ? doc.id : null,
  }), []);

  // Show "In Library" when this paper is already saved (silent on failure).
  useEffect(() => {
    if (!document) return;
    let cancelled = false;
    libraryApi.lookup([libraryPaper(document)]).then(({ item_ids }) => { if (!cancelled) setLibraryId(item_ids[0] || null); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [document, libraryPaper]);

  useEffect(() => {
    const controller = new AbortController();
    readerApi.get(docId, controller.signal)
      .then((loaded) => {
        setDocument(loaded);
        rememberRecent(loaded);
        setView(loaded.has_pdf && !window.matchMedia("(max-width: 960px)").matches ? "pdf" : "text");
        globalThis.document.title = `${loaded.title} · Resora`;
      })
      .catch((caught) => {
        if ((caught as Error)?.name === "AbortError") return;
        if (caught instanceof ReaderError && caught.code === "not_found") forgetRecent(docId); // stale link: drop it from the list
        setLoadError(errorText(caught, t, language));
      });
    readerApi.pages(docId, controller.signal).then((items) => setPages(items.map((item) => item.text))).catch(() => undefined);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  useEffect(() => {
    try {
      window.localStorage.setItem("resora-reader-dark-pages", darkPages ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [darkPages]);

  useEffect(() => () => speech.stop(), [speech.stop]); // eslint-disable-line react-hooks/exhaustive-deps

  const goToPage = useCallback((page: number) => {
    if (!document) return;
    const target = Math.min(Math.max(1, page), Math.max(1, document.page_count));
    if (narrow) setMobilePane("paper");
    window.setTimeout(() => {
      if (view === "pdf" && !pdfFailed && document.has_pdf) viewerRef.current?.scrollToPage(target);
      else textRef.current?.querySelector<HTMLElement>(`[data-page="${target}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setCurrentPage(target);
    }, narrow ? 60 : 0);
  }, [document, narrow, pdfFailed, view]);

  // Find in paper: pages that contain the words.
  const matches = useMemo(() => {
    const needle = find.trim().toLocaleLowerCase();
    if (needle.length < 2) return [];
    return pages.flatMap((text, index) => (text.toLocaleLowerCase().includes(needle) ? [index + 1] : []));
  }, [find, pages]);

  useEffect(() => setFindIndex(0), [find]);

  function nextMatch() {
    if (!matches.length) return;
    const index = (findIndex + 1) % matches.length;
    setFindIndex(index);
    goToPage(matches[index]);
  }

  function onTextMouseUp() {
    const selected = window.getSelection();
    const text = selected?.toString().trim() || "";
    if (text.length < 12 || text.length > 900 || !selected?.rangeCount) {
      setSelection(null);
      return;
    }
    const rect = selected.getRangeAt(0).getBoundingClientRect();
    setSelection({ text, x: rect.left + rect.width / 2, y: rect.top });
  }

  const listenPaper = useCallback(() => {
    const texts = pages.slice(currentPage - 1).filter((text) => text.trim());
    if (!texts.length) return;
    if (!speech.speak("paper", texts, guessLanguage(texts[0]))) setNotice(t("readerNoVoice"));
  }, [currentPage, pages, speech, t]);

  // Chat state lives here so Figures / selection can send questions to it.
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const chatCounter = useRef(0);

  const ask = useCallback(async (question: string) => {
    const text = question.trim();
    if (!text || chatBusy || !document) return;
    setTab("chat");
    const id = ++chatCounter.current;
    setChat((items) => [...items, { id, role: "user", text }]);
    setChatBusy(true);
    try {
      const answer = await readerApi.ask(document.id, text, language);
      setChat((items) => [...items, { id: ++chatCounter.current, role: "assistant", text: answer.answer, answer }]);
    } catch (caught) {
      setChat((items) => [...items, { id: ++chatCounter.current, role: "assistant", text: caught instanceof CreditLimitError ? limitText(caught.limit, language, t) : t("readerAskFailed"), failed: true }]);
    } finally {
      setChatBusy(false);
    }
  }, [chatBusy, document, language, setTab, t]);

  if (loadError) {
    return (
      <div className="rd-state">
        <h1>{loadError}</h1>
        <button type="button" className="rd-button rd-button-primary" onClick={() => navigate("/reader")}>{t("readerUploadPdf")}</button>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="rd-loading" role="status" aria-label={t("readerOpening")}>
        <div className="rd-skel rd-skel-title" />
        <div className="rd-skel rd-skel-line" />
        <div className="rd-loading-grid">
          <div className="rd-skel rd-skel-page" />
          <div className="rd-skel rd-skel-panel" />
        </div>
      </div>
    );
  }

  const compareKey = document.doi ? `doi:${document.doi.toLowerCase()}` : `reader:${document.id}`;
  const inCompare = trayItems.some((item) => item.key === compareKey);
  const usePdf = view === "pdf" && document.has_pdf && !pdfFailed;
  const meta = [document.authors.slice(0, 3).join(", ") + (document.authors.length > 3 ? " et al." : ""), document.venue, document.year].filter(Boolean).join(" · ");

  const paperPane = (
    <div className="rd-paper">
      <div className="rd-toolbar" role="toolbar" aria-label={t("readerTabPaper")}>
        {document.has_pdf ? (
          <div className="rd-seg" role="radiogroup" aria-label={t("readerViewPdf")}>
            {(["pdf", "text"] as const).map((mode) => (
              <button key={mode} type="button" role="radio" aria-checked={view === mode} className={view === mode ? "is-active" : ""} onClick={() => setView(mode)}>
                {mode === "pdf" ? t("readerViewPdf") : t("readerViewText")}
              </button>
            ))}
          </div>
        ) : null}
        <div className="rd-pager">
          <button type="button" className="rd-icon-button" aria-label={t("readerPrev")} title={t("readerPrev")} onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1}><ChevronGlyph flip /></button>
          <span className="rd-page-count">{t("readerPageOf", { page: currentPage, total: document.page_count })}</span>
          <button type="button" className="rd-icon-button" aria-label={t("readerNext")} title={t("readerNext")} onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= document.page_count}><ChevronGlyph /></button>
        </div>
        {usePdf ? (
          <div className="rd-zoom">
            <button type="button" className="rd-icon-button" aria-label={t("readerZoomOut")} title={t("readerZoomOut")} onClick={() => setZoom((value) => Math.max(0.5, Math.round((value - 0.15) * 100) / 100))}><MinusGlyph /></button>
            <button type="button" className="rd-zoom-value" title={t("readerFitWidth")} onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
            <button type="button" className="rd-icon-button" aria-label={t("readerZoomIn")} title={t("readerZoomIn")} onClick={() => setZoom((value) => Math.min(2.5, Math.round((value + 0.15) * 100) / 100))}><PlusGlyph /></button>
          </div>
        ) : null}
        <span className="rs-spacer" />
        <form
          className="rd-find"
          onSubmit={(event) => {
            event.preventDefault();
            nextMatch();
          }}
        >
          <SearchGlyph />
          <input value={find} onChange={(event) => setFind(event.target.value)} placeholder={t("readerFind")} aria-label={t("readerFind")} dir="auto" />
          {find.trim().length >= 2 ? <span className="rd-find-count">{matches.length ? t("readerFindResults", { count: matches.length }) : t("readerNoMatches")}</span> : null}
        </form>
        {usePdf ? (
          <button type="button" className={`rd-chip-toggle${darkPages ? " is-on" : ""}`} aria-pressed={darkPages} onClick={() => setDarkPages((value) => !value)}>
            <MoonGlyph />{t("readerDarkPages")}
          </button>
        ) : null}
      </div>

      {document.source === "abstract" ? (
        <div className="rd-banner">
          <span>{t("readerAbstractNote")}</span>
          <button type="button" className="rd-button rd-button-quiet" onClick={() => navigate("/reader")}>{t("readerUploadPdf")}</button>
        </div>
      ) : null}

      {usePdf ? (
        <PdfViewer
          ref={viewerRef}
          url={readerApi.pdfUrl(document.id)}
          zoom={zoom}
          darkPages={darkPages}
          onPageChange={setCurrentPage}
          onReady={() => undefined}
          onError={() => {
            setPdfFailed(true);
            setNotice(t("readerPdfFailed"));
          }}
          pageLabel={(page) => t("readerPageOf", { page, total: document.page_count })}
        />
      ) : (
        <div className="rd-text" ref={textRef} onMouseUp={onTextMouseUp} onScroll={(event) => {
          const container = event.currentTarget;
          const sections = Array.from(container.querySelectorAll<HTMLElement>("[data-page]"));
          const top = container.scrollTop + 80;
          const current = sections.filter((section) => section.offsetTop <= top).pop();
          if (current) setCurrentPage(Number(current.dataset.page));
        }}>
          {pages.length ? pages.map((text, index) => (
            <article key={index} className="rd-text-page" data-page={index + 1}>
              <header><span>{t("readerPageOf", { page: index + 1, total: document.page_count })}</span></header>
              {text.trim() ? (
                <div dir="auto">{highlight(text, find)}</div>
              ) : (
                <p className="rd-muted">{t("readerScannedPage")}</p>
              )}
            </article>
          )) : <p className="rd-muted rd-pad">{t("readerNoText")}</p>}
        </div>
      )}
      {selection ? (
        <div className="rd-selection" style={{ left: selection.x, top: selection.y }} role="toolbar">
          <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => {
            void ask(t("readerSelectionPrompt", { text: selection.text.slice(0, 600) }));
            setSelection(null);
          }}>{t("readerSelectionExplain")}</button>
        </div>
      ) : null}
    </div>
  );

  const panel = (
    <aside className="rd-panel" aria-label={t("readerTabSummary")}>
      {!narrow ? (
        <div className="rd-tabs" role="tablist">
          {PANEL_TABS.map((item) => (
            <button key={item} type="button" role="tab" aria-selected={tab === item} className={tab === item ? "is-active" : ""} onClick={() => setTab(item)}>
              {t(panelLabel(item))}
            </button>
          ))}
        </div>
      ) : null}
      <div className="rd-panel-body">
        {tab === "summary" ? (
          <SummaryTab document={document} language={language} t={t} cost={credits.summary} autoRun={params.get("auto") === "1"} goToPage={goToPage} speech={speech} onNoVoice={() => setNotice(t("readerNoVoice"))} showToast={showToast} />
        ) : null}
        {tab === "chat" ? <ChatTab messages={chat} busy={chatBusy} onAsk={ask} t={t} cost={credits.chat} goToPage={goToPage} isAbstract={document.source === "abstract"} /> : null}
        {tab === "figures" ? <FiguresTab document={document} t={t} goToPage={goToPage} onExplain={(label) => void ask(t("readerExplainPrompt", { item: label }))} /> : null}
        {tab === "translate" ? <TranslateTab document={document} language={language} t={t} currentPage={currentPage} goToPage={goToPage} speech={speech} onNoVoice={() => setNotice(t("readerNoVoice"))} /> : null}
        {tab === "info" ? <InfoTab document={document} t={t} language={language} showToast={showToast} /> : null}
      </div>
    </aside>
  );

  return (
    <div className="rd-workspace">
      <header className="rd-head">
        <button type="button" className="rd-back" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/reader"))}>
          <ChevronGlyph flip />{t("readerBack")}
        </button>
        <div className="rd-head-main">
          <h1 className="rd-title"><bdi>{document.title}</bdi></h1>
          <div className="rd-meta">
            {meta ? <span><bdi>{meta}</bdi></span> : null}
            <span className={`rd-badge${document.source === "abstract" ? " is-warn" : document.source === "open_access" ? " is-good" : ""}`}>{sourceLabel(document.source, t)}</span>
            {document.page_count > 1 ? <span className="rd-faint">{t("readerPages", { count: document.page_count })} · {t("readerMinutes", { count: document.reading_minutes })}</span> : null}
          </div>
        </div>
        <div className="rd-head-actions">
          <ListenControl speech={speech} id="paper" label={t("readerListen")} t={t} onStart={listenPaper} disabled={!pages.some((text) => text.trim())} />
          <button
            type="button"
            className={`rd-button rd-button-quiet${inCompare ? " is-on" : ""}`}
            aria-pressed={inCompare}
            onClick={() => {
              const result = toggleTray({
                key: compareKey,
                title: document.title,
                authors: document.authors,
                year: document.year ?? null,
                venue: document.venue ?? null,
                doi: document.doi ?? null,
                url: document.url ?? null,
                abstract: document.abstract ?? null,
                is_open_access: document.is_open_access,
                citation_count: document.citation_count,
                reader_doc_id: document.has_pdf ? document.id : null,
                has_pdf: document.has_pdf,
              });
              showToast(result === "added" ? t("compareAdded") : result === "removed" ? t("compareRemoved") : t("compareTrayFull"));
            }}
          >
            <CompareGlyph />{inCompare ? t("readerInCompare") : t("readerAddCompare")}
          </button>
          <button
            type="button"
            className={`rd-button rd-button-quiet${libraryId ? " is-on" : ""}`}
            aria-pressed={Boolean(libraryId)}
            disabled={savingToLibrary}
            onClick={() => {
              if (libraryId) { navigate("/library/saved"); return; }
              setSavingToLibrary(true);
              libraryApi.save([libraryPaper(document)], { source: "reader" })
                .then(({ items }) => { setLibraryId(items[0]?.id || null); showToast(t("savedToLibrary")); })
                .catch(() => showToast(t("saveFailed")))
                .finally(() => setSavingToLibrary(false));
            }}
          >
            <BookmarkGlyph filled={Boolean(libraryId)} />{libraryId ? t("libSavedInLibrary") : t("libSaveToLibrary")}
          </button>
          {document.has_pdf ? (
            <a className="rd-button rd-button-quiet" href={readerApi.pdfUrl(document.id)} download={`${document.title.slice(0, 80)}.pdf`}><DownloadGlyph />{t("readerDownload")}</a>
          ) : null}
          {document.url || document.doi ? (
            <a className="rd-button rd-button-quiet" href={document.doi ? `https://doi.org/${document.doi}` : document.url || "#"} target="_blank" rel="noopener noreferrer"><ExternalGlyph />{t("readerOpenOriginal")}</a>
          ) : null}
        </div>
      </header>

      {notice ? (
        <p className="rd-notice" role="status">
          <span>{notice}</span>
          <button type="button" className="rd-icon-button" aria-label={t("close")} onClick={() => setNotice("")}><CloseGlyph /></button>
        </p>
      ) : null}

      {narrow ? (
        <>
          <div className="rd-tabs rd-tabs-mobile" role="tablist">
            {(["paper", ...PANEL_TABS] as MobilePane[]).map((item) => (
              <button key={item} type="button" role="tab" aria-selected={mobilePane === item} className={mobilePane === item ? "is-active" : ""} onClick={() => (item === "paper" ? setMobilePane("paper") : setTab(item))}>
                {item === "paper" ? t("readerTabPaper") : t(panelLabel(item))}
              </button>
            ))}
          </div>
          {mobilePane === "paper" ? paperPane : panel}
        </>
      ) : (
        <div className="rd-grid">
          {paperPane}
          {panel}
        </div>
      )}

      {toast ? <div className="rd-toast" role="status">{toast}</div> : null}
      <CompareTrayBar t={t} />
    </div>
  );
}

function panelLabel(tab: PanelTab): SearchCopyKey {
  return ({ summary: "readerTabSummary", chat: "readerTabChat", figures: "readerTabFigures", translate: "readerTabTranslate", info: "readerTabInfo" } as const)[tab];
}

function highlight(text: string, needle: string): ReactNode {
  const query = needle.trim();
  const paragraphs = text.split(/\n\s*\n/);
  return paragraphs.map((paragraph, index) => {
    const clean = paragraph.replace(/\s*\n\s*/g, " ");
    if (clean.length < 80 && /^(\d+(\.\d+)*\.?\s+\S|abstract$|references$)/i.test(clean)) return <h3 key={index} className="rd-text-heading">{clean}</h3>;
    if (query.length < 2) return <p key={index}>{clean}</p>;
    const parts = clean.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
    return <p key={index}>{parts.map((part, partIndex) => (partIndex % 2 ? <mark key={partIndex}>{part}</mark> : part))}</p>;
  });
}

/* ========================================================================== */
/*  Listen control                                                            */
/* ========================================================================== */

type Speech = ReturnType<typeof useSpeech>;

function ListenControl({ speech, id, label, t, onStart, disabled }: { speech: Speech; id: string; label: string; t: T; onStart: () => void; disabled?: boolean }) {
  if (!speech.supported) return null;
  const active = speech.activeId === id && speech.state !== "idle";
  if (!active) {
    return (
      <button type="button" className="rd-button rd-button-quiet" onClick={onStart} disabled={disabled}>
        <SpeakerGlyph />{label}
      </button>
    );
  }
  return (
    <div className="rd-player" role="group" aria-label={label}>
      <span className="rd-player-wave" aria-hidden="true"><i /><i /><i /></span>
      {speech.state === "paused" ? (
        <button type="button" onClick={speech.resume}><PlayGlyph />{t("readerResume")}</button>
      ) : (
        <button type="button" onClick={speech.pause}><PauseGlyph />{t("readerPause")}</button>
      )}
      <button
        type="button"
        className="rd-player-rate"
        aria-label={t("readerSpeed")}
        title={t("readerSpeed")}
        onClick={() => speech.setRate((value) => (value >= 1.5 ? 0.75 : Math.round((value + 0.25) * 100) / 100))}
      >
        {speech.rate}×
      </button>
      <button type="button" aria-label={t("readerStop")} title={t("readerStop")} onClick={speech.stop}><StopGlyph /></button>
    </div>
  );
}

/* ========================================================================== */
/*  Summary                                                                   */
/* ========================================================================== */

function PageChips({ pages, t, goToPage }: { pages: number[]; t: T; goToPage: (page: number) => void }) {
  if (!pages.length) return null;
  return (
    <span className="rd-page-chips">
      {pages.slice(0, 4).map((page) => (
        <button key={page} type="button" className="rd-page-chip" aria-label={t("readerGoToPage", { page })} onClick={() => goToPage(page)}>
          {t("readerPageChip", { page })}
        </button>
      ))}
    </span>
  );
}

function SummaryTab({ document, language, t, cost, autoRun, goToPage, speech, onNoVoice, showToast }: {
  document: ReaderDocument;
  language: string;
  t: T;
  cost: number;
  autoRun: boolean;
  goToPage: (page: number) => void;
  speech: Speech;
  onNoVoice: () => void;
  showToast: (message: string) => void;
}) {
  const [level, setLevel] = useState<Level>(() => {
    try {
      const saved = window.localStorage.getItem("resora-reader-level") as Level | null;
      return saved && LEVELS.includes(saved) ? saved : "student";
    } catch {
      return "student";
    }
  });
  const [summaries, setSummaries] = useState<Partial<Record<Level, ReaderSummary>>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const started = useRef(false);
  const summary = summaries[level];

  const run = useCallback(async (target: Level) => {
    setLoading(true);
    setError("");
    try {
      const result = await readerApi.summary(document.id, target, language);
      setSummaries((current) => ({ ...current, [target]: result }));
    } catch (caught) {
      setError(caught instanceof CreditLimitError ? limitText(caught.limit, language, t) : t("readerSummaryFailed"));
    } finally {
      setLoading(false);
    }
  }, [document.id, language, t]);

  useEffect(() => {
    if (autoRun && !started.current) {
      started.current = true;
      void run(level);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun]);

  useEffect(() => {
    setSummaries({});
  }, [language]);

  function chooseLevel(next: Level) {
    setLevel(next);
    try {
      window.localStorage.setItem("resora-reader-level", next);
    } catch {
      /* ignore */
    }
  }

  const sectionEntries = summary ? Object.entries(summary.sections).filter(([key, point]) => SECTION_LABELS[key] && point.text) : [];
  const speakable = summary ? [summary.tldr.text, ...summary.key_points.map((point) => point.text), ...sectionEntries.map(([key, point]) => `${t(SECTION_LABELS[key])}. ${point.text}`)] : [];

  function copySummary() {
    if (!summary) return;
    const text = [`${t("readerTldr")}: ${summary.tldr.text}`, "", `${t("readerKeyPoints")}:`, ...summary.key_points.map((point) => `• ${point.text}`), "", ...sectionEntries.map(([key, point]) => `${t(SECTION_LABELS[key])}: ${point.text}`)].join("\n");
    void navigator.clipboard?.writeText(text).then(() => showToast(t("readerCopied")), () => undefined);
  }

  return (
    <div className="rd-summary">
      <div className="rd-row">
        <div className="rd-seg" role="radiogroup" aria-label={t("readerLevel")}>
          {LEVELS.map((item) => (
            <button key={item} type="button" role="radio" aria-checked={level === item} className={level === item ? "is-active" : ""} onClick={() => chooseLevel(item)}>
              {t(item === "expert" ? "readerLevelExpert" : item === "student" ? "readerLevelStudent" : "readerLevelSimple")}
            </button>
          ))}
        </div>
        {summary ? (
          <div className="rd-row-actions">
            <ListenControl speech={speech} id="summary" label={t("readerListen")} t={t} onStart={() => {
              if (!speech.speak("summary", speakable, language)) onNoVoice();
            }} />
            <button type="button" className="rd-icon-button" aria-label={t("readerCopy")} title={t("readerCopy")} onClick={copySummary}><CopyGlyph /></button>
          </div>
        ) : null}
      </div>

      {loading ? (
        <div className="rd-working" role="status">
          <span className="rd-spinner" aria-hidden="true" />
          <span>{t("readerSummarizing")}</span>
          <div className="rd-skel rd-skel-block" />
          <div className="rd-skel rd-skel-line" />
          <div className="rd-skel rd-skel-line short" />
        </div>
      ) : summary ? (
        <>
          {summary.basic ? <p className="rd-hint">{t("readerBasicNote")}</p> : null}
          {summary.basis === "abstract" ? <p className="rd-hint">{t("readerFromAbstract")}</p> : null}
          <section className="rd-tldr">
            <h2>{t("readerTldr")}</h2>
            <p dir="auto">{summary.tldr.text} <PageChips pages={summary.tldr.pages} t={t} goToPage={goToPage} /></p>
          </section>
          <section className="rd-block">
            <h2>{t("readerKeyPoints")}</h2>
            <ul className="rd-points">
              {summary.key_points.map((point, index) => (
                <li key={index}><span dir="auto">{point.text}</span> <PageChips pages={point.pages} t={t} goToPage={goToPage} /></li>
              ))}
            </ul>
          </section>
          {sectionEntries.length ? (
            <section className="rd-block">
              <h2>{t("readerDetails")}</h2>
              <dl className="rd-sections">
                {sectionEntries.map(([key, point]) => (
                  <div key={key}>
                    <dt>{t(SECTION_LABELS[key])}</dt>
                    <dd dir="auto">{point.text} <PageChips pages={point.pages} t={t} goToPage={goToPage} /></dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : null}
        </>
      ) : (
        <div className="rd-start">
          <span className="rd-start-icon" aria-hidden="true"><SparkGlyph /></span>
          <p>{t("readerSummaryIntro")}</p>
          <button type="button" className="rd-button rd-button-primary" onClick={() => void run(level)}>{t("readerSummarize")}</button>
          <span className="rd-faint">{cost === 1 ? t("readerCreditsOne") : t("readerCredits", { count: cost })}</span>
        </div>
      )}
      {error ? <p className="rd-alert" role="alert">{error}</p> : null}
    </div>
  );
}

/* ========================================================================== */
/*  Chat                                                                      */
/* ========================================================================== */

function ChatTab({ messages, busy, onAsk, t, cost, goToPage, isAbstract }: {
  messages: ChatMessage[];
  busy: boolean;
  onAsk: (question: string) => void;
  t: T;
  cost: number;
  goToPage: (page: number) => void;
  isAbstract: boolean;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length, busy]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim()) return;
    onAsk(draft);
    setDraft("");
  }

  return (
    <div className="rd-chat">
      {!messages.length ? (
        <div className="rd-chat-intro">
          <p>{t("readerChatIntro")}</p>
          {isAbstract ? <p className="rd-hint">{t("readerFromAbstract")}</p> : null}
          <div className="rd-suggestions">
            {SUGGESTIONS.map((key) => (
              <button key={key} type="button" className="rd-suggestion" onClick={() => onAsk(t(key))} disabled={busy}>{t(key)}</button>
            ))}
          </div>
        </div>
      ) : (
        <ol className="rd-messages">
          {messages.map((message) => (
            <li key={message.id} className={`rd-message is-${message.role}${message.failed ? " is-failed" : ""}`}>
              {message.role === "user" ? <span className="rd-message-who">{t("readerYou")}</span> : null}
              <p dir="auto">{message.answer?.not_found ? t("readerNotFound") : message.text}</p>
              {message.answer && !message.answer.not_found && message.answer.citations.length ? (
                <ul className="rd-quotes">
                  {message.answer.citations.map((citation, index) => (
                    <li key={index}>
                      <button type="button" className="rd-page-chip" onClick={() => goToPage(citation.page)} aria-label={t("readerGoToPage", { page: citation.page })}>
                        {t("readerPageChip", { page: citation.page })}
                      </button>
                      <q dir="auto">{citation.quote}</q>
                    </li>
                  ))}
                </ul>
              ) : null}
              {message.answer && !message.answer.not_found ? (
                <span className={`rd-confidence is-${message.answer.confidence}`}>
                  <i aria-hidden="true" />
                  {t(message.answer.confidence === "high" ? "readerConfidenceHigh" : message.answer.confidence === "low" ? "readerConfidenceLow" : "readerConfidenceMedium")}
                </span>
              ) : null}
            </li>
          ))}
          {busy ? (
            <li className="rd-message is-assistant is-thinking" role="status"><span className="rd-dots" aria-hidden="true"><i /><i /><i /></span>{t("readerThinking")}</li>
          ) : null}
          <div ref={endRef} />
        </ol>
      )}
      <form className="rd-chat-input" onSubmit={submit}>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={t("readerChatPlaceholder")} aria-label={t("readerChatPlaceholder")} dir="auto" maxLength={1200} />
        <button type="submit" className="rd-button rd-button-primary" disabled={!draft.trim() || busy}>{t("readerSend")}</button>
      </form>
      <p className="rd-faint rd-center-text">{cost === 1 ? t("readerCreditsOne") : t("readerCredits", { count: cost })}</p>
    </div>
  );
}

/* ========================================================================== */
/*  Figures                                                                   */
/* ========================================================================== */

function FiguresTab({ document, t, goToPage, onExplain }: { document: ReaderDocument; t: T; goToPage: (page: number) => void; onExplain: (label: string) => void }) {
  if (!document.captions.length) return <p className="rd-empty">{t("readerNoFigures")}</p>;
  return (
    <div className="rd-figures">
      <p className="rd-hint">{t("readerFiguresIntro")}</p>
      <ul>
        {document.captions.map((item) => {
          const label = item.kind === "figure" ? t("readerFigure", { n: item.number }) : t("readerTable", { n: item.number });
          return (
            <li key={`${item.kind}-${item.number}`} className="rd-figure">
              <div className="rd-figure-head">
                <span className={`rd-figure-kind is-${item.kind}`}>{item.kind === "figure" ? <ImageGlyph /> : <TableGlyph />}{label}</span>
                <button type="button" className="rd-page-chip" onClick={() => goToPage(item.page)} aria-label={t("readerGoToPage", { page: item.page })}>{t("readerPageChip", { page: item.page })}</button>
              </div>
              <p dir="auto">{item.caption}</p>
              <button type="button" className="rd-button rd-button-quiet" onClick={() => onExplain(`${label} (${item.caption.slice(0, 120)})`)}><SparkGlyph />{t("readerExplain")}</button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ========================================================================== */
/*  Translate                                                                 */
/* ========================================================================== */

function TranslateTab({ document, language, t, currentPage, goToPage, speech, onNoVoice }: {
  document: ReaderDocument;
  language: string;
  t: T;
  currentPage: number;
  goToPage: (page: number) => void;
  speech: Speech;
  onNoVoice: () => void;
}) {
  const [target, setTarget] = useState(language !== "en" ? language : "");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<"side" | "only">("side");
  const [translated, setTranslated] = useState<Record<string, TranslatedPage[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const pickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!pickerOpen) return;
    const close = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setPickerOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setPickerOpen(false);
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", escape);
    };
  }, [pickerOpen]);

  const done = translated[target] || [];
  const lastDone = done.length ? Math.max(...done.map((page) => page.page)) : 0;
  const start = lastDone ? lastDone + 1 : currentPage;
  const end = Math.min(document.page_count, start + 4);

  async function translate() {
    if (!target || start > document.page_count) return;
    setLoading(true);
    setError("");
    try {
      const pages = Array.from({ length: end - start + 1 }, (_, index) => start + index);
      const result = await readerApi.translate(document.id, pages, target);
      setTranslated((current) => ({ ...current, [target]: [...(current[target] || []), ...result.pages].sort((a, b) => a.page - b.page) }));
    } catch (caught) {
      setError(caught instanceof CreditLimitError ? limitText(caught.limit, language, t) : t("readerTranslateFailed"));
    } finally {
      setLoading(false);
    }
  }

  const choices = languages.filter((item) => item.code !== "en" || target === "en").filter((item) => `${item.nativeName} ${item.englishName}`.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <div className="rd-translate">
      <p className="rd-hint">{t("readerTranslateIntro")}</p>
      <div className="rd-row">
        <div className="rd-picker" ref={pickerRef}>
          <button type="button" className="rd-pill" aria-haspopup="listbox" aria-expanded={pickerOpen} onClick={() => setPickerOpen((value) => !value)}>
            <GlobeGlyph /><span className="rd-faint">{t("readerTranslateTo")}</span><b>{target ? nativeName(target) : "—"}</b><ChevronGlyph down />
          </button>
          {pickerOpen ? (
            <div className="rd-popover" role="listbox" aria-label={t("readerTranslateTo")}>
              <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder={t("languageSearch")} aria-label={t("languageSearch")} autoFocus dir="auto" />
              <div className="rd-popover-scroll">
                {choices.map((item) => (
                  <button key={item.code} type="button" role="option" aria-selected={target === item.code} className={target === item.code ? "is-selected" : ""} lang={item.code} onClick={() => {
                    setTarget(item.code);
                    setPickerOpen(false);
                    setFilter("");
                  }}>
                    <span>{item.nativeName}</span><span className="rd-faint">{item.englishName}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        {done.length ? (
          <div className="rd-seg" role="radiogroup" aria-label={t("readerSideBySide")}>
            <button type="button" role="radio" aria-checked={mode === "side"} className={mode === "side" ? "is-active" : ""} onClick={() => setMode("side")}>{t("readerSideBySide")}</button>
            <button type="button" role="radio" aria-checked={mode === "only"} className={mode === "only" ? "is-active" : ""} onClick={() => setMode("only")}>{t("readerTranslationOnly")}</button>
          </div>
        ) : null}
      </div>

      {done.length ? (
        <div className="rd-translation" lang={target} dir={directionOf(target)}>
          <div className="rd-row-actions">
            <ListenControl speech={speech} id="translation" label={t("readerListenTranslation")} t={t} onStart={() => {
              if (!speech.speak("translation", done.flatMap((page) => page.paragraphs), target)) onNoVoice();
            }} />
          </div>
          {done.map((page) => (
            <article key={page.page} className="rd-translated-page">
              <header>
                <button type="button" className="rd-page-chip" onClick={() => goToPage(page.page)} aria-label={t("readerGoToPage", { page: page.page })}>{t("readerPageChip", { page: page.page })}</button>
              </header>
              {page.paragraphs.map((paragraph, index) => (
                <div key={index} className={`rd-pair${mode === "side" ? " is-side" : ""}`}>
                  <p>{paragraph}</p>
                  {mode === "side" ? <p className="rd-original" lang="en" dir="ltr"><span>{t("readerOriginal")}</span>{page.original[index]}</p> : null}
                </div>
              ))}
            </article>
          ))}
        </div>
      ) : null}

      {loading ? (
        <div className="rd-working" role="status"><span className="rd-spinner" aria-hidden="true" />{t("readerTranslating")}</div>
      ) : target && start <= document.page_count ? (
        <button type="button" className="rd-button rd-button-primary rd-wide" onClick={() => void translate()}>
          {done.length ? t("readerTranslateMore") : t("readerTranslatePages", { from: start, to: end })}
        </button>
      ) : null}
      {target ? <p className="rd-faint rd-center-text">{t("readerCreditsOne")}</p> : null}
      {error ? <p className="rd-alert" role="alert">{error}</p> : null}
    </div>
  );
}

/* ========================================================================== */
/*  Info                                                                      */
/* ========================================================================== */

function InfoTab({ document, t, language, showToast }: { document: ReaderDocument; t: T; language: string; showToast: (message: string) => void }) {
  const number = (value: number) => {
    try {
      return new Intl.NumberFormat(language).format(value);
    } catch {
      return String(value);
    }
  };
  const rows: Array<[SearchCopyKey, ReactNode]> = [];
  if (document.authors.length) rows.push(["readerInfoAuthors", <bdi key="a">{document.authors.join(", ")}</bdi>]);
  if (document.venue) rows.push(["readerInfoVenue", <bdi key="v">{document.venue}</bdi>]);
  if (document.year) rows.push(["readerInfoYear", number(document.year)]);
  if (document.doi) rows.push(["readerInfoDoi", <a key="d" href={`https://doi.org/${document.doi}`} target="_blank" rel="noopener noreferrer" dir="ltr">{document.doi}</a>]);
  rows.push(["readerInfoAccess", sourceLabel(document.source, t)]);
  if (document.page_count) rows.push(["readerInfoPages", number(document.page_count)]);
  if (document.word_count) rows.push(["readerInfoWords", number(document.word_count)]);
  if (document.citation_count) rows.push(["readerInfoCitations", number(document.citation_count)]);
  return (
    <div className="rd-info">
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}><dt>{t(label)}</dt><dd>{value}</dd></div>
        ))}
      </dl>
      {document.abstract ? (
        <section className="rd-block">
          <h2>{t("abstractLabel")}</h2>
          <p dir="auto" className="rd-abstract">{document.abstract}</p>
        </section>
      ) : null}
      <button type="button" className="rd-button rd-button-quiet" onClick={() => void navigator.clipboard?.writeText(apa(document)).then(() => showToast(t("readerCopied")), () => undefined)}>
        <CopyGlyph />{t("readerCite")}
      </button>
    </div>
  );
}

/* ========================================================================== */
/*  Icons (decorative; every control also has a text label or aria-label)     */
/* ========================================================================== */

function Svg({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
function FileGlyph({ small = false }: { small?: boolean }) { return <Svg size={small ? 16 : 26}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></Svg>; }
function LockGlyph() { return <Svg size={13}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></Svg>; }
function LinkGlyph() { return <Svg size={17}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></Svg>; }
function CloseGlyph() { return <Svg size={15}><path d="M6 6l12 12M18 6 6 18" /></Svg>; }
function ChevronGlyph({ flip = false, down = false }: { flip?: boolean; down?: boolean }) {
  return <span className={flip ? "rd-flip" : ""}><Svg size={15}>{down ? <path d="m6 9 6 6 6-6" /> : <path d="m9 6 6 6-6 6" />}</Svg></span>;
}
function BookmarkGlyph({ filled = false }: { filled?: boolean }) { return <Svg size={15}><path d="M6 4h12v17l-6-4-6 4V4Z" fill={filled ? "currentColor" : "none"} /></Svg>; }
function MinusGlyph() { return <Svg size={15}><path d="M5 12h14" /></Svg>; }
function PlusGlyph() { return <Svg size={15}><path d="M12 5v14M5 12h14" /></Svg>; }
function SearchGlyph() { return <Svg size={15}><circle cx="11" cy="11" r="7" /><path d="m20 20-4.2-4.2" /></Svg>; }
function MoonGlyph() { return <Svg size={14}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" /></Svg>; }
function DownloadGlyph() { return <Svg size={15}><path d="M12 4v11M7 11l5 5 5-5M5 20h14" /></Svg>; }
function ExternalGlyph() { return <Svg size={15}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>; }
function SpeakerGlyph() { return <Svg size={15}><path d="M4 9v6h4l5 4V5L8 9H4Z" /><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" /></Svg>; }
function PlayGlyph() { return <Svg size={14}><path d="M7 5v14l11-7L7 5Z" /></Svg>; }
function PauseGlyph() { return <Svg size={14}><path d="M8 5v14M16 5v14" /></Svg>; }
function StopGlyph() { return <Svg size={14}><rect x="6" y="6" width="12" height="12" rx="2" /></Svg>; }
function CopyGlyph() { return <Svg size={15}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a1 1 0 0 1 1-1h10" /></Svg>; }
function SparkGlyph() { return <Svg size={16}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /></Svg>; }
function ImageGlyph() { return <Svg size={14}><rect x="4" y="5" width="16" height="14" rx="2" /><path d="m7 16 3.5-4 2.5 3 1.5-1.8L18 17" /></Svg>; }
function TableGlyph() { return <Svg size={14}><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M4 10h16M10 10v9" /></Svg>; }
function CompareGlyph() { return <Svg size={15}><path d="M7 5v14M17 5v14M4 8h6M14 8h6M4 16h6M14 16h6" /></Svg>; }
function GlobeGlyph() { return <Svg size={15}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></Svg>; }
