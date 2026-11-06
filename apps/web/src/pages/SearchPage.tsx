import { FormEvent, KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, ReactNode, RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { researchLanguages } from "../i18n/languages";
import "./SearchPage.css";
import {
  askAboutResults,
  CreditLimitError,
  deleteSavedSearch,
  fetchCreditEstimate,
  fetchSavedSearches,
  fetchUsage,
  findEntities,
  updateSavedSearch,
  type EntityMatches,
  type Usage,
  type UsageLimit,
  looksLikeIdentifier,
  resolveIdentifier,
  streamResearch,
  type CreditEstimate,
  type QueryUnderstanding,
  type ResearchAnswer,
  type ResearchStepId,
  type SavedSearch,
  type StepStatus,
} from "./search/researchApi";
import { AnswerCard, AnswerSkeleton, AskBar, ResearchSteps, type Translate } from "./search/ResearchViews";
import { storeHandoff } from "./reader/readerApi";
import { libraryApi, paperInputFrom } from "./library/libraryApi";
import { CompareTrayBar } from "./compare/CompareTrayBar";
import { toggleTray, useTray } from "./compare/compareTray";
import { hasSearchCatalog, useSearchCopy, type SearchCopyKey } from "./search/copy";

/* -------------------------------------------------------------------------- */
/*  Configuration                                                             */
/* -------------------------------------------------------------------------- */

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

/** Research sources are a backend concern. They are sent with the request but never shown in the UI. */
const enabledSourceIds = ["openalex", "semantic_scholar", "crossref", "arxiv", "europe_pmc", "core", "doaj", "dblp", "zenodo", "preprints", "hal"];
const PAGE_SIZE = 20;
const SLOW_SEARCH_MS = 4000;
const TOAST_MS = 3200;
const LANGUAGE_SOURCE_KEY = "resora-language-source";
const CURRENT_YEAR = new Date().getFullYear();

/* -------------------------------------------------------------------------- */
/*  Types                                                                     */
/* -------------------------------------------------------------------------- */

type SearchPaper = {
  paper_id: string;
  title: string;
  translated_title?: string | null;
  abstract?: string | null;
  translated_abstract?: string | null;
  translation_status?: string;
  year?: number | null;
  venue?: string | null;
  citation_count: number;
  is_open_access: boolean;
  source: string;
  authors: Array<{ name?: string }>;
  result_badges: string[];
  micro_summary?: string | null;
  datasets: string[];
  methodologies: string[];
  code_repositories: string[];
  peer_review_status: string;
  is_preprint: boolean;
  doi?: string | null;
  publication_type?: string | null;
  pdf_urls?: string[];
  external_ids?: Record<string, string>;
  url?: string | null;
  pdf_url?: string | null;
  matched_terms?: string[];
};

type SearchResponse = {
  query: string;
  total_results: number;
  deduplicated_results?: number;
  papers: SearchPaper[];
  translation_retry_ids?: string[];
  pagination?: { page: number; total_pages: number; has_next_page: boolean };
  suggestions?: string[];
  resumable_session_id?: string | null;
  source_failures?: string[];
  query_understanding?: QueryUnderstanding;
};

type HistoryItem = { session_id: string; query: string; created_at: string; result_count: number };

type SearchMode = "search" | "research";
type SortMode = "relevance" | "citations" | "year";
type Status = "idle" | "loading" | "done" | "error";

type Filters = {
  yearFrom: string;
  yearTo: string;
  openAccess: boolean;
  peerReviewed: boolean;
  studyType: string;
  paperLanguage: string;
  minCitations: string;
  author: string;
  venue: string;
  hasCode: boolean;
  hasDataset: boolean;
  preprintOnly: boolean;
  includeRetracted: boolean;
};

const emptyFilters: Filters = {
  yearFrom: "",
  yearTo: "",
  openAccess: false,
  peerReviewed: false,
  studyType: "",
  paperLanguage: "",
  minCitations: "",
  author: "",
  venue: "",
  hasCode: false,
  hasDataset: false,
  preprintOnly: false,
  includeRetracted: false,
};

type LanguageInfo = { code: string; nativeName: string; englishName: string; direction?: string };

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onresult: ((event: { results: ArrayLike<{ 0?: { transcript?: string } }> }) => void) | null;
  start: () => void;
  abort?: () => void;
};
type SpeechWindow = Window & {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};

/* -------------------------------------------------------------------------- */
/*  Copy (English source catalog — every user-visible string lives here)      */
/* -------------------------------------------------------------------------- */



const languages = researchLanguages as unknown as LanguageInfo[];
/** Only languages with a translated catalog can be selected, so the UI is never half-translated. */
const selectableLanguages = languages.filter((item) => hasSearchCatalog(item.code));

/* -------------------------------------------------------------------------- */
/*  Small utilities                                                           */
/* -------------------------------------------------------------------------- */

function readStorage(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable (private mode) — ignore */
  }
}

function languageInfo(code: string) {
  return languages.find((item) => item.code === code);
}

function languageName(code: string) {
  return languageInfo(code)?.nativeName || "English";
}

function languageDirection(code: string) {
  return languageInfo(code)?.direction === "rtl" ? "rtl" : "ltr";
}

/** Map a detected language code to one the user can actually use (exact match first, then same base language). */
function resolveSelectableLanguage(code: string | null) {
  if (!code) return null;
  const exact = selectableLanguages.find((item) => item.code === code);
  if (exact) return exact.code;
  const base = code.split("-")[0];
  return selectableLanguages.find((item) => item.code.split("-")[0] === base)?.code || null;
}

function formatNumber(value: number, locale: string) {
  try {
    return new Intl.NumberFormat(locale).format(value);
  } catch {
    return String(value);
  }
}

function pluralIsOne(value: number, locale: string) {
  try {
    return new Intl.PluralRules(locale).select(value) === "one";
  } catch {
    return value === 1;
  }
}


const speechLocales: Record<string, string> = {
  en: "en-US", ur: "ur-PK", hi: "hi-IN", ar: "ar-SA", fa: "fa-IR", bn: "bn-BD", es: "es-ES", fr: "fr-FR", de: "de-DE",
  it: "it-IT", ru: "ru-RU", tr: "tr-TR", ja: "ja-JP", ko: "ko-KR", id: "id-ID", vi: "vi-VN", th: "th-TH", pl: "pl-PL",
  "zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "pt-BR": "pt-BR", "pt-PT": "pt-PT", "pa-Guru": "pa-IN", "pa-Arab": "pa-PK",
  ta: "ta-IN", te: "te-IN", mr: "mr-IN", gu: "gu-IN", kn: "kn-IN", ml: "ml-IN", sw: "sw-KE", fil: "fil-PH",
};

/* ------------------------------ Language detection ------------------------------ */

const latinHints: Record<string, string[]> = {
  en: ["the", "of", "and", "in", "for", "with", "on", "to", "from", "how", "what", "why", "does", "is", "are", "between"],
  es: ["el", "la", "los", "las", "del", "para", "con", "una", "sobre", "como", "por", "que", "entre", "aprendizaje", "investigación"],
  fr: ["le", "les", "des", "du", "pour", "avec", "une", "sur", "dans", "et", "est", "entre", "apprentissage", "recherche"],
  de: ["der", "die", "das", "und", "für", "mit", "von", "zur", "zum", "über", "eine", "ist", "lernen", "forschung"],
  "pt-BR": ["os", "as", "do", "da", "dos", "das", "para", "com", "uma", "sobre", "em", "entre", "aprendizagem", "pesquisa"],
  it: ["il", "lo", "gli", "della", "delle", "degli", "per", "con", "una", "sulla", "nel", "apprendimento", "ricerca"],
  id: ["dan", "yang", "untuk", "dengan", "pada", "dalam", "terhadap", "penelitian", "pembelajaran"],
  tr: ["ve", "için", "ile", "bir", "üzerine", "araştırma", "öğrenme", "etkisi"],
  pl: ["oraz", "dla", "na", "w", "badania", "uczenie", "wpływ"],
  nl: ["het", "een", "van", "voor", "met", "onderzoek", "en"],
  sw: ["na", "ya", "kwa", "katika", "utafiti"],
  fil: ["ang", "ng", "sa", "mga", "pananaliksik"],
};

