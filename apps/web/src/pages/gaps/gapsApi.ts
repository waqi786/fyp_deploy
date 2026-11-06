/** Gaps API client (same private identity as Library and Compare). */
import { comparisonHeaders } from "../compare/compareApi";
import { LibraryError, libraryApi, libraryApiBase, type LibraryItem } from "../library/libraryApi";

export type GapPaper = {
  id: string;
  title: string;
  abstract?: string | null;
  year?: number | null;
  venue?: string | null;
  authors: string[];
  institutions?: string[];
  citation_count?: number;
  datasets?: string[];
  methods?: string[];
  study_type?: string | null;
  sample_size?: number | null;
  is_open_access?: boolean;
  /** Only on the client: how to open the paper. */
  doi?: string | null;
  url?: string | null;
  pdf_url?: string | null;
  reader_doc_id?: string | null;
};

export type Facet = { kind: string; label: string };
export type SignalKind = "combination_untested" | "combination_thin" | "head_to_head" | "repeated_limitation" | "benchmark_concentration" | "growing_thin" | "ai_hypothesis";
export type Level = "strong" | "moderate" | "limited" | "hypothesis";
export type Signal = {
  id: string;
  kind: SignalKind;
  level: Level;
  a: Facet;
  b?: Facet;
  shared?: string[];
  detail?: string;
  counts: Record<string, number>;
  papers: Record<string, string[]>;
  quotes: Array<{ paper_id: string; text: string }>;
};
export type SignalState = "saved" | "dismissed" | "explored" | "idea";
export type Trends = {
  years: Array<{ year: number; papers: number; citations: number }>;
  series: Record<"method" | "dataset" | "task", Array<{ label: string; total: number; by_year: Record<string, number> }>>;
  keywords: Array<{ label: string; count: number }>;
};
export type People = {
  researchers: Array<{ name: string; papers: number; citations: number; first_year?: number | null; last_year?: number | null; collaborators: string[]; suggested?: Array<{ name: string; shared: string[] }>; paper_ids: string[] }>;
  institutions: Array<{ name: string; papers: number }>;
};
export type DatasetRow = { name: string; papers: number; paper_ids: string[]; tasks: string[]; methods: string[]; metrics: string[]; sample_size?: number | null; first_year?: number | null; last_year?: number | null; open_access_papers: number; quote: string };
export type Analysis = { scope_key: string; paper_count: number; signals: Signal[]; trends: Trends; people: People; datasets: DatasetRow[]; states: Record<string, SignalState> };
export type Stance = "supports" | "opposes" | "mixed" | "not_addressed";
export type Consensus = { mode: "ai" | "keywords"; rows: Array<{ paper_id: string; stance: Stance; reason: string; quote: string }>; counts: Record<Stance, number>; credits_used: number };
export type Scope = { kind: "project" | "collection" | "library" | "topic"; id?: string; label: string };

