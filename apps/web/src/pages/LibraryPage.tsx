/** Library — research memory: Projects · Saved · Read later · Collections · Notes · Citations · Ideas · Tasks.
 *  Sub-tabs are nested routes (/library/<tab>), so every view has a shareable URL. All wording comes from the shared
 *  catalog (search/copy.ts); the page is excluded from the app-wide translator. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { storeHandoff } from "./reader/readerApi";
import { useSearchCopy, type SearchCopyKey } from "./search/copy";
import { AskBar } from "./library/AskBar";
import { CitationsView, ImportDialog } from "./library/CitationsView";
import { CollectionDetail, CollectionsView, ProjectDetail, ProjectsView } from "./library/ListsView";
import { NotesView } from "./library/NotesView";
import { PapersView } from "./library/PapersView";
import { TasksView } from "./library/TasksView";
import { LibraryError, libraryApi, type LibraryItem, type LibraryList, type Overview } from "./library/libraryApi";
import { ClockGlyph, LibraryContext, countLabel, PlusGlyph, SearchGlyph, UploadGlyph, directionOf, formatNumber, useLib, type LibraryCtx } from "./library/ui";
import "./SearchPage.css";
import "./LibraryPage.css";

type TabId = "projects" | "saved" | "read-later" | "collections" | "notes" | "citations" | "ideas" | "tasks";
const TABS: Array<{ id: TabId; key: SearchCopyKey; count?: keyof Overview["counts"] }> = [
  { id: "projects", key: "libTabProjects", count: "projects" },
  { id: "saved", key: "libTabSaved", count: "saved" },
  { id: "read-later", key: "libTabReadLater", count: "read_later" },
  { id: "collections", key: "libTabCollections", count: "collections" },
  { id: "notes", key: "libTabNotes", count: "notes" },
  { id: "citations", key: "libTabCitations" },
  { id: "ideas", key: "libTabIdeas", count: "ideas" },
  { id: "tasks", key: "libTabTasks", count: "tasks_open" },
];

const ERROR_KEYS: Record<string, SearchCopyKey> = {
  network: "libErrorNetwork",
  sign_in_required: "libErrorSignIn",
  library_full: "libErrorFull",
  unreadable_file: "libErrorUnreadable",
  nothing_to_import: "libErrorNothingToImport",
  nothing_to_export: "libErrorNothingToExport",
  not_found: "libErrorNotFound",
};

export function LibraryPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const t = useSearchCopy(interfaceLanguage);
  const navigate = useNavigate();
  const location = useLocation();
  const [items, setItemsState] = useState<LibraryItem[]>([]);
  const [lists, setLists] = useState<LibraryList[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toastText, setToastText] = useState("");
  const [importing, setImporting] = useState(false);
  const toastTimer = useRef<number | undefined>(undefined);

  const errorText = useCallback((caught: unknown) => {
    const code = caught instanceof LibraryError ? caught.code : "unavailable";
    return t(ERROR_KEYS[code] || "libErrorGeneric");
  }, [t]);

  const refresh = useCallback(async () => {
    try {
      const [nextItems, nextLists, nextOverview] = await Promise.all([libraryApi.items(), libraryApi.lists(), libraryApi.overview()]);
      setItemsState(nextItems);
      setLists(nextLists);
      setOverview(nextOverview);
      setError("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoading(false);
    }
  }, [errorText]);

  useEffect(() => { void refresh(); }, [refresh]);

  const toast = useCallback((message: string) => {
    setToastText(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastText(""), 3200);
  }, []);

  const openItem = useCallback((item: LibraryItem) => {
    void libraryApi.update(item.id, { opened: true }).then((saved) => setItemsState((current) => current.map((entry) => (entry.id === saved.id ? saved : entry)))).catch(() => undefined);
    if (item.reader_doc_id) {
      navigate(`/reader/${encodeURIComponent(item.reader_doc_id)}`);
      return;
    }
    const key = `lib-${item.id}`;
    storeHandoff(key, { paper_id: item.id, title: item.title, abstract: item.abstract || null, authors: item.authors, year: item.year ?? null, venue: item.venue || null, doi: item.doi || null, url: item.url || null, pdf_url: item.pdf_url || null });
    navigate(`/reader?${new URLSearchParams({ paper: key, tab: "summary" })}`);
  }, [navigate]);

  const context = useMemo<LibraryCtx>(() => ({
    t, language: interfaceLanguage, items, lists, overview, loading, error, refresh,
    setItems: (update) => setItemsState(update), toast, openItem, errorText,
  }), [t, interfaceLanguage, items, lists, overview, loading, error, refresh, toast, openItem, errorText]);

  const counts = overview?.counts;
  const projectMatch = location.pathname.match(/^\/library\/projects\/([^/]+)/);
  const findPapers = <Link to="/search" className="lb-button lb-button-primary"><SearchGlyph />{t("libFindPapers")}</Link>;

  return (
    <LibraryContext.Provider value={context}>
      <section className="rs-search lb-library" dir={directionOf(interfaceLanguage)} lang={interfaceLanguage} data-no-translate="">
        <div className="lb-shell">
          <header className="lb-head">
            <div className="lb-head-text">
              <h1>{t("libTitle")}</h1>
              <p className="lb-head-sub">
                {counts
                  ? [countLabel(t, counts.saved, "libPaperCountOne", "libPaperCount", interfaceLanguage), counts.projects ? countLabel(t, counts.projects, "libSummaryProjectsOne", "libSummaryProjects", interfaceLanguage) : "", counts.to_read ? t("libSummaryToRead", { count: formatNumber(counts.to_read, interfaceLanguage) }) : ""].filter(Boolean).join(" · ")
                  : t("libSubtitle")}
              </p>
            </div>
            <div className="lb-head-actions">
              {counts?.tasks_overdue ? <Link to="/library/tasks" className="lb-due-pill"><ClockGlyph />{t("libOverdueTasks", { count: counts.tasks_overdue })}</Link> : null}
              <button type="button" className="lb-button lb-button-quiet" onClick={() => setImporting(true)}><UploadGlyph />{t("libImport")}</button>
              <Link to="/search" className="lb-button lb-button-primary"><PlusGlyph />{t("libAddPapers")}</Link>
            </div>
          </header>

          <nav className="lb-tabs" aria-label={t("libTitle")}>
            {TABS.map((tab) => (
              <NavLink key={tab.id} to={`/library/${tab.id}`} className={({ isActive }) => `lb-tab${isActive || (tab.id === "saved" && location.pathname.replace(/\/$/, "") === "/library") ? " is-active" : ""}`}>
                <span>{t(tab.key)}</span>
                {tab.count && counts && counts[tab.count] ? <span className={`lb-tab-count${tab.id === "tasks" && counts.tasks_overdue ? " is-alert" : ""}`}>{formatNumber(counts[tab.count], interfaceLanguage)}</span> : null}
              </NavLink>
            ))}
          </nav>

          <main className="lb-main">
            <Routes>
              <Route index element={<SavedTab findPapers={findPapers} />} />
              <Route path="saved" element={<SavedTab findPapers={findPapers} />} />
              <Route path="read-later" element={<PapersView items={items.filter((item) => item.read_later)} emptyTitle={t("libNoReadLater")} emptyBody={t("libNoReadLaterBody")} />} />
              <Route path="projects" element={<ProjectsView />} />
              <Route path="projects/:projectId" element={<ProjectDetail />} />
              <Route path="collections" element={<CollectionsView />} />
              <Route path="collections/:collectionId" element={<CollectionDetail />} />
              <Route path="notes" element={<NotesView kind="note" onChange={() => void refresh()} />} />
              <Route path="ideas" element={<NotesView kind="idea" onChange={() => void refresh()} />} />
              <Route path="tasks" element={<TasksView />} />
              <Route path="citations" element={<CitationsView onImport={() => setImporting(true)} />} />
              <Route path="*" element={<Navigate to="/library/saved" replace />} />
            </Routes>
          </main>
        </div>

        <AskBar projectId={projectMatch?.[1]} />

        {importing ? <ImportDialog listId={projectMatch?.[1]} onClose={() => setImporting(false)} onDone={() => void refresh()} /> : null}
        <div className="lb-toast-region" aria-live="polite">{toastText ? <div className="lb-toast" role="status">{toastText}</div> : null}</div>
      </section>
    </LibraryContext.Provider>
  );
}

function SavedTab({ findPapers }: { findPapers: ReactNode }) {
  const { t, items } = useLib();
  return <PapersView items={items} emptyTitle={t("libNoSaved")} emptyBody={t("libNoSavedBody")} emptyAction={findPapers} />;
}