const diacriticHints: Array<[RegExp, string, number]> = [
  [/[ñ¿¡]/u, "es", 3],
  [/[ãõ]/u, "pt-BR", 3],
  [/[œæ]|[êèàùûî]/u, "fr", 2],
  [/[ç]/u, "fr", 1],
  [/[ß]|[äöü]/u, "de", 2],
  [/[ğış]/u, "tr", 3],
  [/[ąćęłńśźż]/u, "pl", 3],
  [/[ơưđ]|[ạảấầẩẫậắằẳẵặẹẻẽếềểễệịỉọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/u, "vi", 4],
];

/**
 * Detects the language a user writes in. Script-based for non-Latin scripts, word and diacritic hints for
 * Latin scripts. Returns null when the text is too ambiguous to decide.
 */
function detectQueryLanguage(raw: string): string | null {
  const value = raw.trim();
  if (value.length < 2) return null;
  if (/^10\.\d{4,9}\//.test(value)) return null; // DOI — language neutral

  if (/[぀-ヿ]/u.test(value)) return "ja";
  if (/[가-힯ᄀ-ᇿ]/u.test(value)) return "ko";
  if (/[一-鿿]/u.test(value)) return /[們這個來說國學門體會對時後區無與為]/u.test(value) ? "zh-Hant" : "zh-Hans";
  if (/[฀-๿]/u.test(value)) return "th";
  if (/[ঀ-৿]/u.test(value)) return "bn";
  if (/[਀-੿]/u.test(value)) return "pa-Guru";
  if (/[઀-૿]/u.test(value)) return "gu";
  if (/[஀-௿]/u.test(value)) return "ta";
  if (/[ఀ-౿]/u.test(value)) return "te";
  if (/[ಀ-೿]/u.test(value)) return "kn";
  if (/[ഀ-ൿ]/u.test(value)) return "ml";
  if (/[ऀ-ॿ]/u.test(value)) return /(आहे|आणि|च्या|ला |मध्ये)/u.test(value) ? "mr" : "hi";
  if (/[ሀ-፿]/u.test(value)) return "am";
  if (/[֐-׿]/u.test(value)) return "he";
  if (/[Ͱ-Ͽ]/u.test(value)) return "el";
  if (/[Ѐ-ӿ]/u.test(value)) return /[іїєґ]/iu.test(value) ? "uk" : "ru";
  if (/[؀-ۿݐ-ݿ]/u.test(value)) {
    if (/[ٹڈڑںےۓھ]/u.test(value)) return "ur";
    if (/[پچژگ]/u.test(value) || /ی/u.test(value)) return /[ةى]/u.test(value) ? "ar" : "fa";
    return "ar";
  }

  const lower = value.toLowerCase();
  const words = lower.match(/[\p{L}]+/gu) || [];
  if (!words.length) return null;
  const scores: Record<string, number> = {};
  for (const word of words) {
    for (const [code, hints] of Object.entries(latinHints)) {
      if (hints.includes(word)) scores[code] = (scores[code] || 0) + 1;
    }
  }
  for (const [pattern, code, weight] of diacriticHints) {
    if (pattern.test(lower)) scores[code] = (scores[code] || 0) + weight;
  }
  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const [best, second] = ranked;
  if (best && best[0] !== "en" && best[1] >= 2 && (!second || best[1] > second[1])) return best[0];
  // Plain ASCII text without hints of another language is treated as English (technical terms, short topics).
  if (/^[\x20-\x7e]+$/.test(value)) return "en";
  return best && (!second || best[1] > second[1]) ? best[0] : null;
}

/* ------------------------------ Text cleaning ------------------------------ */

function plainText(value: string) {
  if (!value) return "";
  let text = value;
  if (/[<&]/.test(text) && typeof DOMParser !== "undefined") {
    text = new DOMParser().parseFromString(text.replace(/<\/?(jats:)?[a-z][^>]*>/gi, " "), "text/html").body.textContent || "";
  }
  return text.replace(/[\u200b\ufeff]/g, "").replace(/\s+/g, " ").trim();
}

function comparableWord(word: string) {
  return word.normalize("NFKD").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

/** Removes markup, "Abstract" prefixes and a repeated title from the start of a snippet. */
function cleanSnippet(title: string, snippet: string) {
  let text = plainText(snippet).replace(/^(abstract|summary|background)\s*[:.\-–—]?\s*/i, "");
  const titleWords = plainText(title).split(" ").map(comparableWord).filter(Boolean);
  if (titleWords.length >= 2) {
    const tokens = [...text.matchAll(/\S+/g)];
    let matched = 0;
    let cutAt = 0;
    for (const token of tokens) {
      const word = comparableWord(token[0]);
      if (!word) {
        cutAt = (token.index || 0) + token[0].length;
        continue;
      }
      if (matched < titleWords.length && word === titleWords[matched]) {
        matched += 1;
        cutAt = (token.index || 0) + token[0].length;
        if (matched === titleWords.length) break;
      } else {
        break;
      }
    }
    if (matched >= Math.max(2, Math.ceil(titleWords.length * 0.85))) {
      text = text.slice(cutAt).replace(/^[\s:.;,\-–—|]+/, "");
    }
  }
  return text;
}

function displayYear(year?: number | null) {
  return year && year >= 1500 && year <= CURRENT_YEAR ? year : null;
}

function hostName(url?: string | null) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function authorNames(paper: SearchPaper) {
  return paper.authors.map((author) => (author.name || "").trim()).filter((name) => name && !/^unknown/i.test(name));
}

function isWeb(paper: SearchPaper) {
  return paper.publication_type === "web";
}

function pdfLink(paper: SearchPaper) {
  return paper.pdf_url || paper.pdf_urls?.[0] || null;
}

function isRetracted(paper: SearchPaper) {
  return paper.result_badges.some((badge) => /retract/i.test(badge));
}

function doiUrl(paper: SearchPaper) {
  return paper.doi ? `https://doi.org/${paper.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")}` : null;
}

function apaCitation(paper: SearchPaper) {
  const names = authorNames(paper);
  const authors = names.length > 20 ? `${names.slice(0, 19).join(", ")}, … ${names[names.length - 1]}` : names.join(", ");
  const year = displayYear(paper.year) || "n.d.";
  const link = doiUrl(paper) || paper.url || "";
  return [authors ? `${authors} (${year}).` : `(${year}).`, `${plainText(paper.title)}.`, paper.venue ? `${paper.venue}.` : "", link]
    .filter(Boolean)
    .join(" ");
}

function bibtexCitation(paper: SearchPaper, index = 0) {
  const first = authorNames(paper)[0] || "resora";
  const key = `${first.split(/\s+/).pop()?.replace(/[^a-z0-9]/gi, "") || "paper"}${displayYear(paper.year) || ""}${index ? `_${index}` : ""}`;
  const fields = [
    `  title = {${plainText(paper.title)}}`,
    authorNames(paper).length ? `  author = {${authorNames(paper).join(" and ")}}` : "",
    displayYear(paper.year) ? `  year = {${displayYear(paper.year)}}` : "",
    paper.venue ? `  journal = {${paper.venue}}` : "",
    paper.doi ? `  doi = {${paper.doi}}` : "",
    paper.url ? `  url = {${paper.url}}` : "",
  ].filter(Boolean);
  return `@article{${key},\n${fields.join(",\n")}\n}`;
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function normalizePaper(paper: Partial<SearchPaper>): SearchPaper {
  return {
    paper_id: paper.paper_id || paper.doi || paper.title || Math.random().toString(36).slice(2),
    title: plainText(paper.title || ""),
    translated_title: paper.translated_title ? plainText(paper.translated_title) : null,
    abstract: paper.abstract || null,
    translated_abstract: paper.translated_abstract || null,
    translation_status: paper.translation_status || "original",
    year: paper.year || null,
    venue: paper.venue ? plainText(paper.venue) : null,
    citation_count: Number(paper.citation_count || 0),
    is_open_access: Boolean(paper.is_open_access),
    source: paper.source || "",
    authors: asArray(paper.authors),
    result_badges: asArray(paper.result_badges),
    micro_summary: paper.micro_summary || null,
    datasets: asArray(paper.datasets),
    methodologies: asArray(paper.methodologies),
    code_repositories: asArray(paper.code_repositories),
    peer_review_status: paper.peer_review_status || "unknown",
    is_preprint: Boolean(paper.is_preprint),
    doi: paper.doi || null,
    publication_type: paper.publication_type || null,
    pdf_urls: asArray(paper.pdf_urls),
    external_ids: paper.external_ids || {},
    url: paper.url || null,
    pdf_url: paper.pdf_url || null,
    matched_terms: asArray(paper.matched_terms),
  };
}

function dedupeKey(paper: SearchPaper) {
  return paper.doi?.trim().toLowerCase() || comparableWord(paper.title) || paper.paper_id;
}

function mergePapers(current: SearchPaper[], incoming: SearchPaper[]) {
  const byKey = new Map(current.map((paper) => [dedupeKey(paper), paper]));
  for (const paper of incoming) {
    const key = dedupeKey(paper);
    const existing = byKey.get(key);
    if (!existing || (isWeb(existing) && !isWeb(paper))) byKey.set(key, paper);
  }
  return [...byKey.values()];
}

function downloadText(content: string, filename: string, type = "text/plain") {
  const blob = new Blob([content], { type: `${type};charset=utf-8` });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

function countActiveMoreFilters(filters: Filters) {
  return [
    filters.studyType,
    filters.paperLanguage,
    filters.minCitations && Number(filters.minCitations) > 0,
    filters.author.trim(),
    filters.venue.trim(),
    filters.hasCode,
    filters.hasDataset,
    filters.preprintOnly,
    filters.includeRetracted,
  ].filter(Boolean).length;
}

/* -------------------------------------------------------------------------- */
/*  Hooks                                                                     */
/* -------------------------------------------------------------------------- */

/** Closes a popover on outside pointer-down or Escape. */
function useDismiss(open: boolean, refs: Array<RefObject<HTMLElement | null>>, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      // Clicking the page scrollbar must not close an open menu.
      if (target === document.documentElement || event.clientX >= document.documentElement.clientWidth) return;
      if (refs.some((ref) => ref.current?.contains(target))) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, onClose]);
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

type SearchPageProps = {
  interfaceLanguage?: string;
  onLanguageChange?: (language: string, source?: "settings" | "auto") => void;
};

export function SearchPage({ interfaceLanguage = "en", onLanguageChange }: SearchPageProps) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  /* ---------- language ---------- */
  const [language, setLanguage] = useState(interfaceLanguage);
  const [languagePinned, setLanguagePinned] = useState(() => readStorage(LANGUAGE_SOURCE_KEY) === "settings");
  const [showOriginal, setShowOriginal] = useState(false);
  const [languageToast, setLanguageToast] = useState<{ previous: string } | null>(null);

  useEffect(() => setLanguage(interfaceLanguage), [interfaceLanguage]);

  const t = useSearchCopy(language);

  const direction = languageDirection(language);
  const translating = language !== "en" && !showOriginal;

  /* ---------- query + results ---------- */
  const [query, setQuery] = useState(() => searchParams.get("q") || "");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("search");
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [draftFilters, setDraftFilters] = useState<Filters>(emptyFilters);
  const [sort, setSort] = useState<SortMode>("relevance");
  const [status, setStatus] = useState<Status>("idle");
  const [papers, setPapers] = useState<SearchPaper[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [page, setPage] = useState(1);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [retryIds, setRetryIds] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreFailed, setLoadMoreFailed] = useState(false);
  const [slowSearch, setSlowSearch] = useState(false);
  const [understanding, setUnderstanding] = useState<QueryUnderstanding | null>(null);
  const [researchSteps, setResearchSteps] = useState<Partial<Record<ResearchStepId, StepStatus>>>({});
  const [researchAnswer, setResearchAnswer] = useState<ResearchAnswer | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchAnswerFailed, setResearchAnswerFailed] = useState(false);
  const [askLoading, setAskLoading] = useState(false);
  const [askAnswer, setAskAnswer] = useState<ResearchAnswer | null>(null);
  const [estimate, setEstimate] = useState<CreditEstimate | null>(null);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [limitNotice, setLimitNotice] = useState<UsageLimit | null>(null);
  const [entities, setEntities] = useState<EntityMatches>({ researchers: [], institutions: [] });

  /* ---------- UI state ---------- */
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const lookedUp = useRef(new Set<string>());
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [quickView, setQuickView] = useState<SearchPaper | null>(null);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [listening, setListening] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const lastUrlQueryRef = useRef<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const closeMenu = useCallback(() => setOpenMenu(null), []);
  const toggleMenu = useCallback((id: string) => setOpenMenu((current) => (current === id ? null : id)), []);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(""), TOAST_MS);
  }, []);

  /* ---------- workspace signals ---------- */
  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`${apiBaseUrl}/search/history`);
      if (!res.ok) return;
      const items = (await res.json()) as HistoryItem[];
      setHistory(Array.isArray(items) ? items : []);
    } catch {
      /* history is optional */
    }
  }, []);

  const loadSavedSearches = useCallback(async () => setSavedSearches(await fetchSavedSearches()), []);

  useEffect(() => {
    void loadHistory();
    void loadSavedSearches();
    void fetchCreditEstimate().then(setEstimate);
    void fetchUsage().then(setUsage);
    const speechWindow = window as SpeechWindow;
    setVoiceSupported(Boolean(speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition));
    return () => {
      abortRef.current?.abort();
      if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    };
  }, [loadHistory, loadSavedSearches]);

  const trayItems = useTray();
  const trayKeys = useMemo(() => new Set(trayItems.map((item) => item.key)), [trayItems]);

  const recentSearches = useMemo(() => {
    const seen = new Set<string>();
    return history
      .map((item) => item.query?.trim())
      .filter((item): item is string => Boolean(item) && !seen.has(item.toLowerCase()) && Boolean(seen.add(item.toLowerCase())))
      .slice(0, 4);
  }, [history]);

  /* ---------- search ---------- */
  type RunOptions = {
    query: string;
    page?: number;
    append?: boolean;
    language?: string;
    filters?: Filters;
    sort?: SortMode;
    mode?: SearchMode;
    queryType?: string;
    voiceTranscript?: string | null;
  };

  const runSearch = useCallback(async (options: RunOptions) => {
    const searchQuery = options.query.trim();
    if (!searchQuery) {
      showToast(t("emptyQuery"));
      return;
    }
    const append = Boolean(options.append);
    const targetPage = options.page || 1;
    const lang = options.language || language;
    const activeFilters = options.filters || filters;
    const activeSort = options.sort || sort;
    const activeMode = options.mode || mode;
    const translate = lang !== "en";

    if (!append) abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;
    const isCurrent = () => requestId === requestIdRef.current;

    if (append) {
      setLoadingMore(true);
      setLoadMoreFailed(false);
    } else {
      setStatus("loading");
      setPapers([]);
      setTotalResults(0);
      setHasNextPage(false);
      setSuggestions([]);
      setRetryIds([]);
      setLoadMoreFailed(false);
      setUnderstanding(null);
      setResearchAnswer(null);
      setResearchLoading(false);
      setAskAnswer(null);
      setEntities({ researchers: [], institutions: [] });
      setLimitNotice(null);
      setSubmittedQuery(searchQuery);
      lastUrlQueryRef.current = searchQuery;
      setSearchParams({ q: searchQuery }, { replace: true });
    }

    const payload = {
      query: searchQuery,
      page: targetPage,
      limit: PAGE_SIZE,
      sources: enabledSourceIds,
      language: lang,
      query_language: "auto",
      paper_language: activeFilters.paperLanguage || null,
      target_language: lang,
      translate_results: translate,
      min_citations: Number(activeFilters.minCitations) || 0,
      open_access_only: activeFilters.openAccess,
      study_type: activeFilters.studyType || null,
      quartile: null,
      sample_size_min: null,
      year_from: activeFilters.yearFrom ? Number(activeFilters.yearFrom) : null,
      year_to: activeFilters.yearTo ? Number(activeFilters.yearTo) : null,
      methodology: null,
      author: activeFilters.author.trim() || null,
      venue: activeFilters.venue.trim() || null,
      institution: null,
      dataset: null,
      peer_reviewed_only: activeFilters.peerReviewed,
      preprint_only: activeFilters.preprintOnly,
      include_retracted: activeFilters.includeRetracted,
      citation_context: null,
      region: null,
      chemical_formula: null,
      gene_or_protein: null,
      equipment_or_software: null,
      negative_results_only: false,
      temporal_aware: false,
      patent_overlap: false,
      grey_literature: false,
      conference_priority: false,
      cited_by_quality_only: false,
      private_search_vault: true,
      collaborative_session: false,
      sort_by: activeSort === "year" ? "recent" : activeSort,
      search_mode: activeMode === "research" ? "semantic" : "hybrid",
      query_type: options.queryType || "natural_language",
      voice_transcript: options.voiceTranscript || null,
      image_caption: null,
      session_id: append ? sessionId : null,
    };

    try {
      const res = await fetch(`${apiBaseUrl}/search/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream, application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`search ${res.status}`);

      let data: SearchResponse | undefined;
      if (res.headers.get("content-type")?.includes("text/event-stream") && res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";
        const consumeFrame = (frame: string) => {
          const lines = frame.split("\n");
          const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
          const eventData = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
          if (!eventName || !eventData) return;
          let parsed: unknown;
          try {
            parsed = JSON.parse(eventData);
          } catch {
            return;
          }
          const body = parsed as Partial<SearchResponse> & { message?: string };
          if (eventName === "source_results" && Array.isArray(body.papers) && !translate && !append && isCurrent()) {
            // Progressive results: show papers as soon as the first sources answer (original-language only).
            setPapers((current) => mergePapers(current, body.papers!.map(normalizePaper)));
          } else if (eventName === "done" && Array.isArray(body.papers)) {
            data = body as SearchResponse;
          } else if (eventName === "error") {
            throw new Error("search stream error");
          }
        };
        while (true) {
          const { value, done } = await reader.read();
          pending += decoder.decode(value, { stream: !done });
          const frames = pending.split("\n\n");
          pending = frames.pop() || "";
          for (const frame of frames) consumeFrame(frame);
          if (done) break;
        }
        if (pending.trim()) consumeFrame(pending);
      } else {
        data = (await res.json()) as SearchResponse;
      }

      if (!isCurrent()) return;
      if (!data) throw new Error("search ended early");

      const incoming = asArray(data.papers).map(normalizePaper).filter((paper) => paper.title);
      setSessionId(data.resumable_session_id || null);
      setPapers((current) => (append ? mergePapers(current, incoming) : incoming));
      setTotalResults(Number(data.total_results || 0));
      setPage(data.pagination?.page || targetPage);
      setHasNextPage(Boolean(data.pagination?.has_next_page));
      setSuggestions(asArray(data.suggestions).slice(0, 4));
      setRetryIds(asArray(data.translation_retry_ids));
      if (!append) {
        setUnderstanding(data.query_understanding || null);
        if (searchQuery.split(/\s+/).length <= 6 && !looksLikeIdentifier(searchQuery)) {
          void findEntities(searchQuery).then((matches) => isCurrent() && setEntities(matches));
        }
        setStatus("done");
      }
      void loadHistory();
    } catch (error) {
      if ((error as Error)?.name === "AbortError" || !isCurrent()) return;
      if (append) {
        setLoadMoreFailed(true);
      } else {
        setStatus("error");
      }
    } finally {
      if (isCurrent()) setLoadingMore(false);
    }
  }, [filters, language, loadHistory, mode, sessionId, setSearchParams, showToast, sort, t]);

  /** Research with Resora: real progress steps → papers → cited answer (streamed). */
  const runResearch = useCallback(async (options: RunOptions) => {
    const searchQuery = options.query.trim();
    if (!searchQuery) {
      showToast(t("emptyQuery"));
      return;
    }
    const lang = options.language || language;
    const activeFilters = options.filters || filters;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;
    const isCurrent = () => requestId === requestIdRef.current;

    setStatus("loading");
    setPapers([]);
    setTotalResults(0);
    setHasNextPage(false);
    setSuggestions([]);
    setRetryIds([]);
    setLoadMoreFailed(false);
    setUnderstanding(null);
    setResearchSteps({});
    setResearchAnswer(null);
    setResearchAnswerFailed(false);
    setResearchLoading(true);
    setAskAnswer(null);
    setEntities({ researchers: [], institutions: [] });
    setLimitNotice(null);
    setSubmittedQuery(searchQuery);
    lastUrlQueryRef.current = searchQuery;
    setSearchParams({ q: searchQuery, mode: "research" }, { replace: true });

    let answered = false;
    let gotPapers = false;
    try {
      await streamResearch<SearchPaper>(
        {
          query: searchQuery,
          language: lang,
          year_from: activeFilters.yearFrom ? Number(activeFilters.yearFrom) : null,
          year_to: activeFilters.yearTo ? Number(activeFilters.yearTo) : null,
          open_access_only: activeFilters.openAccess,
          peer_reviewed_only: activeFilters.peerReviewed,
          preprint_only: activeFilters.preprintOnly,
          include_retracted: activeFilters.includeRetracted,
          study_type: activeFilters.studyType || null,
          paper_language: activeFilters.paperLanguage || null,
          min_citations: Number(activeFilters.minCitations) || 0,
          author: activeFilters.author.trim() || null,
          venue: activeFilters.venue.trim() || null,
        },
        {
          onStep: (step, stepStatus) => isCurrent() && setResearchSteps((current) => ({ ...current, [step]: stepStatus })),
          onPapers: (event) => {
            if (!isCurrent()) return;
            setPapers(asArray(event.papers).map(normalizePaper).filter((paper) => paper.title));
            setTotalResults(Number(event.total || 0));
            setUnderstanding(event.query_understanding || null);
            setRetryIds(asArray(event.translation_retry_ids));
            gotPapers = event.papers?.length > 0;
            setStatus("done");
          },
          onAnswer: (answer) => {
            answered = true;
            if (isCurrent()) setResearchAnswer(answer);
          },
          onAnswerError: () => isCurrent() && setResearchAnswerFailed(true),
        },
        controller.signal,
      );
      if (!isCurrent()) return;
      setStatus((current) => (current === "loading" ? "done" : current));
      if (gotPapers && !answered) setResearchAnswerFailed(true);
      void loadHistory();
      void fetchUsage().then(setUsage);
    } catch (error) {
      if ((error as Error)?.name === "AbortError" || !isCurrent()) return;
      if (error instanceof CreditLimitError) {
        // Papers are still shown; only the AI answer is held back until the window resets.
        setLimitNotice(error.limit);
        setStatus((current) => (current === "loading" ? "done" : current));
        void fetchUsage().then(setUsage);
        return;
      }
      setStatus((current) => (current === "done" ? current : "error"));
      setResearchAnswerFailed(true);
    } finally {
      if (isCurrent()) setResearchLoading(false);
    }
  }, [filters, language, loadHistory, setSearchParams, showToast, t]);

  const execute = useCallback((options: RunOptions) => {
    const target = options.mode || mode;
    return target === "research" && !options.append ? runResearch(options) : runSearch(options);
  }, [mode, runResearch, runSearch]);

  /* Auto-detect the user's language from what they type, switch the whole page, then search. */
  const searchWithLanguageDetection = useCallback((rawQuery: string, extra?: Partial<RunOptions>) => {
    const searchQuery = rawQuery.trim();
    let nextLanguage = language;
    if (!languagePinned) {
      const detected = resolveSelectableLanguage(detectQueryLanguage(searchQuery));
      if (detected && detected !== language) {
        setLanguageToast({ previous: language });
        setLanguage(detected);
        onLanguageChange?.(detected, "auto");
        nextLanguage = detected;
      }
    }
    void execute({ query: searchQuery, language: nextLanguage, ...extra });
    // A pasted DOI or arXiv id opens that exact paper while the normal results load underneath.
    if (looksLikeIdentifier(searchQuery)) {
      showToast(t("openingPaper"));
      void resolveIdentifier<SearchPaper>(searchQuery, nextLanguage)
        .then((paper) => {
          if (paper) setQuickView(normalizePaper(paper));
        })
        .catch(() => undefined);
    }
  }, [execute, language, languagePinned, onLanguageChange, showToast, t]);

  // Respond to ?q= (e.g. a search started from Home, or browser back/forward).
  useEffect(() => {
    const urlQuery = searchParams.get("q")?.trim() || "";
    if (urlQuery && urlQuery !== lastUrlQueryRef.current) {
      lastUrlQueryRef.current = urlQuery;
      const urlMode: SearchMode = searchParams.get("mode") === "research" ? "research" : "search";
      setMode(urlMode);
      setQuery(urlQuery);
      searchWithLanguageDetection(urlQuery, { mode: urlMode });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Poll background translation retries and patch results when they complete.
  const retryKey = retryIds.join(":");
  useEffect(() => {
    if (!retryKey) return;
    const pendingIds = new Set(retryKey.split(":"));
    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      await Promise.all([...pendingIds].map(async (id) => {
        try {
          const res = await fetch(`${apiBaseUrl}/search/translation/retries/${encodeURIComponent(id)}`);
          if (!res.ok) return;
          const job = (await res.json()) as { status?: string; paper_id?: string; translated_title?: string | null; translated_abstract?: string | null };
          if (job.status === "completed" && job.paper_id) {
            pendingIds.delete(id);
            setPapers((current) => current.map((paper) => (paper.paper_id === job.paper_id
              ? { ...paper, translated_title: job.translated_title ? plainText(job.translated_title) : paper.translated_title, translated_abstract: job.translated_abstract ?? paper.translated_abstract, translation_status: "translated" }
              : paper)));
          } else if (job.status === "failed") {
            pendingIds.delete(id);
          }
        } catch {
          /* worker starting — keep polling */
        }
      }));
      if (!pendingIds.size || attempts > 40) window.clearInterval(interval);
    };
    const interval = window.setInterval(() => void poll(), 2000);
    void poll();
    return () => window.clearInterval(interval);
  }, [retryKey]);

  // "Still finding more results…" after a few seconds of loading.
  useEffect(() => {
    if (status !== "loading") {
      setSlowSearch(false);
      return;
    }
    const slowTimer = window.setTimeout(() => setSlowSearch(true), SLOW_SEARCH_MS);
    return () => window.clearTimeout(slowTimer);
  }, [status]);

  // "/" focuses the search bar.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      if (target && (target.isContentEditable || /^(input|textarea|select)$/i.test(target.tagName))) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Hide the language toast after a few seconds.
  useEffect(() => {
    if (!languageToast) return;
    const timer = window.setTimeout(() => setLanguageToast(null), 7000);
    return () => window.clearTimeout(timer);
  }, [languageToast]);

  /* ---------- handlers ---------- */
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (!value) {
      inputRef.current?.focus();
      return;
    }
    setOpenMenu(null);
    searchWithLanguageDetection(value);
  }

  function rerunIfActive(next: Partial<RunOptions>) {
    if (submittedQuery) void execute({ query: submittedQuery, ...next });
  }

  function chooseLanguage(code: string) {
    setLanguage(code);
    setLanguagePinned(true);
    writeStorage(LANGUAGE_SOURCE_KEY, "settings");
    onLanguageChange?.(code, "settings");
    setLanguageToast(null);
    setOpenMenu(null);
    rerunIfActive({ language: code });
  }

  function chooseAutoLanguage() {
    setLanguagePinned(false);
    writeStorage(LANGUAGE_SOURCE_KEY, "auto");
    setOpenMenu(null);
    const detected = resolveSelectableLanguage(detectQueryLanguage(submittedQuery || query));
    if (detected && detected !== language) {
      setLanguage(detected);
      onLanguageChange?.(detected, "auto");
      rerunIfActive({ language: detected });
    }
  }

  function keepPreviousLanguage() {
    if (!languageToast) return;
    const previous = languageToast.previous;
    setLanguageToast(null);
    setLanguage(previous);
    setLanguagePinned(true);
    writeStorage(LANGUAGE_SOURCE_KEY, "settings");
    onLanguageChange?.(previous, "settings");
    rerunIfActive({ language: previous });
  }

  function updateFilters(next: Partial<Filters>) {
    const merged = { ...filters, ...next };
    setFilters(merged);
    rerunIfActive({ filters: merged });
  }

  function setYear(from: string, to = "") {
    setOpenMenu(null);
    updateFilters({ yearFrom: from, yearTo: to });
  }

  function openMoreFilters() {
    setDraftFilters(filters);
    toggleMenu("filters");
  }

  function applyMoreFilters() {
    const merged = {
      ...filters,
      studyType: draftFilters.studyType,
      paperLanguage: draftFilters.paperLanguage,
      minCitations: draftFilters.minCitations,
      author: draftFilters.author,
      venue: draftFilters.venue,
      hasCode: draftFilters.hasCode,
      hasDataset: draftFilters.hasDataset,
      preprintOnly: draftFilters.preprintOnly,
      includeRetracted: draftFilters.includeRetracted,
    };
    setFilters(merged);
    setOpenMenu(null);
    rerunIfActive({ filters: merged });
  }

  function clearAllFilters() {
    setFilters(emptyFilters);
    setDraftFilters(emptyFilters);
    setOpenMenu(null);
    rerunIfActive({ filters: emptyFilters });
  }

  function changeSort(next: SortMode) {
    setOpenMenu(null);
    if (next === sort) return;
    setSort(next);
    rerunIfActive({ sort: next });
  }

  function changeMode(next: SearchMode) {
    if (next === mode) return;
    setMode(next);
    rerunIfActive({ mode: next });
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  function showMore() {
    if (!submittedQuery || loadingMore) return;
    void runSearch({ query: submittedQuery, page: page + 1, append: true });
  }

  function clearQuery() {
    setQuery("");
    inputRef.current?.focus();
  }

  async function saveCurrentSearch(name: string, cadence: "off" | "daily" | "weekly") {
    if (!submittedQuery) return;
    setOpenMenu(null);
    try {
      const res = await fetch(`${apiBaseUrl}/search/saved`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: (name.trim() || submittedQuery).slice(0, 120),
          query: submittedQuery,
          sources: enabledSourceIds,
          filters: {
            language,
            min_citations: Number(filters.minCitations) || 0,
            open_access_only: filters.openAccess,
            peer_reviewed_only: filters.peerReviewed,
            study_type: filters.studyType || null,
            paper_language: filters.paperLanguage || null,
            year_from: filters.yearFrom ? Number(filters.yearFrom) : null,
            year_to: filters.yearTo ? Number(filters.yearTo) : null,
            author: filters.author.trim() || null,
            venue: filters.venue.trim() || null,
            preprint_only: filters.preprintOnly,
            include_retracted: filters.includeRetracted,
          },
          alert_enabled: cadence !== "off",
          alert_cadence: cadence === "off" ? "weekly" : cadence,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      showToast(cadence === "daily" ? t("searchSavedDaily") : cadence === "weekly" ? t("searchSavedWeekly") : t("searchSaved"));
      void loadSavedSearches();
    } catch {
      showToast(t("saveSearchFailed"));
    }
  }

  // Mark results that are already in the Library (one request per new batch of results; failures are silent).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const fresh = papers.filter((paper) => paper.paper_id && !lookedUp.current.has(paper.paper_id) && !isWeb(paper)).slice(0, 200);
      if (!fresh.length) return;
      fresh.forEach((paper) => lookedUp.current.add(paper.paper_id));
      libraryApi.lookup(fresh.map((paper) => paperInputFrom(paperHandoff(paper))))
        .then(({ item_ids }) => {
          const saved = fresh.filter((_, index) => item_ids[index]).map((paper) => paper.paper_id);
          if (saved.length) setSavedIds((ids) => [...new Set([...ids, ...saved])]);
        })
        .catch(() => undefined);
    }, 400);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [papers]);

  async function savePaper(paper: SearchPaper) {
    if (savedIds.includes(paper.paper_id)) return;
    setSavedIds((ids) => [...ids, paper.paper_id]); // optimistic
    try {
      await libraryApi.save([paperInputFrom(paperHandoff(paper))], { source: "search" });
      showToast(t("savedToLibrary"));
    } catch {
      setSavedIds((ids) => ids.filter((id) => id !== paper.paper_id));
      showToast(t("saveFailed"));
    }
  }

  async function copyCitation(paper: SearchPaper, format: "apa" | "bibtex") {
    setOpenMenu(null);
    const text = format === "apa" ? apaCitation(paper) : bibtexCitation(paper);
    try {
      await navigator.clipboard.writeText(text);
      showToast(t("citationCopied"));
    } catch {
      downloadText(text, format === "apa" ? "citation.txt" : "citation.bib");
    }
  }

  function exportResults(format: "csv" | "bibtex") {
    setOpenMenu(null);
    if (!visiblePapers.length) return;
    if (format === "csv") {
      const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
      const rows = visiblePapers.map((paper) => [
        plainText(paper.title), authorNames(paper).join("; "), displayYear(paper.year) || "", paper.venue || "",
        paper.citation_count, paper.doi || "", paper.url || pdfLink(paper) || "",
      ].map(escape).join(","));
      downloadText(["title,authors,year,venue,citations,doi,url", ...rows].join("\n"), "resora-search-results.csv", "text/csv");
    } else {
      downloadText(visiblePapers.map((paper, index) => bibtexCitation(paper, index + 1)).join("\n\n"), "resora-search-results.bib");
    }
    showToast(t("exportDone"));
  }

  async function changeSavedAlert(item: SavedSearch, cadence: "off" | "daily" | "weekly") {
    const changes = cadence === "off" ? { alert_enabled: false } : { alert_enabled: true, alert_cadence: cadence };
    setSavedSearches((items) => items.map((entry) => (entry.id === item.id ? { ...entry, ...changes } : entry)));
    try {
      await updateSavedSearch(item.id, changes);
      showToast(t("savedUpdated"));
    } catch {
      showToast(t("savedUpdateFailed"));
      void loadSavedSearches();
    }
  }

  async function removeSaved(item: SavedSearch) {
    setSavedSearches((items) => items.filter((entry) => entry.id !== item.id));
    try {
      await deleteSavedSearch(item.id);
      showToast(t("savedDeleted"));
    } catch {
      showToast(t("savedUpdateFailed"));
      void loadSavedSearches();
    }
  }

  async function askResults(question: string) {
    const context = visiblePapers.slice(0, 15).map((paper) => ({
      paper_id: paper.paper_id,
      title: paper.title,
      abstract: plainText(paper.abstract || paper.micro_summary || "").slice(0, 1500) || null,
      year: displayYear(paper.year),
      venue: paper.venue || null,
    }));
    if (!context.length) return;
    setAskLoading(true);
    try {
      setAskAnswer(await askAboutResults({ question, language, papers: context }));
      void fetchUsage().then(setUsage);
    } catch (error) {
      if (error instanceof CreditLimitError) {
        showToast(limitMessage(error.limit, language, t));
        void fetchUsage().then(setUsage);
        return;
      }
      showToast(t("askFailed"));
    } finally {
      setAskLoading(false);
    }
  }

  function openPaperById(paperId: string) {
    const paper = papers.find((item) => item.paper_id === paperId);
    if (paper) setQuickView(paper);
  }

  /** Compare adds the paper to the Compare tray (or removes it); the tray bar opens the Compare page. */
  function openCompare(paper: SearchPaper) {
    setOpenMenu(null);
    const result = toggleTray({ ...paperHandoff(paper), key: handoffKey(paper) });
    showToast(result === "added" ? t("compareAdded") : result === "removed" ? t("compareRemoved") : t("compareTrayFull"));
  }

  /** Summarize and Read paper both open the Reader tab, with this paper's public metadata handed over. */
  function handoffKey(paper: SearchPaper) {
    return paper.paper_id || dedupeKey(paper);
  }

  function paperHandoff(paper: SearchPaper) {
    return {
      paper_id: paper.paper_id,
      title: plainText(paper.title),
      abstract: plainText(paper.abstract || "") || null,
      authors: authorNames(paper),
      year: displayYear(paper.year),
      venue: paper.venue || null,
      doi: paper.doi || null,
      url: paper.url || null,
      pdf_url: pdfLink(paper),
      is_open_access: Boolean(paper.is_open_access),
      citation_count: paper.citation_count || 0,
    };
  }

  function openInReader(paper: SearchPaper, tab: "summary" | "read") {
    setOpenMenu(null);
    const key = handoffKey(paper);
    storeHandoff(key, paperHandoff(paper));
    const params = new URLSearchParams({ paper: key, tab: "summary" });
    if (tab === "summary") params.set("auto", "1"); // "Summarize" starts the summary right away
    navigate(`/reader?${params.toString()}`);
  }

  function openSummary(paper: SearchPaper) {
    openInReader(paper, "summary");
  }

  function readPaper(paper: SearchPaper) {
    if (isWeb(paper)) openExternal(paper);
    else openInReader(paper, "read");
  }

  function openExternal(paper: SearchPaper) {
    const href = pdfLink(paper) || paper.url || doiUrl(paper);
    if (!href) {
      showToast(t("noLink"));
      return;
    }
    window.open(href, "_blank", "noopener,noreferrer");
  }

  function startVoiceSearch() {
    const speechWindow = window as SpeechWindow;
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      showToast(t("voiceUnavailable"));
      return;
    }
    const recognition = new Recognition();
    recognition.lang = speechLocales[language] || language || navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim() || "";
      if (!transcript) return;
      setQuery(transcript);
      searchWithLanguageDetection(transcript, { queryType: "voice", voiceTranscript: transcript });
    };
    recognition.start();
  }

  /* ---------- derived ---------- */
  const visiblePapers = useMemo(() => papers.filter((paper) => {
    if (filters.hasCode && !paper.code_repositories.length) return false;
    if (filters.hasDataset && !paper.datasets.length) return false;
    return true;
  }), [filters.hasCode, filters.hasDataset, papers]);

  const hasQuery = status !== "idle";
  const isLoading = status === "loading";
  const busy = isLoading || researchLoading;
  const tLoose = t as unknown as Translate;
  const sessionWindow = usage?.windows.find((window) => window.scope === "session");
  const usageWarning = sessionWindow && sessionWindow.limit > 0 && sessionWindow.percent >= 0.8 && sessionWindow.percent < 1
    ? t("usageNearLimit", { percent: Math.round(sessionWindow.percent * 100), time: formatTime(sessionWindow.resets_at, language) })
    : "";
  const exhausted = usage?.windows.find((window) => window.limit > 0 && window.remaining <= 0);
  const creditHint = mode === "research" && estimate
    ? (estimate.research_credits === 1 ? t("creditsEstimateOne") : t("creditsEstimate", { count: estimate.research_credits }))
    : "";
  const chipParts = understanding && status === "done"
    ? [
        understanding.year_from ? t("chipSince", { year: understanding.year_from }) : "",
        understanding.open_access_only ? t("chipOpenAccess") : "",
        understanding.author ? t("chipBy", { author: understanding.author }) : "",
        understanding.reviews_only ? t("chipReviews") : "",
      ].filter(Boolean)
    : [];
  const showQueryChip = Boolean(
    understanding?.query
    && (chipParts.length || understanding.query.trim().toLowerCase() !== submittedQuery.trim().toLowerCase()),
  );
  const moreFilterCount = countActiveMoreFilters(filters);
  const anyFilterActive = moreFilterCount > 0 || Boolean(filters.yearFrom || filters.yearTo || filters.openAccess || filters.peerReviewed);
  const translationsPending = translating && papers.some((paper) => paper.translation_status === "unavailable" || paper.translation_status === "pending");
  const resultCount = Math.max(totalResults, visiblePapers.length);

  const yearLabel = filters.yearFrom && filters.yearTo
    ? t("yearRange", { from: filters.yearFrom, to: filters.yearTo })
    : filters.yearFrom
      ? t("sinceYear", { year: filters.yearFrom })
      : filters.yearTo
        ? t("untilYear", { year: filters.yearTo })
        : "";

  const sortLabels: Record<SortMode, string> = { relevance: t("sortMostRelevant"), citations: t("mostCited"), year: t("resultSortNewest") };

  /* ---------- render pieces ---------- */
  const modeSwitch = (
    <div className="rs-segmented" role="radiogroup" aria-label={t("modeLabel")}>
      {(["search", "research"] as const).map((value) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={mode === value}
          className={mode === value ? "is-active" : ""}
          onClick={() => changeMode(value)}
        >
          {value === "search" ? t("searchTab") : t("researchWithResora")}
        </button>
      ))}
    </div>
  );

  const languageControl = (
    <LanguageMenu
      open={openMenu === "language"}
      onToggle={() => toggleMenu("language")}
      onClose={closeMenu}
      language={language}
      pinned={languagePinned}
      showOriginal={showOriginal}
      onShowOriginal={setShowOriginal}
      onChoose={chooseLanguage}
      onAuto={chooseAutoLanguage}
      t={t}
    />
  );

  const searchBar = (
    <form className={`rs-bar${busy ? " is-loading" : ""}`} role="search" onSubmit={handleSubmit}>
      <span className="rs-bar-icon" aria-hidden="true"><SearchGlyph /></span>
      <input
        ref={inputRef}
        name="search-query"
        type="search"
        className="rs-bar-input"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={mode === "research" ? t("researchPlaceholder") : t("placeholder")}
        aria-label={mode === "research" ? t("researchPlaceholder") : t("placeholder")}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="search"
        dir="auto"
      />
      {query ? (
        <button type="button" className="rs-icon-button" onClick={clearQuery} aria-label={t("clearQuery")} title={t("clearQuery")}>
          <CloseGlyph />
        </button>
      ) : null}
      {voiceSupported ? (
        <button
          type="button"
          className={`rs-icon-button${listening ? " is-live" : ""}`}
          onClick={startVoiceSearch}
          disabled={listening}
          aria-label={listening ? t("listening") : t("searchByVoice")}
          title={listening ? t("listening") : t("searchByVoice")}
        >
          <MicGlyph />
        </button>
      ) : null}
      <button type="submit" className="rs-bar-submit" disabled={busy} aria-busy={busy}>
        {busy ? <span className="rs-spinner" aria-hidden="true" /> : null}
        <span>{busy ? t("searching") : mode === "research" ? t("researchButton") : t("searchTab")}</span>
      </button>
      {busy ? <span className="rs-progress" aria-hidden="true" /> : null}
    </form>
  );

  /* ---------- render ---------- */
  return (
    <section className={`rs-search${hasQuery ? " has-query" : " is-empty"}`} dir={direction} lang={language} data-no-translate="">
      {!hasQuery ? (
        <div className="rs-col rs-hero">
          <div className="rs-hero-glow" aria-hidden="true" />
          <h1 className="rs-hero-title">{t("findResearch")}</h1>
          <p className="rs-hero-subtitle">{mode === "research" ? t("researchSubtitle") : t("searchSubtitle")}</p>
          {searchBar}
          {creditHint ? <p className="rs-credit-hint">{creditHint}</p> : null}
          {mode === "research" && (exhausted || usageWarning) ? (
            <p className="rs-usage-note" role="status">{exhausted ? limitMessage({ scope: exhausted.scope, resets_at: exhausted.resets_at }, language, t) : usageWarning}</p>
          ) : null}
          <div className="rs-hero-controls">
            {modeSwitch}
            {languageControl}
          </div>
          <div className="rs-examples">
            <span className="rs-examples-label">{t("trySearch")}</span>
            {[t("exampleClimate"), t("exampleMedical"), t("exampleDoi")].map((example) => (
              <button key={example} type="button" className="rs-chip" onClick={() => { setQuery(example); searchWithLanguageDetection(example); }}>
                <bdi>{example}</bdi>
              </button>
            ))}
          </div>
          <SearchShelf
            recent={recentSearches}
            saved={savedSearches}
            onRun={(value) => { setQuery(value); searchWithLanguageDetection(value); }}
            onCadence={(item, cadence) => void changeSavedAlert(item, cadence)}
            onDelete={(item) => void removeSaved(item)}
            t={t}
          />
        </div>
      ) : (
        <div className="rs-col rs-top">
          <div className="rs-top-row">
            {modeSwitch}
            {languageControl}
          </div>
          {searchBar}
          {creditHint ? <p className="rs-credit-hint rs-credit-hint-start">{creditHint}</p> : null}
          {mode === "research" && usageWarning && !limitNotice ? <p className="rs-usage-note rs-credit-hint-start" role="status">{usageWarning}</p> : null}
          <div className="rs-filters">
            <div className="rs-filter-group">
              <YearMenu
                open={openMenu === "year"}
                onToggle={() => toggleMenu("year")}
                onClose={closeMenu}
                label={yearLabel}
                filters={filters}
                onPick={setYear}
                onClear={() => setYear("", "")}
                t={t}
              />
              <button type="button" className={`rs-pill${filters.openAccess ? " is-active" : ""}`} aria-pressed={filters.openAccess} onClick={() => updateFilters({ openAccess: !filters.openAccess })}>
                {filters.openAccess ? <CheckGlyph /> : null}{t("openAccess")}
              </button>
              <button type="button" className={`rs-pill${filters.peerReviewed ? " is-active" : ""}`} aria-pressed={filters.peerReviewed} onClick={() => updateFilters({ peerReviewed: !filters.peerReviewed })}>
                {filters.peerReviewed ? <CheckGlyph /> : null}{t("peerReviewedBadge")}
              </button>
              <MoreFilters
                open={openMenu === "filters"}
                onToggle={openMoreFilters}
                onClose={closeMenu}
                count={moreFilterCount}
                draft={draftFilters}
                setDraft={setDraftFilters}
                onApply={applyMoreFilters}
                onClearAll={clearAllFilters}
                t={t}
              />
            </div>
            <SaveSearchMenu
              open={openMenu === "save"}
              onToggle={() => toggleMenu("save")}
              onClose={closeMenu}
              defaultName={submittedQuery}
              disabled={!submittedQuery}
              onSave={(name, cadence) => void saveCurrentSearch(name, cadence)}
              t={t}
            />
          </div>
        </div>
      )}

      {languageToast ? (
        <div className="rs-language-toast" role="status">
          <span>{t("switchedTo", { language: languageName(language) })}</span>
          <button type="button" onClick={keepPreviousLanguage}>{t("keepLanguage", { language: languageName(languageToast.previous) })}</button>
          <button type="button" className="rs-icon-button rs-icon-small" onClick={() => setLanguageToast(null)} aria-label={t("close")}><CloseGlyph /></button>
        </div>
      ) : null}

      {hasQuery ? (
        <div className="rs-col rs-results" role="region" aria-label={t("searchTab")} aria-live="polite" aria-busy={busy}>
          {showQueryChip && understanding?.query ? (
            <div className="rs-query-chip">
              <span className="rs-muted">{t("searchingFor")}</span>
              <bdi className="rs-query-chip-text">{[understanding.query, ...chipParts].join(" · ")}</bdi>
              <button
                type="button"
                className="rs-text-button rs-text-button-small"
                onClick={() => { setQuery(understanding.query || submittedQuery); inputRef.current?.focus(); }}
              >
                <PencilGlyph />{t("editQuery")}
              </button>
            </div>
          ) : null}

          {mode === "research" && limitNotice ? (
            <div className="rs-limit" role="status">
              <span className="rs-limit-icon" aria-hidden="true"><ClockGlyph /></span>
              <p>{limitMessage(limitNotice, language, t)}</p>
            </div>
          ) : null}

          {mode === "research" && !limitNotice && (researchLoading || researchAnswer || researchAnswerFailed) && status !== "error" ? (
            <div className="rs-research">
              {researchLoading && !researchAnswer ? <ResearchSteps steps={researchSteps} t={tLoose} /> : null}
              {researchAnswer ? (
                <AnswerCard answer={researchAnswer} papers={papers} onOpenPaper={openPaperById} title={t("researchOverview")} t={tLoose} />
              ) : researchAnswerFailed && status === "done" ? (
                <p className="rs-quiet-line">{t("answerUnavailable")}</p>
              ) : researchLoading && status === "done" ? (
                <AnswerSkeleton label={t("stepAnswer")} />
              ) : null}
            </div>
          ) : null}

          {mode === "search" && status === "done" && (entities.researchers.length || entities.institutions.length) ? (
            <nav className="rs-entities" aria-label={t("entitiesLabel")}>
              {[...entities.researchers, ...entities.institutions].map((entity) => (
                <Link
                  key={`${entity.kind}:${entity.id}`}
                  className="rs-entity"
                  to={`/${entity.kind === "researcher" ? "researchers" : "institutions"}/${encodeURIComponent(entity.id)}`}
                >
                  <span className={`rs-entity-avatar${entity.kind === "institution" ? " is-institution" : ""}`} aria-hidden="true">
                    {entity.kind === "institution" ? <BuildingGlyph /> : initials(entity.name)}
                  </span>
                  <span className="rs-entity-text">
                    <bdi className="rs-entity-name">{entity.name}</bdi>
                    <span className="rs-entity-sub">
                      {[entity.kind === "researcher" ? t("profileResearcher") : t("profileInstitution"), entity.subtitle, entity.works_count ? t("worksCount", { count: formatNumber(entity.works_count, language) }) : ""].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </Link>
              ))}
            </nav>
          ) : null}

          {status === "done" && visiblePapers.length ? (
            <div className="rs-results-head">
              <p className="rs-count">
                {mode === "research" ? <>{t("papersHeading")} <span className="rs-muted">· </span></> : null}
                {t("aboutResults", {
                  count: formatNumber(resultCount, language),
                  unit: pluralIsOne(resultCount, language) ? t("resultSingular") : t("resultPlural"),
                })}
              </p>
              <div className="rs-results-actions">
                <Dropdown
                  id="export"
                  open={openMenu === "export"}
                  onToggle={() => toggleMenu("export")}
                  onClose={closeMenu}
                  trigger={<>{t("exportLabel")}<ChevronGlyph /></>}
                  triggerClassName="rs-text-button"
                  align="end"
                >
                  <button type="button" role="menuitem" className="rs-menu-item" onClick={() => exportResults("csv")}>{t("exportCsv")}</button>
                  <button type="button" role="menuitem" className="rs-menu-item" onClick={() => exportResults("bibtex")}>{t("exportBibtex")}</button>
                </Dropdown>
                {mode === "search" ? <Dropdown
                  id="sort"
                  open={openMenu === "sort"}
                  onToggle={() => toggleMenu("sort")}
                  onClose={closeMenu}
                  trigger={<><span className="rs-muted">{t("sortBy")}:</span> {sortLabels[sort]}<ChevronGlyph /></>}
                  triggerClassName="rs-pill rs-pill-compact"
                  align="end"
                >
                  {(Object.keys(sortLabels) as SortMode[]).map((value) => (
                    <button key={value} type="button" role="menuitemradio" aria-checked={sort === value} className={`rs-menu-item${sort === value ? " is-selected" : ""}`} onClick={() => changeSort(value)}>
                      <span>{sortLabels[value]}</span>{sort === value ? <CheckGlyph /> : null}
                    </button>
                  ))}
                </Dropdown> : null}
              </div>
            </div>
          ) : null}

          {translationsPending && status === "done" ? <p className="rs-quiet-line">{t("translationRetrying")}</p> : null}

          {status === "error" ? (
            <StateMessage
              icon={<CloudGlyph />}
              title={t("errorTitle")}
              text={t("errorHint")}
              action={<button type="button" className="rs-button rs-button-primary" onClick={() => void execute({ query: submittedQuery })}>{t("retry")}</button>}
            />
          ) : status === "done" && !visiblePapers.length ? (
            <StateMessage
              icon={<SearchGlyph />}
              title={t("noResultsTitle")}
              text={t("noResultsHint")}
              action={
                <div className="rs-state-actions">
                  {anyFilterActive ? <button type="button" className="rs-button rs-button-outline" onClick={clearAllFilters}>{t("clearFilters")}</button> : null}
                  {suggestions.length ? (
                    <div className="rs-examples">
                      <span className="rs-examples-label">{t("relatedSearches")}</span>
                      {suggestions.map((item) => (
                        <button key={item} type="button" className="rs-chip" onClick={() => { setQuery(item); searchWithLanguageDetection(item); }}><bdi>{item}</bdi></button>
                      ))}
                    </div>
                  ) : null}
                </div>
              }
            />
          ) : (
            <div className="rs-list">
              {visiblePapers.map((paper) => (
                <ResultCard
                  key={paper.paper_id}
                  paper={paper}
                  language={language}
                  translating={translating}
                  saved={savedIds.includes(paper.paper_id)}
                  openMenu={openMenu}
                  onToggleMenu={toggleMenu}
                  onCloseMenu={closeMenu}
                  onSave={() => void savePaper(paper)}
                  onCite={(format) => void copyCitation(paper, format)}
                  onCompare={() => openCompare(paper)}
                  inCompare={trayKeys.has(handoffKey(paper))}
                  onSummarize={() => openSummary(paper)}
                  onRead={() => readPaper(paper)}
                  onDetails={() => { setOpenMenu(null); setQuickView(paper); }}
                  t={t}
                />
              ))}
              {isLoading ? <SkeletonList count={visiblePapers.length ? 2 : mode === "research" ? 3 : 5} label={t("searching")} /> : null}
              {loadingMore ? <SkeletonList count={3} label={t("searching")} /> : null}
            </div>
          )}

          {isLoading && slowSearch ? <p className="rs-quiet-line rs-center">{t("stillFinding")}</p> : null}

          {status === "done" && visiblePapers.length && loadMoreFailed ? (
            <div className="rs-inline-error" role="alert">
              <span>{t("loadMoreFailed")}</span>
              <button type="button" className="rs-text-button" onClick={showMore}>{t("retry")}</button>
            </div>
          ) : null}

          {mode === "search" && status === "done" && visiblePapers.length && hasNextPage && !loadingMore && !loadMoreFailed ? (
            <div className="rs-center">
              <button type="button" className="rs-button rs-button-outline rs-show-more" onClick={showMore}>{t("showMoreResults")}</button>
            </div>
          ) : null}

          {mode === "research" && status === "done" && visiblePapers.length && !researchLoading ? (
            <div className="rs-center">
              <button type="button" className="rs-button rs-button-outline rs-show-more" onClick={() => changeMode("search")}>{t("seeAllResults")}</button>
            </div>
          ) : null}

          {mode === "search" && status === "done" && visiblePapers.length ? (
            <div className="rs-ask-zone">
              {askAnswer ? (
                <AnswerCard answer={askAnswer} papers={papers} onOpenPaper={openPaperById} onClose={() => setAskAnswer(null)} title={t("askAnswerTitle")} t={tLoose} />
              ) : null}
              <AskBar onAsk={(question) => void askResults(question)} loading={askLoading} credits={estimate ? estimate.ask_credits : null} t={tLoose} />
            </div>
          ) : null}
        </div>
      ) : null}

      {quickView ? (
        <QuickView
          paper={papers.find((item) => item.paper_id === quickView.paper_id) || quickView}
          language={language}
          translating={translating}
          saved={savedIds.includes(quickView.paper_id)}
          onClose={() => setQuickView(null)}
          onSave={() => void savePaper(quickView)}
          onCopy={async (text) => {
            try {
              await navigator.clipboard.writeText(text);
              showToast(t("citationCopied"));
            } catch {
              showToast(text);
            }
          }}
          onCompare={() => openCompare(quickView)}
          inCompare={trayKeys.has(handoffKey(quickView))}
          onSummarize={() => openSummary(quickView)}
          onRead={() => readPaper(quickView)}
          t={t}
        />
      ) : null}

      <CompareTrayBar t={t} />

      <div className="rs-toast-region" aria-live="polite">
        {toast ? <div className="rs-toast" role="status">{toast}</div> : null}
      </div>
    </section>
  );
}

export default SearchPage;

/* -------------------------------------------------------------------------- */
/*  Components                                                                */
/* -------------------------------------------------------------------------- */

type T = (key: SearchCopyKey, values?: Record<string, string | number>) => string;

function Dropdown({
  id,
  open,
  onToggle,
  onClose,
  trigger,
  triggerClassName,
  triggerLabel,
  align = "start",
  wide = false,
  role = "menu",
  children,
}: {
  id: string;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  trigger: ReactNode;
  triggerClassName: string;
  triggerLabel?: string;
  align?: "start" | "end";
  wide?: boolean;
  role?: "menu" | "dialog";
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  useDismiss(open, [rootRef], onClose);

  useEffect(() => {
    if (!open || !panelRef.current) return;
    const first = panelRef.current.querySelector<HTMLElement>("[aria-checked='true'], input, button");
    first?.focus({ preventScroll: true });
  }, [open]);

  function onPanelKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (role !== "menu" || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = [...(panelRef.current?.querySelectorAll<HTMLElement>("[role^='menuitem']") || [])];
    if (!items.length) return;
    event.preventDefault();
    const index = items.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : event.key === "ArrowDown" ? (index + 1) % items.length : (index - 1 + items.length) % items.length;
    items[next]?.focus();
  }

  return (
    <div className="rs-dropdown" ref={rootRef}>
      <button
        type="button"
        className={triggerClassName}
        aria-haspopup={role === "menu" ? "menu" : "dialog"}
        aria-expanded={open}
        aria-controls={open ? `rs-pop-${id}` : undefined}
        aria-label={triggerLabel}
        onClick={onToggle}
      >
        {trigger}
      </button>
      {open ? (
        <div
          id={`rs-pop-${id}`}
          ref={panelRef}
          role={role}
          className={`rs-popover rs-popover-${align}${wide ? " rs-popover-wide" : ""}`}
          onKeyDown={onPanelKeyDown}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

function LanguageMenu({
  open, onToggle, onClose, language, pinned, showOriginal, onShowOriginal, onChoose, onAuto, t,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  language: string;
  pinned: boolean;
  showOriginal: boolean;
  onShowOriginal: (value: boolean) => void;
  onChoose: (code: string) => void;
  onAuto: () => void;
  t: T;
}) {
  const [filter, setFilter] = useState("");
  useEffect(() => {
    if (!open) setFilter("");
  }, [open]);
  const matches = selectableLanguages.filter((item) => `${item.nativeName} ${item.englishName} ${item.code}`.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <Dropdown
      id="language"
      open={open}
      onToggle={onToggle}
      onClose={onClose}
      triggerClassName="rs-pill rs-language-pill"
      triggerLabel={`${t("languageLabel")}: ${languageName(language)}`}
      trigger={<><GlobeGlyph /><span className="rs-muted">{t("languageLabel")}</span><bdi>{languageName(language)}</bdi><ChevronGlyph /></>}
      align="end"
    >
      <button type="button" role="menuitemradio" aria-checked={!pinned} className={`rs-menu-item${!pinned ? " is-selected" : ""}`} onClick={onAuto}>
        <span>{t("autoLanguage")}</span>{!pinned ? <CheckGlyph /> : null}
      </button>
      <div className="rs-menu-divider" />
      <input
        className="rs-menu-search"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        placeholder={t("languageSearch")}
        aria-label={t("languageSearch")}
        dir="auto"
      />
      <div className="rs-menu-scroll">
        {matches.length ? matches.map((item) => {
          const selected = pinned && item.code === language;
          return (
            <button
              key={item.code}
              type="button"
              role="menuitemradio"
              aria-checked={selected}
              lang={item.code}
              dir={item.direction === "rtl" ? "rtl" : "ltr"}
              className={`rs-menu-item${selected || item.code === language ? " is-selected" : ""}`}
              onClick={() => onChoose(item.code)}
            >
              <span>{item.nativeName}</span>
              {item.code === language ? <CheckGlyph /> : <span className="rs-menu-hint">{item.englishName}</span>}
            </button>
          );
        }) : <p className="rs-menu-empty">{t("noLanguageMatch")}</p>}
      </div>
      {language !== "en" ? (
        <>
          <div className="rs-menu-divider" />
          <label className="rs-switch-row">
            <span>{t("showOriginal")}</span>
            <input type="checkbox" role="switch" checked={showOriginal} onChange={(event) => onShowOriginal(event.target.checked)} />
            <span className="rs-switch" aria-hidden="true" />
          </label>
        </>
      ) : null}
    </Dropdown>
  );
}

function YearMenu({
  open, onToggle, onClose, label, filters, onPick, onClear, t,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  label: string;
  filters: Filters;
  onPick: (from: string, to?: string) => void;
  onClear: () => void;
  t: T;
}) {
  const [from, setFrom] = useState(filters.yearFrom);
  const [to, setTo] = useState(filters.yearTo);
  useEffect(() => {
    if (open) {
      setFrom(filters.yearFrom);
      setTo(filters.yearTo);
    }
  }, [filters.yearFrom, filters.yearTo, open]);

  const fromNumber = Number(from);
  const toNumber = Number(to);
  const invalid = Boolean(
    (from && (fromNumber < 1900 || fromNumber > CURRENT_YEAR)) ||
    (to && (toNumber < 1900 || toNumber > CURRENT_YEAR)) ||
    (from && to && fromNumber > toNumber),
  );
  const quick: Array<[string, string]> = [["", t("anyTime")], ["2025", t("since2025")], ["2022", t("since2022")], ["2015", t("since2015")]];
  const activeQuick = !filters.yearTo ? filters.yearFrom : "__custom";

  return (
    <div className={`rs-pill-split${label ? " is-active" : ""}`}>
      <Dropdown
        id="year"
        open={open}
        onToggle={onToggle}
        onClose={onClose}
        triggerClassName={`rs-pill${label ? " is-active" : ""}`}
        trigger={<>{label ? <bdi>{label}</bdi> : t("yearFilter")}<ChevronGlyph /></>}
      >
        {quick.map(([value, text]) => (
          <button key={value || "any"} type="button" role="menuitemradio" aria-checked={activeQuick === value} className={`rs-menu-item${activeQuick === value ? " is-selected" : ""}`} onClick={() => onPick(value)}>
            <span>{text}</span>{activeQuick === value ? <CheckGlyph /> : null}
          </button>
        ))}
        <div className="rs-menu-divider" />
        <p className="rs-menu-label">{t("customRange")}</p>
        <div className="rs-year-range">
          <label>
            <span>{t("yearFrom")}</span>
            <input type="number" inputMode="numeric" min={1900} max={CURRENT_YEAR} value={from} placeholder="2018" onChange={(event) => setFrom(event.target.value.slice(0, 4))} />
          </label>
          <label>
            <span>{t("yearTo")}</span>
            <input type="number" inputMode="numeric" min={1900} max={CURRENT_YEAR} value={to} placeholder={String(CURRENT_YEAR)} onChange={(event) => setTo(event.target.value.slice(0, 4))} />
          </label>
        </div>
        <div className="rs-menu-footer">
          <button type="button" className="rs-button rs-button-primary rs-button-small" disabled={invalid || (!from && !to)} onClick={() => onPick(from, to)}>{t("applyFilters")}</button>
        </div>
      </Dropdown>
      {label ? (
        <button type="button" className="rs-pill-clear" onClick={onClear} aria-label={`${t("clearFilter")}: ${label}`} title={t("clearFilter")}>
          <CloseGlyph />
        </button>
      ) : null}
    </div>
  );
}

function MoreFilters({
  open, onToggle, onClose, count, draft, setDraft, onApply, onClearAll, t,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  count: number;
  draft: Filters;
  setDraft: (filters: Filters) => void;
  onApply: () => void;
  onClearAll: () => void;
  t: T;
}) {
  const studyTypes: Array<[string, string]> = [
    ["", t("anyStudy")], ["review", t("studyReview")], ["meta_analysis", t("studyMeta")], ["rct", t("studyRct")],
    ["case_study", t("studyCase")], ["experimental", t("studyExperimental")], ["clinical", t("studyClinical")], ["protocol", t("studyProtocol")],
  ];
  const update = (next: Partial<Filters>) => setDraft({ ...draft, ...next });
  const toggles: Array<[keyof Filters, string]> = [["hasCode", t("hasCode")], ["hasDataset", t("hasDataset")], ["preprintOnly", t("preprintsOnly")], ["includeRetracted", t("includeRetracted")]];

  return (
    <Dropdown
      id="filters"
      open={open}
      onToggle={onToggle}
      onClose={onClose}
      role="dialog"
      wide
      triggerClassName={`rs-pill${count ? " is-active" : ""}`}
      trigger={<><SlidersGlyph />{t("moreFilters")}{count ? <span className="rs-count-badge">{count}</span> : null}</>}
    >
      <div className="rs-filter-panel">
        <fieldset className="rs-field">
          <legend>{t("studyLabel")}</legend>
          <div className="rs-chip-row">
            {studyTypes.map(([value, label]) => (
              <button key={value || "any"} type="button" className={`rs-chip${draft.studyType === value ? " is-active" : ""}`} aria-pressed={draft.studyType === value} onClick={() => update({ studyType: value })}>
                {label}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="rs-field-grid">
          <PaperLanguageField value={draft.paperLanguage} onChange={(code) => update({ paperLanguage: code })} t={t} />
          <label className="rs-field">
            <span>{t("minCitations")}</span>
            <input className="rs-input" type="number" inputMode="numeric" min={0} value={draft.minCitations} placeholder="0" onChange={(event) => update({ minCitations: event.target.value })} />
          </label>
          <label className="rs-field">
            <span>{t("authorFilter")}</span>
            <input className="rs-input" value={draft.author} placeholder={t("authorPlaceholder")} onChange={(event) => update({ author: event.target.value })} dir="auto" />
          </label>
          <label className="rs-field">
            <span>{t("venueFilter")}</span>
            <input className="rs-input" value={draft.venue} placeholder={t("venuePlaceholder")} onChange={(event) => update({ venue: event.target.value })} dir="auto" />
          </label>
        </div>

        <div className="rs-toggle-grid">
          {toggles.map(([key, label]) => (
            <label key={key} className="rs-switch-row">
              <span>{label}</span>
              <input type="checkbox" role="switch" checked={Boolean(draft[key])} onChange={(event) => update({ [key]: event.target.checked } as Partial<Filters>)} />
              <span className="rs-switch" aria-hidden="true" />
            </label>
          ))}
        </div>
      </div>
      <div className="rs-menu-footer rs-menu-footer-split">
        <button type="button" className="rs-text-button" onClick={onClearAll}>{t("clearAll")}</button>
        <button type="button" className="rs-button rs-button-primary rs-button-small" onClick={onApply}>{t("applyFilters")}</button>
      </div>
    </Dropdown>
  );
}

function formatTime(iso: string, language: string) {
  try {
    return new Intl.DateTimeFormat(language, { hour: "numeric", minute: "2-digit" }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleTimeString();
  }
}

function formatDay(iso: string, language: string) {
  try {
    return new Intl.DateTimeFormat(language, { weekday: "short", month: "short", day: "numeric" }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleDateString();
  }
}

function limitMessage(limit: UsageLimit, language: string, t: T) {
  if (limit.scope === "session") return t("limitReachedSession", { time: formatTime(limit.resets_at, language) });
  if (limit.scope === "week") return t("limitReachedWeek", { date: formatDay(limit.resets_at, language) });
  return t("limitReachedMonth", { date: formatDay(limit.resets_at, language) });
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

function cleanSavedName(item: SavedSearch) {
  const name = (item.name || "").replace(/^\s*search\s*:\s*/i, "").trim();
  return name || item.query;
}

function SearchShelf({
  recent, saved, onRun, onCadence, onDelete, t,
}: {
  recent: string[];
  saved: SavedSearch[];
  onRun: (query: string) => void;
  onCadence: (item: SavedSearch, cadence: "off" | "daily" | "weekly") => void;
  onDelete: (item: SavedSearch) => void;
  t: T;
}) {
  const savedItems = useMemo(() => {
    const seen = new Set<string>();
    return saved.filter((item) => {
      const key = `${cleanSavedName(item).toLowerCase()}|${item.query.trim().toLowerCase()}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [saved]);
  const [tab, setTab] = useState<"recent" | "saved">(recent.length ? "recent" : "saved");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (tab === "recent" && !recent.length && savedItems.length) setTab("saved");
    if (tab === "saved" && !savedItems.length) {
      setEditing(false);
      if (recent.length) setTab("recent");
    }
  }, [recent.length, savedItems.length, tab]);

  if (!recent.length && !savedItems.length) return null;
  const cadences: Array<["off" | "daily" | "weekly", string]> = [["off", t("alertOff")], ["daily", t("alertDaily")], ["weekly", t("alertWeekly")]];
  const showSaved = tab === "saved" && savedItems.length > 0;

  return (
    <section className="rs-shelf" aria-label={showSaved ? t("savedSearchesTitle") : t("recentSearches")}>
      <div className="rs-shelf-head">
        <div className="rs-shelf-tabs" role="tablist">
          {recent.length ? (
            <button type="button" role="tab" aria-selected={!showSaved} className={!showSaved ? "is-active" : ""} onClick={() => { setTab("recent"); setEditing(false); }}>
              {t("recentSearches")}
            </button>
          ) : null}
          {savedItems.length ? (
            <button type="button" role="tab" aria-selected={showSaved} className={showSaved ? "is-active" : ""} onClick={() => setTab("saved")}>
              {t("savedSearches")}<span className="rs-shelf-count">{savedItems.length}</span>
            </button>
          ) : null}
        </div>
        {showSaved ? (
          <button type="button" className="rs-shelf-edit" aria-pressed={editing} onClick={() => setEditing((value) => !value)}>
            {editing ? t("doneEditing") : t("manageSaved")}
          </button>
        ) : null}
      </div>

      <ul className="rs-shelf-list" role="tabpanel">
        {showSaved
          ? savedItems.map((item) => {
              const current = item.alert_enabled ? (item.alert_cadence === "daily" ? "daily" : "weekly") : "off";
              const name = cleanSavedName(item);
              return (
                <li key={item.id} className={editing ? "is-editing" : ""}>
                  <button type="button" className="rs-shelf-row" onClick={() => onRun(item.query)}>
                    <span className="rs-shelf-icon" aria-hidden="true">{item.alert_enabled ? <BellGlyph /> : <BookmarkGlyph />}</span>
                    <span className="rs-shelf-text">
                      <bdi className="rs-shelf-title">{name}</bdi>
                      {name !== item.query ? <bdi className="rs-shelf-sub">{item.query}</bdi> : null}
                    </span>
                    {!editing ? (
                      <span className="rs-shelf-meta">{current === "off" ? null : current === "daily" ? t("alertDaily") : t("alertWeekly")}</span>
                    ) : null}
                    {!editing ? <span className="rs-shelf-arrow" aria-hidden="true"><ArrowGlyph /></span> : null}
                  </button>
                  {editing ? (
                    <div className="rs-shelf-controls">
                      <div className="rs-mini-segmented" role="radiogroup" aria-label={t("alertMe")}>
                        {cadences.map(([value, label]) => (
                          <button key={value} type="button" role="radio" aria-checked={current === value} className={current === value ? "is-active" : ""} onClick={() => onCadence(item, value)}>
                            {label}
                          </button>
                        ))}
                      </div>
                      <button type="button" className="rs-shelf-delete" onClick={() => onDelete(item)}>{t("deleteSaved")}</button>
                    </div>
                  ) : null}
                </li>
              );
            })
          : recent.map((item) => (
              <li key={item}>
                <button type="button" className="rs-shelf-row" onClick={() => onRun(item)}>
                  <span className="rs-shelf-icon" aria-hidden="true"><ClockGlyph /></span>
                  <span className="rs-shelf-text"><bdi className="rs-shelf-title">{item}</bdi></span>
                  <span className="rs-shelf-arrow" aria-hidden="true"><ArrowGlyph /></span>
                </button>
              </li>
            ))}
      </ul>
    </section>
  );
}

