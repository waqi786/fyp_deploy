/** Shared Compare API helpers: the private owner header used by every Compare request, and adding papers by reference. */
import type { PaperHandoff } from "../reader/readerApi";

export const compareApiBase = import.meta.env.VITE_API_BASE_URL || "/api/v1";

/** Same identity as the Compare page: a per-browser owner id, plus the signed-in session token when present. */
export function comparisonHeaders(): Record<string, string> {
  let owner = "";
  try {
    owner = window.localStorage.getItem("resora-compare-owner") || "";
    if (!owner) {
      owner = crypto.randomUUID();
      window.localStorage.setItem("resora-compare-owner", owner);
    }
  } catch {
    owner = owner || crypto.randomUUID();
  }
  const headers: Record<string, string> = { "X-Resora-User": owner };
  try {
    const sessionKey = Object.keys(window.localStorage).find((key) => key.startsWith("sb-") && key.endsWith("-auth-token"));
    const sessionValue = sessionKey ? (JSON.parse(window.localStorage.getItem(sessionKey) || "{}") as { access_token?: string; currentSession?: { access_token?: string } }) : null;
    const accessToken = sessionValue?.access_token || sessionValue?.currentSession?.access_token;
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  } catch {
    /* a missing or invalid optional session is handled by the API */
  }
  return headers;
}

export type StoredPdf = { id: string; name: string; pages: number; size: number; sha256: string };
export type MissingPaper = { key: string; title: string; reason: "no_open_pdf" | "not_readable" | "mismatch" | "duplicate" | "limit"; publisher_url?: string | null };

/** Ask the API to fetch each paper's legal open-access PDF and store it in this comparison. */
export async function addPapersToComparison(comparisonId: string, papers: Array<PaperHandoff & { key: string }>, signal?: AbortSignal) {
  const response = await fetch(`${compareApiBase}/comparison/pdfs/add-papers`, {
    method: "POST",
    headers: { ...comparisonHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ comparison_id: comparisonId, papers }),
    signal,
  });
  if (!response.ok) throw new Error(`add-papers ${response.status}`);
  return (await response.json()) as { comparison_id: string; files: StoredPdf[]; unavailable: MissingPaper[] };
}

export type SavedComparison = { comparison_id: string; name: string | null; focus: string | null; columns: string[]; file_count: number; updated_at: string };

async function expectJson<T>(response: Response, what: string): Promise<T> {
  if (!response.ok) throw new Error(`${what} ${response.status}`);
  return (await response.json()) as T;
}

/** Comparisons this owner has stored PDFs for, newest first, with the names they gave them. */
export async function listSavedComparisons(signal?: AbortSignal) {
  const response = await fetch(`${compareApiBase}/comparison/pdfs/saved`, { headers: comparisonHeaders(), signal });
  return (await expectJson<{ comparisons: SavedComparison[] }>(response, "saved")).comparisons;
}

/** Remember a comparison's name, focus and columns. `default_name` is used only the first time it is saved. */
export async function saveComparison(comparisonId: string, details: { name?: string; default_name?: string; focus?: string; columns?: string[] }) {
  const response = await fetch(`${compareApiBase}/comparison/pdfs/saved/${encodeURIComponent(comparisonId)}`, {
    method: "PUT",
    headers: { ...comparisonHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(details),
  });
  return expectJson<SavedComparison>(response, "save");
}

/** Delete a comparison together with every stored PDF in it. */
export async function deleteSavedComparison(comparisonId: string) {
  const response = await fetch(`${compareApiBase}/comparison/pdfs/saved/${encodeURIComponent(comparisonId)}`, { method: "DELETE", headers: comparisonHeaders() });
  if (!response.ok && response.status !== 404) throw new Error(`delete ${response.status}`);
}

/** Machine-translate table values into the interface language (private content: never sent to training providers). */
export async function translateComparisonText(comparisonId: string, language: string, texts: string[]) {
  const response = await fetch(`${compareApiBase}/comparison/pdfs/${encodeURIComponent(comparisonId)}/translate`, {
    method: "POST",
    headers: { ...comparisonHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ language, texts }),
  });
  return (await expectJson<{ translations: string[] }>(response, "translate")).translations;
}
