/** Write API client: reviews and drafts, screening, claim checks. */
import { comparisonHeaders } from "../compare/compareApi";
import { LibraryError, libraryApiBase, type CitationStyle } from "../library/libraryApi";

export type ReviewStyle = "thematic" | "methodological" | "chronological" | "narrative";
export type DraftType = "introduction" | "related_work" | "abstract" | "research_questions" | "proposal" | "conclusion";
export type Section = { id: string; heading: string; purpose: string; papers: number[]; text: string; status: "empty" | "generated" | "edited"; unsupported: string[] };
export type Source = { item_id?: string | null; title: string; authors: string[]; year?: number | null; venue?: string | null; doi?: string | null; url?: string | null; abstract?: string | null };
export type WriteDoc = { id: string; kind: "review" | "draft"; title: string; style: string; language: string; citation_style: CitationStyle; project_id?: string | null; sources: Array<Source | null>; sections: Section[]; created_at: string; updated_at: string };
export type DocSummary = { id: string; kind: "review" | "draft"; title: string; style: string; language: string; project_id?: string | null; updated_at: string; summary: { sections: number; words: number; sources: number } };
export type Version = { id: string; label: string; created_at: string; words: number };
export type Decision = "include" | "exclude" | "maybe";
export type ScreeningRecord = { id: string; title: string; authors: string[]; year?: number | null; venue?: string | null; doi?: string | null; abstract?: string | null; duplicate_of?: string | null; ta_decision?: Decision | null; ta_reason?: string | null; ft_decision?: Decision | null; ft_reason?: string | null; note?: string | null };
export type Prisma = { identified: number; duplicates: number; screened: number; screen_excluded: number; screen_pending: number; full_text_assessed: number; full_text_excluded: number; full_text_pending: number; full_text_reasons: Array<{ reason: string; count: number }>; included: number };
export type Screening = { id: string; name: string; project_id?: string | null; criteria: string; created_at: string; updated_at: string; prisma: Prisma; records?: ScreeningRecord[] };
export type Theme = { label: string; kind: "task" | "domain" | "method" | "dataset"; papers: number[]; evidence: "consistent" | "mixed" | "unclear"; quotes: Array<{ n: number; text: string }> };
export type Verdict = "supported" | "conflicting" | "mixed" | "not_found";
export type ClaimResult = { claim: string; verdict: Verdict; strength?: "strong" | "moderate" | "limited" | null; evidence: Array<{ n: number; quote: string }>; safer?: string | null };
export type ClaimCheck = { mode: "ai" | "keywords"; claims: ClaimResult[]; sources: Array<{ n: number; item_id?: string | null; title: string; year?: number | null; authors: string[] }>; credits_used: number };

async function call<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${libraryApiBase}/write${path}`, { method, headers: { ...comparisonHeaders(), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
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

export const writeApi = {
  documents: () => call<DocSummary[]>("/documents"),
  create: (data: { kind: "review" | "draft"; title: string; style: string; language: string; citation_style: CitationStyle; project_id?: string | null; item_ids?: string[] }) => call<WriteDoc>("/documents", data),
  get: (id: string) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}`),
  update: (id: string, changes: { title?: string; citation_style?: CitationStyle; language?: string; sections?: Section[] }) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}`, changes, "PATCH"),
  remove: (id: string) => call<void>(`/documents/${encodeURIComponent(id)}`, undefined, "DELETE"),
  addSources: (id: string, itemIds: string[]) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}/sources`, { item_ids: itemIds }),
  removeSource: (id: string, n: number) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}/sources/${n}`, undefined, "DELETE"),
  outline: (id: string, style: ReviewStyle, themes?: Array<{ label: string; papers: number[] }>) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}/outline`, { style, ...(themes ? { themes } : {}) }),
  themes: (id: string) => call<{ themes: Theme[] }>(`/documents/${encodeURIComponent(id)}/themes`),
  writeSection: (id: string, sectionId: string, instruction: string) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}/sections/${encodeURIComponent(sectionId)}/write`, { instruction }),
  check: (id: string) => call<{ broken_markers: number[]; uncited_sources: number[]; unsupported: Array<{ section_id: string; sentences: string[] }> }>(`/documents/${encodeURIComponent(id)}/check`),
  versions: (id: string) => call<{ versions: Version[] }>(`/documents/${encodeURIComponent(id)}/versions`),
  saveVersion: (id: string) => call<{ id: string }>(`/documents/${encodeURIComponent(id)}/versions`, {}),
  restore: (id: string, versionId: string) => call<WriteDoc>(`/documents/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/restore`, {}),
  exportDoc: (id: string, format: "docx" | "markdown" | "latex" | "html", rtl: boolean, referencesLabel: string) =>
    call<{ filename: string; mime: string; content?: string; base64?: string; bib?: string; bib_filename?: string }>(`/documents/${encodeURIComponent(id)}/export`, { format, rtl, references_label: referencesLabel }),
  screenings: () => call<{ screenings: Screening[] }>("/screenings"),
  createScreening: (data: { name: string; project_id?: string | null; item_ids?: string[]; criteria?: string }) => call<Screening>("/screenings", data),
  screening: (id: string) => call<Screening>(`/screenings/${encodeURIComponent(id)}`),
  updateScreening: (id: string, changes: { name?: string; criteria?: string }) => call<Screening>(`/screenings/${encodeURIComponent(id)}`, changes, "PATCH"),
  deleteScreening: (id: string) => call<void>(`/screenings/${encodeURIComponent(id)}`, undefined, "DELETE"),
  importRecords: (id: string, data: { item_ids?: string[]; content?: string; filename?: string }) => call<{ added: number; duplicates: number; screening: Screening }>(`/screenings/${encodeURIComponent(id)}/records`, data),
  decide: (id: string, recordId: string, changes: Partial<Pick<ScreeningRecord, "ta_decision" | "ta_reason" | "ft_decision" | "ft_reason" | "note">>) =>
    call<{ record: ScreeningRecord; prisma: Prisma }>(`/screenings/${encodeURIComponent(id)}/records/${encodeURIComponent(recordId)}`, changes, "PATCH"),
  toLibrary: (id: string, projectId?: string | null) => call<{ saved: number; already_saved: number }>(`/screenings/${encodeURIComponent(id)}/to-library`, { project_id: projectId || null }),
  claims: (data: { text: string; item_ids?: string[]; project_id?: string | null; document_id?: string | null; language: string }) => call<ClaimCheck>("/claims", data),
};
