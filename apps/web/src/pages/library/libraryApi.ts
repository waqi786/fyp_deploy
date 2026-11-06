/** Library API client. Same private identity as Compare (per-browser owner header + signed-in session token). */
import { comparisonHeaders } from "../compare/compareApi";
import type { PaperHandoff } from "../reader/readerApi";

export const libraryApiBase = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

export type ReadingStatus = "to_read" | "reading" | "read";
export type SaveSource = "search" | "reader" | "compare" | "import" | "manual";
export type IdeaStatus = "new" | "exploring" | "parked" | "done";
export type CitationStyle = "apa" | "mla" | "chicago" | "harvard" | "ieee" | "vancouver";
export type ExportFormat = "bibtex" | "biblatex" | "ris" | "endnote" | "csljson" | "markdown" | "text";

export type LibraryItem = {
  id: string;
  paper_key: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  arxiv_id?: string | null;
  url?: string | null;
  pdf_url?: string | null;
  abstract?: string | null;
  reader_doc_id?: string | null;
  source: SaveSource;
  status: ReadingStatus;
  important: boolean;
  read_later: boolean;
  tags: string[];
  list_ids: string[];
  added_at: string;
  updated_at: string;
  opened_at?: string | null;
};

export type ProjectStats = { papers: number; to_read: number; important: number; notes: number; ideas: number; tasks_open: number };
export type LibraryList = {
  id: string;
  kind: "project" | "collection";
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  item_count: number;
  item_ids?: string[] | null;
  stats?: ProjectStats | null;
};

export type LibraryNote = {
  id: string;
  kind: "note" | "idea";
  title?: string | null;
  body: string;
  quote?: string | null;
  page?: number | null;
  item_id?: string | null;
  project_id?: string | null;
  status?: IdeaStatus | null;
  created_at: string;
  updated_at: string;
};

export type LibraryTask = {
  id: string;
  title: string;
  due_date?: string | null;
  done: boolean;
  priority: "normal" | "high";
  project_id?: string | null;
  item_id?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
};

export type Overview = {
  counts: Record<"saved" | "to_read" | "reading" | "read" | "important" | "read_later" | "notes" | "ideas" | "tasks_open" | "tasks_overdue" | "projects" | "collections", number>;
  tags: Array<{ tag: string; count: number }>;
};

export type CitationEntry = { id: string; text: string; parts: Array<{ text: string; italic: boolean }> };
export type AskSource = { n: number; kind: "paper" | "note" | "idea"; id: string; title: string; snippet: string; item_id?: string | null };
export type AskResult = { mode: "answer" | "matches"; answer?: string | null; not_found: boolean; sources: AskSource[]; window_applied: boolean; credits_used: number };
export type ImportResult = { format: string; added: number; already_saved: number; items: LibraryItem[]; not_found: string[] };
export type Scope = { item_ids?: string[]; list_id?: string };