function whyReasons(paper: SearchPaper, language: string, t: T): string[] {
  const reasons: string[] = [];
  const terms = asArray(paper.matched_terms);
  if (terms.length) reasons.push(t("whyMatches", { terms: terms.join("”, “") }));
  const year = displayYear(paper.year);
  if (!isWeb(paper)) {
    if (paper.citation_count >= 100) reasons.push(t("whyHighlyCited", { count: formatNumber(paper.citation_count, language) }));
    if (year && year >= CURRENT_YEAR - 2) reasons.push(t("whyRecent", { year }));
    if (paper.is_open_access && pdfLink(paper)) reasons.push(t("whyOpenAccess"));
    if (paper.peer_review_status === "peer_reviewed" && !paper.is_preprint) reasons.push(t("whyPeerReviewed"));
    if (paper.code_repositories.length) reasons.push(t("whyCode"));
  }
  return reasons.length ? reasons : [t("whyRelevant")];
}

function SaveSearchMenu({
  open, onToggle, onClose, defaultName, disabled, onSave, t,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  defaultName: string;
  disabled: boolean;
  onSave: (name: string, cadence: "off" | "daily" | "weekly") => void;
  t: T;
}) {
  const [name, setName] = useState(defaultName);
  const [cadence, setCadence] = useState<"off" | "daily" | "weekly">("weekly");
  useEffect(() => {
    if (open) setName(defaultName);
  }, [defaultName, open]);
  const options: Array<["off" | "daily" | "weekly", string]> = [["off", t("alertOff")], ["daily", t("alertDaily")], ["weekly", t("alertWeekly")]];

  return (
    <Dropdown
      id="save"
      open={open && !disabled}
      onToggle={onToggle}
      onClose={onClose}
      role="dialog"
      align="end"
      triggerClassName="rs-text-button"
      trigger={<><BookmarkGlyph />{t("saveSearch")}</>}
    >
      <form
        className="rs-save-panel"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim().length >= 2) onSave(name, cadence);
        }}
      >
        <p className="rs-menu-label">{t("saveSearchTitle")}</p>
        <label className="rs-field">
          <span>{t("searchName")}</span>
          <input className="rs-input" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} dir="auto" />
        </label>
        <fieldset className="rs-field">
          <legend>{t("alertMe")}</legend>
          <div className="rs-chip-row">
            {options.map(([value, label]) => (
              <button key={value} type="button" className={`rs-chip${cadence === value ? " is-active" : ""}`} aria-pressed={cadence === value} onClick={() => setCadence(value)}>
                {label}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="rs-menu-footer">
          <button type="submit" className="rs-button rs-button-primary rs-button-small" disabled={name.trim().length < 2}>{t("saveButton")}</button>
        </div>
      </form>
    </Dropdown>
  );
}

function PaperLanguageField({ value, onChange, t }: { value: string; onChange: (code: string) => void; t: T }) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState("");
  const listId = "rs-paper-language-list";
  const matches = languages.filter((item) => `${item.nativeName} ${item.englishName}`.toLowerCase().includes(filter.trim().toLowerCase()));
  const current = value ? languageName(value) : t("anyPaperLanguage");

  function pick(code: string) {
    onChange(code);
    setExpanded(false);
    setFilter("");
  }

  return (
    <div className="rs-field">
      <span id="rs-paper-language-label">{t("paperLanguage")}</span>
      <button
        type="button"
        className="rs-input rs-select-button"
        aria-haspopup="listbox"
        aria-expanded={expanded}
        aria-controls={expanded ? listId : undefined}
        aria-labelledby="rs-paper-language-label"
        onClick={() => setExpanded((open) => !open)}
      >
        <bdi>{current}</bdi><ChevronGlyph />
      </button>
      {expanded ? (
        <div className="rs-inline-list">
          <input className="rs-menu-search" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder={t("languageSearch")} aria-label={t("languageSearch")} dir="auto" autoFocus />
          <div id={listId} role="listbox" aria-labelledby="rs-paper-language-label" className="rs-menu-scroll rs-menu-scroll-short">
            <button type="button" role="option" aria-selected={!value} className={`rs-menu-item${!value ? " is-selected" : ""}`} onClick={() => pick("")}>
              <span>{t("anyPaperLanguage")}</span>{!value ? <CheckGlyph /> : null}
            </button>
            {matches.map((item) => (
              <button key={item.code} type="button" role="option" aria-selected={value === item.code} lang={item.code} className={`rs-menu-item${value === item.code ? " is-selected" : ""}`} onClick={() => pick(item.code)}>
                <span>{item.nativeName}</span>{value === item.code ? <CheckGlyph /> : <span className="rs-menu-hint">{item.englishName}</span>}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ResultCard({
  paper, language, translating, saved, openMenu, onToggleMenu, onCloseMenu, onSave, onCite, onCompare, inCompare, onSummarize, onRead, onDetails, t,
}: {
  paper: SearchPaper;
  language: string;
  translating: boolean;
  saved: boolean;
  openMenu: string | null;
  onToggleMenu: (id: string) => void;
  onCloseMenu: () => void;
  onSave: () => void;
  onCite: (format: "apa" | "bibtex") => void;
  onCompare: () => void;
  inCompare: boolean;
  onSummarize: () => void;
  onRead: () => void;
  onDetails: () => void;
  t: T;
}) {
  const web = isWeb(paper);
  const useTranslation = translating && Boolean(paper.translated_title);
  const title = useTranslation ? paper.translated_title! : paper.title;
  const rawSnippet = (translating && paper.translated_abstract) || paper.micro_summary || paper.abstract || "";
  const snippet = cleanSnippet(title, cleanSnippet(paper.title, rawSnippet));
  const names = authorNames(paper);
  const authorsText = names.length > 3 ? `${names.slice(0, 3).join(", ")} ${t("etAl")}` : names.join(", ");
  const year = displayYear(paper.year);
  const meta = web
    ? [hostName(paper.url), t("webArticle"), year].filter(Boolean)
    : [authorsText, paper.venue, year].filter(Boolean);
  const hasPdf = paper.is_open_access && Boolean(pdfLink(paper));
  const textDir = useTranslation ? languageDirection(language) : "auto";

  const badges: Array<{ label: string; tone?: "danger" }> = [];
  if (!web) {
    if (isRetracted(paper)) badges.push({ label: t("retractedBadge"), tone: "danger" });
    if (paper.is_open_access) badges.push({ label: t("openAccess") });
    if (paper.is_preprint) badges.push({ label: t("preprintBadge") });
    else if (paper.peer_review_status === "peer_reviewed") badges.push({ label: t("peerReviewedBadge") });
    if (paper.code_repositories.length) badges.push({ label: t("codeAvailable") });
  }

  function onCardClick(event: ReactMouseEvent<HTMLElement>) {
    if ((event.target as HTMLElement).closest("button, a, input, [role='menu'], [role='dialog']")) return;
    if (window.getSelection()?.toString()) return;
    onDetails();
  }

  const citeId = `cite:${paper.paper_id}`;
  const whyId = `why:${paper.paper_id}`;
  const moreId = `more:${paper.paper_id}`;

  return (
    <article className={`rs-card${web ? " is-web" : ""}${isRetracted(paper) ? " is-flagged" : ""}`} onClick={onCardClick}>
      <div className="rs-card-head">
        <h3 className="rs-card-title" dir={textDir}>
          <button type="button" onClick={onDetails} title={useTranslation ? t("originalTitle", { title: paper.title }) : undefined}>{title}</button>
        </h3>
        {!web && paper.citation_count > 0 ? (
          <span className="rs-card-citations">
            <strong>{formatNumber(paper.citation_count, language)}</strong> {pluralIsOne(paper.citation_count, language) ? t("citationSingular") : t("citations")}
          </span>
        ) : null}
      </div>
      <div className="rs-card-meta-row">
        {meta.length ? <p className="rs-card-meta"><bdi>{meta.join(" · ")}</bdi></p> : null}
        <Dropdown
          id={whyId}
          open={openMenu === whyId}
          onToggle={() => onToggleMenu(whyId)}
          onClose={onCloseMenu}
          role="dialog"
          triggerClassName="rs-why"
          triggerLabel={t("whyThisResult")}
          trigger={<><InfoGlyph />{t("whyShort")}</>}
        >
          <div className="rs-why-panel">
            <p className="rs-menu-label">{t("whyThisResult")}</p>
            <ul>
              {whyReasons(paper, language, t).map((reason) => <li key={reason}><CheckGlyph /><span>{reason}</span></li>)}
            </ul>
          </div>
        </Dropdown>
      </div>
      {snippet ? <p className="rs-card-snippet" dir={textDir}>{snippet}</p> : null}
      <div className="rs-card-foot">
        <div className="rs-badges">
          {badges.slice(0, 3).map((badge) => <span key={badge.label} className={`rs-badge${badge.tone === "danger" ? " is-danger" : ""}`}>{badge.label}</span>)}
          {useTranslation ? <span className="rs-translated" title={t("originalTitle", { title: paper.title })}><TranslateGlyph />{t("translated")}</span> : null}
        </div>
        <div className="rs-card-actions">
          <div className="rs-secondary-actions">
            <button type="button" className={`rs-button rs-button-outline${saved ? " is-saved" : ""}`} aria-pressed={saved} onClick={onSave}>
              {saved ? <CheckGlyph /> : null}{saved ? t("saved") : t("save")}
            </button>
            {!web ? (
              <>
                <Dropdown
                  id={citeId}
                  open={openMenu === citeId}
                  onToggle={() => onToggleMenu(citeId)}
                  onClose={onCloseMenu}
                  triggerClassName="rs-button rs-button-outline"
                  trigger={t("citeAction")}
                  align="end"
                >
                  <button type="button" role="menuitem" className="rs-menu-item" onClick={() => onCite("apa")}>{t("copyApa")}</button>
                  <button type="button" role="menuitem" className="rs-menu-item" onClick={() => onCite("bibtex")}>{t("copyBibtex")}</button>
                </Dropdown>
                <button type="button" className={`rs-button rs-button-outline${inCompare ? " is-on" : ""}`} aria-pressed={inCompare} onClick={onCompare}>{inCompare ? t("compareInTray") : t("compare")}</button>
                <button type="button" className="rs-button rs-button-outline" onClick={onSummarize}>{t("summarizeAction")}</button>
              </>
            ) : null}
          </div>
          {!web ? (
            <div className="rs-mobile-more">
              <Dropdown
                id={moreId}
                open={openMenu === moreId}
                onToggle={() => onToggleMenu(moreId)}
                onClose={onCloseMenu}
                triggerClassName="rs-button rs-button-outline"
                trigger={t("moreActions")}
                align="end"
              >
                <button type="button" role="menuitem" className="rs-menu-item" onClick={() => { onCloseMenu(); onSave(); }}>{saved ? t("saved") : t("save")}</button>
                <button type="button" role="menuitem" className="rs-menu-item" onClick={() => onCite("apa")}>{t("copyApa")}</button>
                <button type="button" role="menuitem" className="rs-menu-item" onClick={() => onCite("bibtex")}>{t("copyBibtex")}</button>
                <button type="button" role="menuitem" className="rs-menu-item" onClick={onCompare}>{inCompare ? t("compareInTray") : t("compare")}</button>
                <button type="button" role="menuitem" className="rs-menu-item" onClick={onSummarize}>{t("summarizeAction")}</button>
              </Dropdown>
            </div>
          ) : null}
          {web ? (
            <button type="button" className="rs-button rs-button-outline" onClick={onRead} disabled={!paper.url}>{t("visitWebsite")}<ExternalGlyph /></button>
          ) : hasPdf ? (
            <button type="button" className="rs-button rs-button-primary" onClick={onRead}>{t("readPaper")}</button>
          ) : (
            <button type="button" className="rs-button rs-button-outline" onClick={onDetails}>{t("viewDetails")}</button>
          )}
        </div>
      </div>
    </article>
  );
}

function QuickView({
  paper, language, translating, saved, onClose, onSave, onCopy, onCompare, inCompare, onSummarize, onRead, t,
}: {
  paper: SearchPaper;
  language: string;
  translating: boolean;
  saved: boolean;
  onClose: () => void;
  onSave: () => void;
  onCopy: (text: string) => void;
  onCompare: () => void;
  inCompare: boolean;
  onSummarize: () => void;
  onRead: () => void;
  t: T;
}) {
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const web = isWeb(paper);
  const useTranslation = translating && Boolean(paper.translated_title);
  const title = useTranslation ? paper.translated_title! : paper.title;
  const abstract = cleanSnippet(paper.title, (translating && paper.translated_abstract) || paper.abstract || paper.micro_summary || "");
  const names = authorNames(paper);
  const year = displayYear(paper.year);
  const doi = doiUrl(paper);
  const citation = apaCitation(paper);
  const textDir = useTranslation ? languageDirection(language) : "auto";
  const hasPdf = paper.is_open_access && Boolean(pdfLink(paper));

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab" && panelRef.current) {
        const focusable = [...panelRef.current.querySelectorAll<HTMLElement>("button, a[href], input, [tabindex]:not([tabindex='-1'])")].filter((el) => !el.hasAttribute("disabled"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = originalOverflow;
      previous?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="rs-drawer-backdrop" onPointerDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={panelRef} className="rs-drawer" role="dialog" aria-modal="true" aria-labelledby="rs-drawer-title">
        <div className="rs-drawer-head">
          <div className="rs-badges">
            {!web && isRetracted(paper) ? <span className="rs-badge is-danger">{t("retractedBadge")}</span> : null}
            {!web && paper.is_open_access ? <span className="rs-badge">{t("openAccess")}</span> : null}
            {!web && paper.is_preprint ? <span className="rs-badge">{t("preprintBadge")}</span> : !web && paper.peer_review_status === "peer_reviewed" ? <span className="rs-badge">{t("peerReviewedBadge")}</span> : null}
          </div>
          <button ref={closeRef} type="button" className="rs-icon-button" onClick={onClose} aria-label={t("close")} title={t("close")}><CloseGlyph /></button>
        </div>

        <div className="rs-drawer-body">
          <h2 id="rs-drawer-title" className="rs-drawer-title" dir={textDir}>{title}</h2>
          {useTranslation ? <p className="rs-drawer-original" dir="auto">{t("originalTitle", { title: paper.title })}</p> : null}
          <p className="rs-card-meta">
            <bdi>{web ? [hostName(paper.url), year].filter(Boolean).join(" · ") : [names.join(", "), year].filter(Boolean).join(" · ")}</bdi>
          </p>
          {!web && (paper.venue || paper.citation_count > 0) ? (
            <dl className="rs-facts">
              {paper.venue ? <div><dt>{t("publishedIn")}</dt><dd><bdi>{paper.venue}</bdi></dd></div> : null}
              {paper.citation_count > 0 ? <div><dt>{t("citationsLabel")}</dt><dd>{formatNumber(paper.citation_count, language)}</dd></div> : null}
              {doi ? <div><dt>{t("doiLabel")}</dt><dd><a href={doi} target="_blank" rel="noopener noreferrer"><bdi>{paper.doi}</bdi></a></dd></div> : null}
            </dl>
          ) : null}

          <section className="rs-drawer-section">
            <h3>{t("abstractLabel")}</h3>
            <p dir={textDir}>{abstract || t("noAbstract")}</p>
          </section>

          {paper.datasets.length || paper.methodologies.length || paper.code_repositories.length ? (
            <section className="rs-drawer-section rs-drawer-grid">
              {paper.datasets.length ? <div><h3>{t("datasetsLabel")}</h3><div className="rs-chip-row">{paper.datasets.slice(0, 8).map((item) => <span key={item} className="rs-tag"><bdi>{item}</bdi></span>)}</div></div> : null}
              {paper.methodologies.length ? <div><h3>{t("methodsLabel")}</h3><div className="rs-chip-row">{paper.methodologies.slice(0, 8).map((item) => <span key={item} className="rs-tag"><bdi>{item}</bdi></span>)}</div></div> : null}
              {paper.code_repositories.length ? (
                <div>
                  <h3>{t("codeLabel")}</h3>
                  <div className="rs-chip-row">
                    {paper.code_repositories.slice(0, 3).map((item) => <a key={item} className="rs-tag rs-tag-link" href={item} target="_blank" rel="noopener noreferrer"><bdi>{hostName(item) || item}</bdi><ExternalGlyph /></a>)}
                  </div>
                </div>
              ) : null}
            </section>
          ) : null}

          {!web ? (
            <section className="rs-drawer-section">
              <h3>{t("citeLabel")}</h3>
              <div className="rs-cite-box">
                <p dir="ltr">{citation}</p>
                <button type="button" className="rs-button rs-button-outline rs-button-small" onClick={() => onCopy(citation)}>{t("copy")}</button>
              </div>
            </section>
          ) : null}
        </div>

        <div className="rs-drawer-foot">
          <button type="button" className={`rs-button rs-button-outline${saved ? " is-saved" : ""}`} aria-pressed={saved} onClick={onSave}>{saved ? <CheckGlyph /> : null}{saved ? t("saved") : t("save")}</button>
          {!web ? <button type="button" className={`rs-button rs-button-outline${inCompare ? " is-on" : ""}`} aria-pressed={inCompare} onClick={onCompare}>{inCompare ? t("compareInTray") : t("compare")}</button> : null}
          {!web ? <button type="button" className="rs-button rs-button-outline" onClick={onSummarize}>{t("summarizeAction")}</button> : null}
          <span className="rs-spacer" />
          {web ? (
            <button type="button" className="rs-button rs-button-primary" onClick={onRead} disabled={!paper.url}>{t("visitWebsite")}<ExternalGlyph /></button>
          ) : (
            <button type="button" className="rs-button rs-button-primary" onClick={onRead} disabled={!hasPdf && !paper.url && !doi}>{t("readPaper")}<ExternalGlyph /></button>
          )}
        </div>
      </div>
    </div>
  );
}

function SkeletonList({ count, label }: { count: number; label: string }) {
  return (
    <div className="rs-skeletons" role="status" aria-label={label} data-testid="search-loading-skeletons">
      {Array.from({ length: count }, (_, index) => (
        <div className="rs-skeleton-card" key={index} aria-hidden="true">
          <div className="rs-skeleton-row"><i className="rs-sk rs-sk-title" /><i className="rs-sk rs-sk-cite" /></div>
          <i className="rs-sk rs-sk-meta" />
          <i className="rs-sk rs-sk-line" />
          <i className="rs-sk rs-sk-line rs-sk-short" />
          <div className="rs-skeleton-row rs-skeleton-foot">
            <span><i className="rs-sk rs-sk-badge" /><i className="rs-sk rs-sk-badge" /></span>
            <span><i className="rs-sk rs-sk-btn" /><i className="rs-sk rs-sk-btn" /><i className="rs-sk rs-sk-btn rs-sk-primary" /></span>
          </div>
        </div>
      ))}
    </div>
  );
}

function StateMessage({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) {
  return (
    <div className="rs-state" role="status">
      <span className="rs-state-icon" aria-hidden="true">{icon}</span>
      <h2>{title}</h2>
      <p>{text}</p>
      {action}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Icons (decorative, inherit currentColor)                                  */
/* -------------------------------------------------------------------------- */

function Svg({ children, size = 16, strokeWidth = 1.9 }: { children: ReactNode; size?: number; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}
function SearchGlyph() { return <Svg size={20} strokeWidth={2}><circle cx="11" cy="11" r="7" /><path d="m20 20-4.2-4.2" /></Svg>; }
function MicGlyph() { return <Svg size={18}><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><path d="M12 19v3" /></Svg>; }
function CloseGlyph() { return <Svg size={16} strokeWidth={2.1}><path d="M6 6l12 12M18 6 6 18" /></Svg>; }
function ChevronGlyph() { return <span className="rs-chevron"><Svg size={14} strokeWidth={2.2}><path d="m6 9 6 6 6-6" /></Svg></span>; }
function CheckGlyph() { return <Svg size={14} strokeWidth={2.4}><path d="m5 12.5 4.5 4.5L19 7.5" /></Svg>; }
function GlobeGlyph() { return <Svg size={15}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></Svg>; }
function BookmarkGlyph() { return <Svg size={15}><path d="M6 4h12v17l-6-4-6 4V4Z" /></Svg>; }
function SlidersGlyph() { return <Svg size={15}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></Svg>; }
function ArrowGlyph() { return <span className="rs-flip-rtl"><Svg size={15} strokeWidth={2}><path d="M5 12h14M13 6l6 6-6 6" /></Svg></span>; }
function ClockGlyph() { return <Svg size={14}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></Svg>; }
function ExternalGlyph() { return <Svg size={14}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>; }
function TranslateGlyph() { return <Svg size={13}><path d="M4 5h8M8 3v2M10 5c-.7 3.6-3 6.5-6 8M6.5 9c1 1.7 2.6 3 4.5 3.8M13 21l4-9 4 9M14.5 18h5" /></Svg>; }
function BellGlyph() { return <Svg size={14}><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Z" /><path d="M10 20a2 2 0 0 0 4 0" /></Svg>; }
function InfoGlyph() { return <Svg size={13}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8v.01" /></Svg>; }
function PencilGlyph() { return <Svg size={13}><path d="M4 20h4L19 9l-4-4L4 16v4Z" /><path d="m14 6 4 4" /></Svg>; }
function BuildingGlyph() { return <Svg size={16}><path d="M4 21V5l8-3 8 3v16" /><path d="M9 21v-4h6v4M8 8h.01M12 8h.01M16 8h.01M8 12h.01M12 12h.01M16 12h.01" /></Svg>; }
function CloudGlyph() { return <Svg size={22}><path d="M7 18a5 5 0 1 1 .9-9.9A6 6 0 0 1 19.5 10 4 4 0 0 1 18 18H7Z" /><path d="M12 11v3M12 16.5v.01" /></Svg>; }