async function call<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${libraryApiBase}${path}`, { method, headers: { ...comparisonHeaders(), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new LibraryError("network");
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
    throw new LibraryError(typeof detail?.detail?.code === "string" ? detail.detail.code : response.status === 402 ? "limit_reached" : "unavailable", response.status);
  }
  return (await response.json()) as T;
}

const strip = ({ doi: _doi, url: _url, pdf_url: _pdf, reader_doc_id: _reader, ...paper }: GapPaper) => paper;

export const gapsApi = {
  signals: (papers: GapPaper[], scope: Scope) => call<Analysis>("/gap/signals", { papers: papers.map(strip), scope, current_year: new Date().getFullYear() }),
  setState: (signalId: string, scopeKey: string, state: SignalState | null, snapshot: Record<string, unknown> = {}) => call<void>(`/gap/states/${encodeURIComponent(signalId)}`, { scope_key: scopeKey, state, snapshot }, "PUT"),
  toIdea: (signalId: string, scopeKey: string, title: string, body: string, projectId?: string) => call<{ idea_id: string }>(`/gap/states/${encodeURIComponent(signalId)}/idea`, { scope_key: scopeKey, title, body, project_id: projectId || null }),
  consensus: (question: string, papers: GapPaper[], language: string) => call<Consensus>("/gap/consensus", { question, papers: papers.map(strip), language }),
  hypotheses: (papers: GapPaper[], focus: string, signals: Signal[], language: string) => call<{ hypotheses: Signal[]; credits_used: number }>("/gap/hypotheses", { papers: papers.map(strip), focus, signals: signals.slice(0, 20), language }),
};

export type RecommendationReason = { kind: "extends" | "same_dataset" | "same_method" | "similar_topic" | "addresses_limitation"; paper_title: string; label: string };
export type Recommendation = { paper_id: string; reason: RecommendationReason };

export async function recommendFor(saved: GapPaper[], query: string, notes: string[] = []): Promise<Array<{ paper: GapPaper; reason: RecommendationReason }>> {
  const candidates = (await topicPapers(query)).slice(0, 300);
  if (!candidates.length || !saved.length) return [];
  const result = await call<{ recommendations: Recommendation[] }>("/gap/recommendations", { saved: saved.slice(0, 300).map(strip), candidates: candidates.map(strip), notes: notes.slice(0, 200), current_year: new Date().getFullYear(), limit: 10 });
  const byId = new Map(candidates.map((paper) => [paper.id, paper]));
  return result.recommendations.flatMap((row) => { const paper = byId.get(row.paper_id); return paper ? [{ paper, reason: row.reason }] : []; });
}

export function paperFromItem(item: LibraryItem): GapPaper {
  return { id: item.id, title: item.title, abstract: item.abstract || null, year: item.year ?? null, venue: item.venue || null, authors: item.authors, doi: item.doi || null, url: item.url || null, pdf_url: item.pdf_url || null, reader_doc_id: item.reader_doc_id || null };
}

type SearchPaper = {
  paper_id: string; title: string; abstract?: string | null; year?: number | null; venue?: string | null; citation_count?: number;
  authors?: Array<{ name?: string; institution?: string; affiliation?: string }>; institutions?: string[]; datasets?: string[]; methodologies?: string[];
  study_type?: string | null; sample_size?: number | null; is_open_access?: boolean; doi?: string | null; url?: string | null; pdf_url?: string | null;
};

/** The most relevant papers for a topic (up to 200), from the same search as the Search tab. */
export async function topicPapers(query: string): Promise<GapPaper[]> {
  const pages = await Promise.all([1, 2].map((page) => call<{ papers: SearchPaper[] }>("/search/", { query, limit: 100, page }).catch((error) => { if (page === 1) throw error; return { papers: [] }; })));
  const seen = new Set<string>();
  return pages.flatMap((page) => page.papers || []).filter((paper) => paper.title && !seen.has(paper.paper_id) && seen.add(paper.paper_id)).map((paper) => ({
    id: paper.paper_id,
    title: paper.title.replace(/<[^>]+>/g, ""),
    abstract: paper.abstract ? paper.abstract.replace(/<[^>]+>/g, " ") : null,
    year: paper.year ?? null,
    venue: paper.venue || null,
    authors: (paper.authors || []).map((author) => author.name || "").filter(Boolean),
    institutions: [...(paper.institutions || []), ...(paper.authors || []).map((author) => author.institution || author.affiliation || "")].filter(Boolean),
    citation_count: paper.citation_count || 0,
    datasets: paper.datasets || [],
    methods: paper.methodologies || [],
    study_type: paper.study_type || null,
    sample_size: paper.sample_size ?? null,
    is_open_access: Boolean(paper.is_open_access),
    doi: paper.doi || null,
    url: paper.url || null,
    pdf_url: paper.pdf_url || null,
  }));
}

export async function scopePapers(scope: Scope): Promise<GapPaper[]> {
  if (scope.kind === "topic") return topicPapers(scope.label);
  const items = await libraryApi.items();
  if (scope.kind === "library") return items.map(paperFromItem);
  return items.filter((item) => item.list_ids.includes(scope.id || "")).map(paperFromItem);
}