/** An error with a stable code the page translates; server wording is never shown. */
export class LibraryError extends Error {
  constructor(public code: string, public status = 0) {
    super(code);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${libraryApiBase}/library${path}`, {
      ...init,
      headers: { ...comparisonHeaders(), ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers || {}) },
    });
  } catch (error) {
    if ((error as Error)?.name === "AbortError") throw error;
    throw new LibraryError("network");
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: { code?: string } } | null;
    throw new LibraryError(typeof body?.detail?.code === "string" ? body.detail.code : response.status === 404 ? "not_found" : "unavailable", response.status);
  }
  return (await response.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);

export type PaperInput = {
  title: string;
  authors?: string[];
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  arxiv_id?: string | null;
  url?: string | null;
  pdf_url?: string | null;
  abstract?: string | null;
  reader_doc_id?: string | null;
};

export function paperInputFrom(paper: PaperHandoff & { reader_doc_id?: string | null }): PaperInput {
  return {
    title: paper.title,
    authors: paper.authors || [],
    year: paper.year ?? null,
    venue: paper.venue || null,
    doi: paper.doi || null,
    url: paper.url || null,
    pdf_url: paper.pdf_url || null,
    abstract: paper.abstract || null,
    reader_doc_id: paper.reader_doc_id || null,
  };
}

export const libraryApi = {
  overview: () => call<Overview>("/overview"),
  items: () => call<LibraryItem[]>("/items"),
  save: (papers: PaperInput[], options: { source: SaveSource; list_id?: string; tags?: string[]; read_later?: boolean }) =>
    call<{ items: LibraryItem[]; already_saved: string[] }>("/items", { method: "POST", body: json({ papers, ...options }) }),
  lookup: (papers: PaperInput[]) => call<{ item_ids: Array<string | null> }>("/items/lookup", { method: "POST", body: json({ papers }) }),
  update: (id: string, changes: Partial<Pick<LibraryItem, "status" | "important" | "read_later" | "tags">> & { opened?: boolean }) =>
    call<LibraryItem>(`/items/${encodeURIComponent(id)}`, { method: "PATCH", body: json(changes) }),
  bulk: (ids: string[], action: "set_status" | "add_tag" | "remove_tag" | "add_to_list" | "remove_from_list" | "important" | "read_later" | "delete", value?: string | boolean) =>
    call<{ updated: number }>("/items/bulk", { method: "POST", body: json({ ids, action, value: value ?? null }) }),
  remove: (id: string) => call<void>(`/items/${encodeURIComponent(id)}`, { method: "DELETE" }),
  lists: (kind?: "project" | "collection") => call<LibraryList[]>(`/lists${kind ? `?kind=${kind}` : ""}`),
  list: (id: string) => call<LibraryList>(`/lists/${encodeURIComponent(id)}`),
  createList: (kind: "project" | "collection", name: string, description?: string) => call<LibraryList>("/lists", { method: "POST", body: json({ kind, name, description: description || null }) }),
  updateList: (id: string, changes: { name?: string; description?: string }) => call<LibraryList>(`/lists/${encodeURIComponent(id)}`, { method: "PATCH", body: json(changes) }),
  deleteList: (id: string) => call<void>(`/lists/${encodeURIComponent(id)}`, { method: "DELETE" }),
  notes: (filter: { kind?: "note" | "idea"; project_id?: string; item_id?: string } = {}) => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, value]) => value) as Array<[string, string]>);
    return call<LibraryNote[]>(`/notes${params.toString() ? `?${params}` : ""}`);
  },
  createNote: (note: Partial<LibraryNote> & { kind: "note" | "idea" }) => call<LibraryNote>("/notes", { method: "POST", body: json(note) }),
  updateNote: (id: string, changes: Partial<LibraryNote>) => call<LibraryNote>(`/notes/${encodeURIComponent(id)}`, { method: "PATCH", body: json(changes) }),
  deleteNote: (id: string) => call<void>(`/notes/${encodeURIComponent(id)}`, { method: "DELETE" }),
  tasks: (projectId?: string) => call<LibraryTask[]>(`/tasks${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),
  createTask: (task: { title: string; due_date?: string | null; priority?: "normal" | "high"; project_id?: string | null; item_id?: string | null }) => call<LibraryTask>("/tasks", { method: "POST", body: json(task) }),
  updateTask: (id: string, changes: Partial<Omit<LibraryTask, "id">>) => call<LibraryTask>(`/tasks/${encodeURIComponent(id)}`, { method: "PATCH", body: json(changes) }),
  deleteTask: (id: string) => call<void>(`/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
  cite: (scope: Scope, style: CitationStyle) => call<{ style: CitationStyle; entries: CitationEntry[] }>("/citations/format", { method: "POST", body: json({ ...scope, style }) }),
  exportCitations: (scope: Scope, format: ExportFormat, style: CitationStyle) =>
    call<{ content: string; filename: string; mime: string; count: number }>("/citations/export", { method: "POST", body: json({ ...scope, format, style }) }),
  importCitations: (content: string, options: { filename?: string; list_id?: string } = {}) => call<ImportResult>("/citations/import", { method: "POST", body: json({ content, format: "auto", ...options }) }),
  ask: (question: string, language: string, projectId?: string) => call<AskResult>("/ask", { method: "POST", body: json({ question, language, project_id: projectId || null }) }),
};

/** Save one paper from Search, the Reader or Compare. Resolves to the saved item (also when it was saved before). */
export async function saveToLibrary(paper: PaperInput, source: SaveSource) {
  const result = await libraryApi.save([paper], { source });
  return result.items[0];
}
