/** Helpers shared by Gaps, Write and Library: calm localized error text and opening a paper in the Reader. */
import type { useNavigate } from "react-router-dom";
import { storeHandoff } from "../reader/readerApi";
import type { SearchCopyKey, SearchT } from "../search/copy";
import { LibraryError } from "../library/libraryApi";

const ERRORS: Record<string, SearchCopyKey> = { network: "libErrorNetwork", sign_in_required: "libErrorSignIn", limit_reached: "gapErrorCredits", ai_unavailable: "gapErrorAi" };

export function errorTextFor(t: SearchT, caught: unknown) {
  const code = caught instanceof LibraryError ? caught.code : "unavailable";
  return t(ERRORS[code] || "libErrorGeneric");
}

export function openInReader(navigate: ReturnType<typeof useNavigate>, paper: { id: string; title: string; abstract?: string | null; authors: string[]; year?: number | null; venue?: string | null; doi?: string | null; url?: string | null; pdf_url?: string | null; reader_doc_id?: string | null }) {
  if (paper.reader_doc_id) {
    navigate(`/reader/${encodeURIComponent(paper.reader_doc_id)}`);
    return;
  }
  const key = `gap-${paper.id}`.slice(0, 120);
  storeHandoff(key, { paper_id: paper.id, title: paper.title, abstract: paper.abstract || null, authors: paper.authors, year: paper.year ?? null, venue: paper.venue || null, doi: paper.doi || null, url: paper.url || null, pdf_url: paper.pdf_url || null });
  navigate(`/reader?${new URLSearchParams({ paper: key, tab: "summary" })}`);
}
