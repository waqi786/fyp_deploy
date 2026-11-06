/** Reader API client: open, upload, pages, summary, chat and translation. */

import { CreditLimitError, type UsageLimit } from "../search/researchApi";

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

export type DocumentSource = "upload" | "open_access" | "abstract";
export type Level = "expert" | "student" | "simple";

export type ReaderCaption = { kind: "figure" | "table"; number: number; page: number; caption: string };
export type ReaderDocument = {
  id: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  url?: string | null;
  abstract?: string | null;
  source: DocumentSource;
  has_pdf: boolean;
  page_count: number;
  word_count: number;
  reading_minutes: number;
  scanned_pages: number[];
  captions: ReaderCaption[];
  is_open_access: boolean;
  citation_count: number;
};
export type SummaryPoint = { text: string; pages: number[] };
export type ReaderSummary = {
  tldr: SummaryPoint;
  key_points: SummaryPoint[];
  sections: Record<string, SummaryPoint>;
  level: Level;
  language: string;
  basis: DocumentSource;
  basic: boolean;
  credits_used: number;
};
export type ReaderCitation = { page: number; quote: string };
export type ReaderAnswer = {
  answer: string;
  citations: ReaderCitation[];
  confidence: "high" | "medium" | "low";
  not_found: boolean;
  language: string;
  credits_used: number;
};
export type TranslatedPage = { page: number; paragraphs: string[]; original: string[] };
export type PaperHandoff = {
  paper_id?: string;
  title: string;
  abstract?: string | null;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  url?: string | null;
  pdf_url?: string | null;
  is_open_access?: boolean;
  citation_count?: number;
};

/** Error with a stable code the page can translate (never shows server wording). */
export class ReaderError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(code);
    this.name = "ReaderError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/reader${path}`, init);
  } catch (error) {
    if ((error as Error)?.name === "AbortError") throw error;
    console.error(`[Resora Reader] ${init?.method || "GET"} ${apiBaseUrl}/reader${path} did not reach the API (network error or CORS block).`, error);
    throw new ReaderError("network", 0);
  }
  if (response.ok) return (await response.json()) as T;
  const body = (await response.json().catch(() => ({}))) as { detail?: { code?: string } & Partial<UsageLimit> };
  if (response.status === 402 && body.detail?.scope) throw new CreditLimitError(body.detail as UsageLimit);
  if (body.detail && typeof body.detail === "object" && body.detail.code) throw new ReaderError(body.detail.code, response.status);
  // No Reader error code: the request never reached the Reader API (old server build, missing route or proxy).
  // This is NOT "document not found" — say so in the console for developers, show a neutral message to users.
  console.error(`[Resora Reader] ${init?.method || "GET"} ${path} returned ${response.status} without a Reader error code. Is the API running the latest build with the /reader router?`);
  throw new ReaderError("service_unavailable", response.status);
}

const json = (body: unknown, signal?: AbortSignal): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
  signal,
});

export const readerApi = {
  open: (payload: { paper?: PaperHandoff; link?: string }, signal?: AbortSignal) => request<ReaderDocument>("/open", json(payload, signal)),
  upload: (file: File, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    return request<ReaderDocument>("/upload", { method: "POST", body: form, signal });
  },
  get: (id: string, signal?: AbortSignal) => request<ReaderDocument>(`/${encodeURIComponent(id)}`, { signal }),
  pages: (id: string, signal?: AbortSignal) =>
    request<{ pages: Array<{ page: number; text: string }> }>(`/${encodeURIComponent(id)}/pages?start=1&end=400`, { signal }).then((data) => data.pages),
  summary: (id: string, level: Level, language: string, signal?: AbortSignal) =>
    request<ReaderSummary>(`/${encodeURIComponent(id)}/summary`, json({ level, language }, signal)),
  ask: (id: string, question: string, language: string, signal?: AbortSignal) =>
    request<ReaderAnswer>(`/${encodeURIComponent(id)}/ask`, json({ question, language }, signal)),
  translate: (id: string, pages: number[], language: string, signal?: AbortSignal) =>
    request<{ language: string; pages: TranslatedPage[]; credits_used: number }>(`/${encodeURIComponent(id)}/translate`, json({ pages, language }, signal)),
  pdfUrl: (id: string) => `${apiBaseUrl}/reader/${encodeURIComponent(id)}/pdf`,
};

/* ------------------------------------------------------------------ handoff from Search and recent documents */

const HANDOFF_PREFIX = "resora-reader-handoff:";
const RECENT_KEY = "resora-reader-recent";

export function storeHandoff(key: string, paper: PaperHandoff) {
  try {
    window.sessionStorage.setItem(HANDOFF_PREFIX + key, JSON.stringify(paper));
  } catch {
    /* storage blocked: the Reader will show the upload screen instead */
  }
}

export function readHandoff(key: string): PaperHandoff | null {
  try {
    const raw = window.sessionStorage.getItem(HANDOFF_PREFIX + key);
    return raw ? (JSON.parse(raw) as PaperHandoff) : null;
  } catch {
    return null;
  }
}

export type RecentDocument = { id: string; title: string; source: DocumentSource; openedAt: number };

export function readRecent(): RecentDocument[] {
  try {
    const items = JSON.parse(window.localStorage.getItem(RECENT_KEY) || "[]") as RecentDocument[];
    return Array.isArray(items) ? items.filter((item) => item && typeof item.id === "string").slice(0, 8) : [];
  } catch {
    return [];
  }
}

export function rememberRecent(document: ReaderDocument) {
  try {
    const items = readRecent().filter((item) => item.id !== document.id);
    items.unshift({ id: document.id, title: document.title, source: document.source, openedAt: Date.now() });
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, 8)));
  } catch {
    /* ignore */
  }
}

export function forgetRecent(id: string) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(readRecent().filter((item) => item.id !== id)));
  } catch {
    /* ignore */
  }
}
