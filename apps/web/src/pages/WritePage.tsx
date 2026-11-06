/** Write — Reviews · Screening · Draft · Check claims. Everything is grounded in papers from the user's Library:
 *  citations are [n] markers to the document's numbered sources, and sentences the sources do not back are flagged. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { useSearchCopy, type SearchCopyKey, type SearchT } from "./search/copy";
import { libraryApi, type CitationStyle, type LibraryItem, type LibraryList } from "./library/libraryApi";
import { STYLES as CITATION_STYLES, download } from "./library/CitationsView";
import { BackGlyph, CheckGlyph, ChevronGlyph, ConfirmButton, CopyGlyph, EmptyState, ErrorLine, Menu, NoteGlyph, PlusGlyph, SearchGlyph, Select, SkeletonRows, SparkGlyph, TaskGlyph, UploadGlyph, authorLine, directionOf, formatDay, formatNumber, useDismiss } from "./library/ui";
import { errorTextFor } from "./gaps/shared";
import { writeApi, type ClaimCheck, type Decision, type DocSummary, type DraftType, type Prisma, type ReviewStyle, type Screening, type ScreeningRecord, type Section, type Theme, type Verdict, type Version, type WriteDoc } from "./write/writeApi";
import "./SearchPage.css";
import "./LibraryPage.css";
import "./GapsWritePage.css";

type TabId = "reviews" | "screening" | "draft" | "claims";
const TABS: Array<{ id: TabId; key: SearchCopyKey }> = [
  { id: "reviews", key: "wrTabReviews" },
  { id: "screening", key: "wrTabScreening" },
  { id: "draft", key: "wrTabDraft" },
  { id: "claims", key: "wrTabClaims" },
];
const REVIEW_STYLES: Array<{ id: ReviewStyle; key: SearchCopyKey }> = [
  { id: "thematic", key: "wrStyleThematic" },
  { id: "methodological", key: "wrStyleMethodological" },
  { id: "chronological", key: "wrStyleChronological" },
  { id: "narrative", key: "wrStyleNarrative" },
];
const DRAFT_TYPES: Array<{ id: DraftType; key: SearchCopyKey }> = [
  { id: "introduction", key: "wrDraftIntroduction" },
  { id: "related_work", key: "wrDraftRelatedWork" },
  { id: "abstract", key: "wrDraftAbstract" },
  { id: "research_questions", key: "wrDraftQuestions" },
  { id: "proposal", key: "wrDraftProposal" },
  { id: "conclusion", key: "wrDraftConclusion" },
];

type Ctx = { t: SearchT; language: string; items: LibraryItem[]; lists: LibraryList[]; toast: (message: string) => void; reloadLibrary: () => void };

export function WritePage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const t = useSearchCopy(interfaceLanguage);
  const location = useLocation();
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [lists, setLists] = useState<LibraryList[]>([]);
  const [toastText, setToastText] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const toast = useCallback((message: string) => {
    setToastText(message);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToastText(""), 3200);
  }, []);
  const reloadLibrary = useCallback(() => {
    libraryApi.items().then(setItems).catch(() => undefined);
    libraryApi.lists().then(setLists).catch(() => undefined);
  }, []);
  useEffect(reloadLibrary, [reloadLibrary]);
  const ctx: Ctx = { t, language: interfaceLanguage, items, lists, toast, reloadLibrary };
  const inEditor = /^\/writing\/doc\//.test(location.pathname);

  return (
    <section className="rs-search lb-library gw-page" dir={directionOf(interfaceLanguage)} lang={interfaceLanguage} data-no-translate="">
      <div className="lb-shell">
        {!inEditor ? (
          <>
            <header className="lb-head">
              <div className="lb-head-text">
                <h1>{t("wrTitle")}</h1>
                <p className="lb-head-sub">{t("wrSubtitle")}</p>
              </div>
            </header>
            <nav className="lb-tabs" aria-label={t("wrTitle")}>
              {TABS.map((tab) => (
                <NavLink key={tab.id} to={`/writing/${tab.id}`} className={({ isActive }) => `lb-tab${isActive || (tab.id === "reviews" && location.pathname.replace(/\/$/, "") === "/writing") ? " is-active" : ""}`}>
                  <span>{t(tab.key)}</span>
                </NavLink>
              ))}
            </nav>
          </>
        ) : null}
        <main className="lb-main">
          <Routes>
            <Route index element={<DocsView ctx={ctx} kind="review" />} />
            <Route path="reviews" element={<DocsView ctx={ctx} kind="review" />} />
            <Route path="draft" element={<DocsView ctx={ctx} kind="draft" />} />
            <Route path="doc/:docId" element={<DocEditor ctx={ctx} />} />
            <Route path="screening" element={<ScreeningsView ctx={ctx} />} />
            <Route path="screening/:screeningId" element={<ScreeningDetail ctx={ctx} />} />
            <Route path="claims" element={<ClaimsView ctx={ctx} />} />
            <Route path="*" element={<Navigate to="/writing/reviews" replace />} />
          </Routes>
        </main>
      </div>
      <div className="lb-toast-region" aria-live="polite">{toastText ? <div className="lb-toast" role="status">{toastText}</div> : null}</div>
    </section>
  );
}

// ---------------------------------------------------------------- source selection (project, collection or chosen papers)

type SourceChoice = { project_id?: string; item_ids: string[] };

function SourcePicker({ ctx, value, onChange }: { ctx: Ctx; value: SourceChoice & { scope: string }; onChange: (next: SourceChoice & { scope: string }) => void }) {
  const { t, items, lists, language } = ctx;
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(language);
    return items.filter((item) => !needle || `${item.title} ${item.authors.join(" ")}`.toLocaleLowerCase(language).includes(needle)).slice(0, 200);
  }, [items, query, language]);
  useEffect(() => {
    // "All saved papers" means every item, including ones that finished loading after the choice was made.
    if (value.scope === "all" && value.item_ids.length !== items.length) onChange({ ...value, item_ids: items.map((item) => item.id) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, value.scope]);
  if (!items.length) return <p className="lb-section-note">{t("wrNoLibrary")} <Link className="lb-link" to="/search">{t("libFindPapers")}</Link></p>;
  return (
    <div className="gw-sources-pick">
      <Select label={t("wrSources")} value={value.scope} onChange={(scope) => {
        const list = lists.find((entry) => entry.id === scope);
        onChange({ scope, project_id: list?.kind === "project" ? list.id : undefined, item_ids: scope === "all" ? items.map((item) => item.id) : scope === "pick" ? [] : list ? items.filter((item) => item.list_ids.includes(list.id)).map((item) => item.id) : [] });
      }} options={[
        { value: "pick", label: t("wrPickPapers") },
        { value: "all", label: t("libAllSavedPapers") },
        ...lists.filter((list) => list.kind === "project").map((list) => ({ value: list.id, label: t("libProjectOption", { name: list.name }) })),
        ...lists.filter((list) => list.kind === "collection").map((list) => ({ value: list.id, label: t("libCollectionOption", { name: list.name }) })),
      ]} />
      {value.scope === "pick" ? (
        <>
          <label className="lb-search lb-search-full"><SearchGlyph /><span className="rs-visually-hidden">{t("libFilterPapers")}</span><input type="search" value={query} dir="auto" onChange={(event) => setQuery(event.target.value)} placeholder={t("libFilterPapers")} /></label>
          <ul className="lb-pick-list gw-pick-short">
            {visible.map((item) => {
              const on = value.item_ids.includes(item.id);
              return (
                <li key={item.id}>
                  <label className={`lb-pick${on ? " is-on" : ""}`}>
                    <span className="lb-check"><input type="checkbox" checked={on} onChange={() => onChange({ ...value, item_ids: on ? value.item_ids.filter((id) => id !== item.id) : [...value.item_ids, item.id] })} /><span aria-hidden="true"><CheckGlyph /></span></span>
                    <span className="lb-pick-text"><bdi className="lb-pick-title">{item.title}</bdi><span className="lb-row-meta"><bdi>{[authorLine(item, t), item.year].filter(Boolean).join(" · ")}</bdi></span></span>
                  </label>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
      <p className="lb-section-note">{t("wrSourcesChosen", { count: formatNumber(value.item_ids.length, language) })}</p>
    </div>
  );
}

// ---------------------------------------------------------------- documents list + create

function DocsView({ ctx, kind }: { ctx: Ctx; kind: "review" | "draft" }) {
  const { t, language, toast } = ctx;
  const navigate = useNavigate();
  const [docs, setDocs] = useState<DocSummary[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [style, setStyle] = useState<string>(kind === "review" ? "thematic" : "introduction");
  const [citation, setCitation] = useState<CitationStyle>("apa");
  const [sources, setSources] = useState<SourceChoice & { scope: string }>({ scope: "pick", item_ids: [] });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    writeApi.documents().then((all) => setDocs(all.filter((doc) => doc.kind === kind))).catch((caught) => setError(errorTextFor(t, caught)));
  }, [kind, t]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !sources.item_ids.length) return;
    setBusy(true);
    try {
      const doc = await writeApi.create({ kind, title: title.trim(), style, language, citation_style: citation, project_id: sources.project_id || null, item_ids: sources.item_ids });
      navigate(`/writing/doc/${doc.id}`);
    } catch (caught) {
      toast(errorTextFor(t, caught));
    } finally {
      setBusy(false);
    }
  }

  const options = kind === "review" ? REVIEW_STYLES : DRAFT_TYPES;
  return (
    <div className="lb-section">
      <div className="lb-section-head">
        <p className="lb-section-note">{kind === "review" ? t("wrReviewsIntro") : t("wrDraftIntro")}</p>
        {!creating ? <button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{kind === "review" ? t("wrNewReview") : t("wrNewDraft")}</button> : null}
      </div>
      {creating ? (
        <form className="lb-panel gw-create" onSubmit={(event) => void create(event)}>
          <label className="lb-field"><span>{t("wrDocTitle")}</span><input autoFocus value={title} maxLength={300} dir="auto" onChange={(event) => setTitle(event.target.value)} placeholder={kind === "review" ? t("wrReviewTitlePlaceholder") : t("wrDraftTitlePlaceholder")} /></label>
          <div className="lb-field">
            <span>{kind === "review" ? t("wrReviewStyle") : t("wrDraftType")}</span>
            <div className="lb-segmented lb-segmented-scroll" role="group" aria-label={kind === "review" ? t("wrReviewStyle") : t("wrDraftType")}>
              {options.map((option) => <button key={option.id} type="button" aria-pressed={style === option.id} className={style === option.id ? "is-active" : ""} onClick={() => setStyle(option.id)}>{t(option.key)}</button>)}
            </div>
          </div>
          <div className="lb-field"><span>{t("wrSources")}</span><SourcePicker ctx={ctx} value={sources} onChange={setSources} /></div>
          <label className="lb-field"><span>{t("libCitationStyle")}</span>
            <Select label={t("libCitationStyle")} value={citation} onChange={(next) => setCitation(next as CitationStyle)} options={CITATION_STYLES.map((entry) => ({ value: entry.id, label: entry.label }))} />
          </label>
          <div className="lb-form-actions">
            <button type="button" className="lb-button lb-button-quiet" onClick={() => setCreating(false)}>{t("libCancel")}</button>
            <button type="submit" className="lb-button lb-button-primary" disabled={busy || !title.trim() || !sources.item_ids.length}>{kind === "review" ? t("wrCreateReview") : t("wrCreateDraft")}</button>
          </div>
        </form>
      ) : null}
      {error ? <ErrorLine message={error} t={t} /> : null}
      {!docs && !error ? <SkeletonRows rows={3} /> : null}
      {docs && !docs.length && !creating ? <EmptyState icon={<NoteGlyph />} title={kind === "review" ? t("wrNoReviews") : t("wrNoDrafts")} body={kind === "review" ? t("wrNoReviewsBody") : t("wrNoDraftsBody")} action={<button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{kind === "review" ? t("wrNewReview") : t("wrNewDraft")}</button>} /> : null}
      {docs?.length ? (
        <ul className="lb-collection-list">
          {docs.map((doc) => (
            <li key={doc.id}>
              <Link to={`/writing/doc/${doc.id}`} className="lb-collection-row">
                <span className="lb-collection-icon" aria-hidden="true"><NoteGlyph /></span>
                <span className="lb-collection-name"><bdi>{doc.title}</bdi></span>
                <span className="lb-collection-count">{t("wrDocMeta", { words: formatNumber(doc.summary.words, language), sources: formatNumber(doc.summary.sources, language), date: formatDay(doc.updated_at, language) })}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- editor

function wordCount(text: string) {
  return (text.match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu) || []).length;
}

function DocEditor({ ctx }: { ctx: Ctx }) {
  const { t, language, items, toast } = ctx;
  const { docId = "" } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<WriteDoc | null>(null);
  const [missing, setMissing] = useState(false);
  const [saving, setSaving] = useState<"saved" | "saving" | "error">("saved");
  const [writing, setWriting] = useState<string | null>(null);
  const [instruction, setInstruction] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [check, setCheck] = useState<{ broken_markers: number[]; uncited_sources: number[] } | null>(null);
  const [claims, setClaims] = useState<Record<string, ClaimCheck | "busy">>({});
  const [themesOpen, setThemesOpen] = useState(false);
  const focused = useRef<{ id: string; el: HTMLTextAreaElement } | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const pending = useRef<Partial<Pick<WriteDoc, "title" | "citation_style">> & { sections?: Section[] }>({});

  useEffect(() => {
    writeApi.get(docId).then(setDoc).catch(() => setMissing(true));
  }, [docId]);

  const flush = useCallback(async () => {
    const changes = pending.current;
    pending.current = {};
    if (!Object.keys(changes).length) return;
    setSaving("saving");
    try {
      const saved = await writeApi.update(docId, changes);
      setDoc((current) => current && ({ ...saved, sections: saved.sections.map((section) => ({ ...section, text: current.sections.find((entry) => entry.id === section.id)?.text ?? section.text })) }));
      setSaving("saved");
    } catch {
      setSaving("error");
    }
  }, [docId]);

  useEffect(() => () => { window.clearTimeout(saveTimer.current); void flush(); }, [flush]);

  function queue(changes: typeof pending.current) {
    pending.current = { ...pending.current, ...changes };
    setSaving("saving");
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => void flush(), 900);
  }

  if (missing) return <EmptyState title={t("libErrorNotFound")} action={<Link className="lb-button lb-button-quiet" to="/writing/reviews">{t("wrBack")}</Link>} />;
  if (!doc) return <SkeletonRows rows={5} />;
  const sources = doc.sources;
  const words = doc.sections.reduce((sum, section) => sum + wordCount(section.text), 0);
  const unsupported = doc.sections.reduce((sum, section) => sum + section.unsupported.length, 0);
  // Coverage: in how many sections each source is cited.
  const coverage: Record<number, number> = {};
  for (const section of doc.sections) {
    for (const n of new Set([...section.text.matchAll(/\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g)].flatMap((match) => match[1].split(/\s*,\s*/).flatMap((part) => { const [a, b] = part.split(/\s*[–-]\s*/).map(Number); return b ? Array.from({ length: Math.max(0, Math.min(b - a, 50)) + 1 }, (_, i) => a + i) : [a]; })))) coverage[n] = (coverage[n] || 0) + 1;
  }

  function editSection(id: string, text: string) {
    setDoc((current) => {
      if (!current) return current;
      const sections = current.sections.map((section) => (section.id === id ? { ...section, text } : section));
      queue({ sections });
      return { ...current, sections };
    });
  }

  function insertCitation(n: number) {
    const target = focused.current;
    if (!target) { toast(t("wrClickSectionFirst")); return; }
    const { el, id } = target;
    const marker = `[${n}]`;
    const start = el.selectionStart ?? el.value.length;
    const before = el.value.slice(0, start).replace(/\s+$/, "");
    const next = `${before} ${marker}${el.value.slice(el.selectionEnd ?? start)}`;
    editSection(id, next);
    window.requestAnimationFrame(() => { el.focus(); const position = before.length + marker.length + 1; el.setSelectionRange(position, position); });
  }

  async function writeWithSources(section: Section) {
    window.clearTimeout(saveTimer.current);
    await flush();
    setWriting(section.id);
    try {
      setDoc(await writeApi.writeSection(doc!.id, section.id, instruction[section.id] || ""));
      toast(t("wrSectionWritten"));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    } finally {
      setWriting(null);
    }
  }

  async function checkSectionClaims(section: Section) {
    await flush();
    setClaims((current) => ({ ...current, [section.id]: "busy" }));
    try {
      const result = await writeApi.claims({ text: section.text, document_id: doc!.id, language });
      setClaims((current) => ({ ...current, [section.id]: result }));
    } catch (caught) {
      setClaims((current) => { const next = { ...current }; delete next[section.id]; return next; });
      toast(errorTextFor(t, caught));
    }
  }

  async function runCheck() {
    await flush();
    try {
      const result = await writeApi.check(doc!.id);
      setCheck(result);
      setDoc(await writeApi.get(doc!.id));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }

  async function exportAs(format: "docx" | "markdown" | "latex" | "pdf") {
    await flush();
    try {
      const rtl = directionOf(doc!.language) === "rtl";
      const result = await writeApi.exportDoc(doc!.id, format === "pdf" ? "html" : format, rtl, t("wrReferences"));
      if (format === "pdf") {
        printHtml(result.content || "");
      } else if (result.base64) {
        const bytes = Uint8Array.from(atob(result.base64), (character) => character.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], { type: result.mime }));
        const anchor = document.createElement("a");
        anchor.href = url; anchor.download = result.filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else {
        download(result.content || "", result.filename, result.mime);
        if (result.bib) download(result.bib, result.bib_filename || "references.bib", "application/x-bibtex");
      }
      toast(format === "pdf" ? t("wrPrintReady") : t("wrExported"));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }

  async function openVersions() {
    try {
      setVersions((await writeApi.versions(doc!.id)).versions);
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }

  return (
    <div className="gw-editor">
      <div className="gw-editor-bar">
        <Link to={doc.kind === "review" ? "/writing/reviews" : "/writing/draft"} className="lb-back"><BackGlyph />{doc.kind === "review" ? t("wrTabReviews") : t("wrTabDraft")}</Link>
        <span className="rs-spacer" />
        <span className={`gw-save-state is-${saving}`} role="status">{saving === "saving" ? t("wrSaving") : saving === "error" ? t("wrSaveFailed") : t("wrSavedState")}</span>
        <span className="gw-words">{t("wrWords", { count: formatNumber(words, language) })}</span>
        <Select label={t("libCitationStyle")} value={doc.citation_style} align="end" onChange={(next) => { const value = next as CitationStyle; setDoc({ ...doc, citation_style: value }); queue({ citation_style: value }); }} options={CITATION_STYLES.map((entry) => ({ value: entry.id, label: entry.label }))} />
        {doc.kind === "review" ? (
          <Menu label={t("wrReviewStyle")} trigger={<><span>{t(REVIEW_STYLES.find((entry) => entry.id === doc.style)?.key || "wrStyleThematic")}</span><ChevronGlyph /></>}
            entries={REVIEW_STYLES.map((entry) => ({ label: t(entry.key), checked: doc.style === entry.id, onSelect: () => void writeApi.outline(doc.id, entry.id).then((next) => { setDoc(next); toast(t("wrOutlineRebuilt")); }).catch((caught) => toast(errorTextFor(t, caught))) }))} />
        ) : null}
        <button type="button" className="lb-button lb-button-quiet" onClick={() => void runCheck()}><CheckGlyph />{t("wrCheck")}</button>
        <Menu label={t("wrVersions")} trigger={<><span>{t("wrVersions")}</span><ChevronGlyph /></>} entries={[
          { label: t("wrSaveVersion"), onSelect: () => void flush().then(() => writeApi.saveVersion(doc.id)).then(() => toast(t("wrVersionSaved"))).catch((caught) => toast(errorTextFor(t, caught))) },
          { label: t("wrShowVersions"), onSelect: () => void openVersions() },
        ]} />
        <Menu label={t("libExport")} trigger={<><span>{t("libExport")}</span><ChevronGlyph /></>} entries={[
          { label: "Word (.docx)", onSelect: () => void exportAs("docx") },
          { label: t("wrExportPdf"), onSelect: () => void exportAs("pdf") },
          { label: "Markdown (.md)", onSelect: () => void exportAs("markdown") },
          { label: "LaTeX (.tex + .bib)", onSelect: () => void exportAs("latex") },
        ]} />
      </div>

      {doc.kind === "review" ? <ReviewSteps t={t} doc={doc} onThemes={() => setThemesOpen(true)} /> : null}
      <input className="gw-doc-title" value={doc.title} dir="auto" maxLength={300} aria-label={t("wrDocTitle")} onChange={(event) => { setDoc({ ...doc, title: event.target.value }); if (event.target.value.trim()) queue({ title: event.target.value }); }} />
      {unsupported || check ? (
        <div className={`gw-check${unsupported || check?.broken_markers.length ? " is-warn" : ""}`} role="status">
          {unsupported ? <span>{t("wrUnsupportedTotal", { count: formatNumber(unsupported, language) })}</span> : <span>{t("wrAllSupported")}</span>}
          {check?.broken_markers.length ? <span>{t("wrBrokenMarkers", { list: check.broken_markers.map((n) => `[${n}]`).join(", ") })}</span> : null}
          {check?.uncited_sources.length ? <span>{t("wrUncited", { list: check.uncited_sources.map((n) => `[${n}]`).join(", ") })}</span> : null}
        </div>
      ) : null}

      <div className="gw-editor-grid">
        <nav className="gw-outline" aria-label={t("wrOutline")}>
          <p className="lb-menu-label">{t("wrOutline")}</p>
          <ol>
            {doc.sections.map((section) => (
              <li key={section.id}><a href={`#sec-${section.id}`} onClick={(event) => { event.preventDefault(); document.getElementById(`sec-${section.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
                <span className={`gw-status-dot is-${section.text.trim() ? (section.unsupported.length ? "warn" : "ok") : "empty"}`} aria-hidden="true" /><bdi>{section.heading}</bdi>
              </a></li>
            ))}
          </ol>
        </nav>

        <div className="gw-sections">
          {doc.sections.map((section) => (
            <section key={section.id} id={`sec-${section.id}`} className="gw-section" aria-label={section.heading}>
              <input className="gw-section-heading" value={section.heading} dir="auto" maxLength={300} aria-label={t("wrSectionHeading")} onChange={(event) => setDoc((current) => { if (!current) return current; const sections = current.sections.map((entry) => entry.id === section.id ? { ...entry, heading: event.target.value } : entry); queue({ sections }); return { ...current, sections }; })} />
              <AutoTextarea
                value={section.text}
                placeholder={t("wrSectionPlaceholder")}
                label={t("wrSectionText", { heading: section.heading })}
                onFocus={(el) => { focused.current = { id: section.id, el }; }}
                onChange={(value) => editSection(section.id, value)}
              />
              {section.unsupported.length ? (
                <details className="gw-unsupported">
                  <summary>{t("wrUnsupportedCount", { count: section.unsupported.length })}</summary>
                  <ul>{section.unsupported.map((sentence) => <li key={sentence} dir="auto">{sentence}</li>)}</ul>
                  <p className="lb-section-note">{t("wrUnsupportedHint")}</p>
                </details>
              ) : null}
              <div className="gw-section-tools">
                <input value={instruction[section.id] || ""} dir="auto" maxLength={600} onChange={(event) => setInstruction((current) => ({ ...current, [section.id]: event.target.value }))} placeholder={t("wrInstructionPlaceholder")} aria-label={t("wrInstruction")} />
                <button type="button" className="lb-button lb-button-primary gw-small" onClick={() => void writeWithSources(section)} disabled={writing !== null || !sources.some(Boolean)}>
                  <SparkGlyph />{writing === section.id ? t("wrWritingNow") : section.text.trim() ? t("wrRewrite") : t("wrWriteWithSources")}
                </button>
                {section.text.trim() ? (
                  <button type="button" className="lb-button lb-button-quiet gw-small" disabled={claims[section.id] === "busy"} onClick={() => void checkSectionClaims(section)}>
                    {claims[section.id] === "busy" ? t("gapThinking") : t("wrCheckClaims")}
                  </button>
                ) : null}
              </div>
              {claims[section.id] && claims[section.id] !== "busy" ? (
                <div className="gw-section-claims">
                  <div className="lb-section-head"><p className="lb-menu-label">{t("wrClaimsInSection")}</p><button type="button" className="lb-text-button" onClick={() => setClaims((current) => { const next = { ...current }; delete next[section.id]; return next; })}>{t("libClose")}</button></div>
                  <ClaimResults t={t} toast={toast} result={claims[section.id] as ClaimCheck} />
                </div>
              ) : null}
              {section.papers.length && section.papers.length < sources.length ? <p className="gw-section-sources">{t("wrSectionUses", { list: section.papers.map((n) => `[${n}]`).join(" ") })}</p> : null}
            </section>
          ))}
          <p className="lb-section-note">{t("wrGroundedNote")}</p>
        </div>

        <aside className="gw-source-panel" aria-label={t("wrSources")}>
          <div className="gw-source-head"><p className="lb-menu-label">{t("wrSources")}</p><button type="button" className="lb-text-button" onClick={() => setAdding(true)}>+ {t("wrAddSources")}</button></div>
          <p className="lb-section-note gw-small">{t("wrCitationHint")}</p>
          <ol className="gw-source-list">
            {sources.map((source, index) => source ? (
              <li key={index}>
                <button type="button" className="gw-cite-button" onClick={() => insertCitation(index + 1)} title={t("wrInsertCitation")} aria-label={t("wrInsertCitationN", { n: index + 1, title: source.title })}>[{index + 1}]</button>
                <span className="gw-source-text"><bdi className="gw-source-title">{source.title}</bdi><span className="lb-row-meta"><bdi>{[source.authors[0], source.year].filter(Boolean).join(" · ")}</bdi></span>
                  <span className={`gw-coverage${coverage[index + 1] ? "" : " is-none"}`}>{coverage[index + 1] ? t("wrCitedIn", { count: formatNumber(coverage[index + 1], language) }) : t("wrNotCitedYet")}</span></span>
                <ConfirmButton className="lb-text-button gw-source-remove" label="×" confirmLabel={t("libConfirmDelete")} onConfirm={() => void writeApi.removeSource(doc.id, index + 1).then(setDoc).catch((caught) => toast(errorTextFor(t, caught)))} />
              </li>
            ) : null)}
          </ol>
        </aside>
      </div>

      {themesOpen ? <ThemesDialog t={t} language={language} doc={doc} onClose={() => setThemesOpen(false)} onApply={async (chosen) => {
        await flush();
        try {
          setDoc(await writeApi.outline(doc.id, "thematic", chosen));
          setThemesOpen(false);
          toast(t("wrOutlineRebuilt"));
        } catch (caught) {
          toast(errorTextFor(t, caught));
        }
      }} /> : null}
      {versions ? <VersionsDialog t={t} language={language} versions={versions} onClose={() => setVersions(null)} onRestore={(version) => void writeApi.restore(doc.id, version.id).then((next) => { setDoc(next); setVersions(null); toast(t("wrRestored")); }).catch((caught) => toast(errorTextFor(t, caught)))} /> : null}
      {adding ? <AddSourcesDialog ctx={ctx} present={sources.filter(Boolean).map((source) => source!.item_id || "")} items={items} onClose={() => setAdding(false)} onAdd={(ids) => void writeApi.addSources(doc.id, ids).then((next) => { setDoc(next); setAdding(false); toast(t("wrSourcesAdded")); }).catch((caught) => toast(errorTextFor(t, caught)))} /> : null}
      <div className="gw-editor-foot"><ConfirmButton label={t("wrDeleteDocument")} confirmLabel={t("libConfirmDelete")} onConfirm={() => void writeApi.remove(doc.id).then(() => navigate(doc.kind === "review" ? "/writing/reviews" : "/writing/draft"))} /></div>
    </div>
  );
}

function AutoTextarea({ value, onChange, onFocus, placeholder, label }: { value: string; onChange: (value: string) => void; onFocus: (el: HTMLTextAreaElement) => void; placeholder: string; label: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(96, el.scrollHeight)}px`;
  }, [value]);
  return <textarea ref={ref} className="gw-section-text" value={value} dir="auto" placeholder={placeholder} aria-label={label} onFocus={(event) => onFocus(event.currentTarget)} onSelect={(event) => onFocus(event.currentTarget)} onChange={(event) => onChange(event.target.value)} />;
}

function printHtml(content: string) {
  document.getElementById("gw-print-frame")?.remove();
  const frame = document.createElement("iframe");
  frame.id = "gw-print-frame";
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;inset-inline-end:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
  frame.srcdoc = content;
  frame.onload = () => { try { frame.contentWindow?.focus(); frame.contentWindow?.print(); } catch { /* blocked */ } };
  document.body.appendChild(frame);
}

/** The literature-review path (Collect → Screen → Themes → Outline → Write → Check → Export) with live progress. */
function ReviewSteps({ t, doc, onThemes }: { t: SearchT; doc: WriteDoc; onThemes: () => void }) {
  const sources = doc.sources.filter(Boolean).length;
  const written = doc.sections.filter((section) => section.text.trim()).length;
  const unsupported = doc.sections.reduce((sum, section) => sum + section.unsupported.length, 0);
  const steps: Array<{ key: SearchCopyKey; state: "done" | "now" | "todo"; detail?: string; action?: () => void; href?: string }> = [
    { key: "wrStepCollect", state: sources ? "done" : "now", detail: t("wrPaperCount", { count: sources }) },
    { key: "wrStepScreen", state: "done", detail: t("wrOptional"), href: "/writing/screening" },
    { key: "wrStepThemes", state: doc.sections.some((section) => section.purpose === "theme" || section.purpose === "method" || section.purpose === "period") ? "done" : "now", action: onThemes },
    { key: "wrStepOutline", state: doc.sections.length ? "done" : "todo", detail: t("wrSectionsCount", { count: doc.sections.length }) },
    { key: "wrStepWrite", state: written === doc.sections.length && written ? "done" : written ? "now" : "todo", detail: `${written}/${doc.sections.length}` },
    { key: "wrStepCheck", state: written && !unsupported ? "done" : written ? "now" : "todo", detail: unsupported ? t("wrUnsupportedShort", { count: unsupported }) : undefined },
    { key: "wrStepExport", state: written === doc.sections.length && written && !unsupported ? "now" : "todo" },
  ];
  return (
    <ol className="gw-steps" aria-label={t("wrStepsLabel")}>
      {steps.map((step, index) => {
        const body = <><span className={`gw-step-dot is-${step.state}`} aria-hidden="true">{step.state === "done" ? <CheckGlyph /> : index + 1}</span><span className="gw-step-text"><b>{t(step.key)}</b>{step.detail ? <span>{step.detail}</span> : null}</span></>;
        return (
          <li key={step.key} className={`gw-step is-${step.state}`} aria-current={step.state === "now" ? "step" : undefined}>
            {step.action ? <button type="button" className="gw-step-link" onClick={step.action}>{body}</button> : step.href ? <Link className="gw-step-link" to={step.href}>{body}</Link> : <span className="gw-step-link">{body}</span>}
          </li>
        );
      })}
    </ol>
  );
}

/** Quotes that add something: not just the source's own title. */
function usefulThemeQuotes(theme: Theme, doc: WriteDoc) {
  return theme.quotes.filter((quote) => quote.text && normalizedText(quote.text) !== normalizedText(doc.sources[quote.n - 1]?.title || ""));
}

const EVIDENCE_KEYS: Record<Theme["evidence"], SearchCopyKey> = { consistent: "wrEvidenceConsistent", mixed: "wrEvidenceMixed", unclear: "wrEvidenceUnclear" };
const KIND_KEYS: Record<Theme["kind"], SearchCopyKey> = { task: "gapTasks", domain: "wrThemeDomain", method: "gapMethods", dataset: "gapTabDatasets" };

/** Candidate themes from the sources: pick some, see the quotes and whether results agree, then build the outline. */
function ThemesDialog({ t, language, doc, onClose, onApply }: { t: SearchT; language: string; doc: WriteDoc; onClose: () => void; onApply: (themes: Array<{ label: string; papers: number[] }>) => Promise<void> }) {
  const panel = useRef<HTMLDivElement>(null);
  const [themes, setThemes] = useState<Theme[] | null>(null);
  const [error, setError] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  useDismiss(true, [panel], onClose);
  useEffect(() => {
    writeApi.themes(doc.id).then((result) => { setThemes(result.themes); setChosen(new Set(result.themes.slice(0, 5).map((theme) => theme.label))); }).catch(() => setError(true));
  }, [doc.id]);
  const picked = (themes || []).filter((theme) => chosen.has(theme.label));
  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog lb-dialog-wide" role="dialog" aria-modal="true" aria-labelledby="gw-themes-title">
        <h2 id="gw-themes-title">{t("wrThemesTitle")}</h2>
        <p className="lb-dialog-sub">{t("wrThemesNote")}</p>
        {error ? <ErrorLine message={t("libErrorGeneric")} t={t} /> : !themes ? <SkeletonRows rows={3} /> : !themes.length ? <EmptyState title={t("wrNoThemes")} body={t("wrNoThemesBody")} /> : (
          <ul className="gw-themes">
            {themes.map((theme) => {
              const on = chosen.has(theme.label);
              return (
                <li key={`${theme.kind}:${theme.label}`} className={`gw-theme${on ? " is-on" : ""}`}>
                  <label className="lb-pick">
                    <span className="lb-check"><input type="checkbox" checked={on} onChange={() => setChosen((current) => { const next = new Set(current); if (on) next.delete(theme.label); else next.add(theme.label); return next; })} /><span aria-hidden="true"><CheckGlyph /></span></span>
                    <span className="lb-pick-text">
                      <bdi className="lb-pick-title">{theme.label}</bdi>
                      <span className="lb-row-meta">{t(KIND_KEYS[theme.kind])} · {t("wrPaperCount", { count: formatNumber(theme.papers.length, language) })} · {theme.papers.map((n) => `[${n}]`).join(" ")}</span>
                    </span>
                    <span className={`gw-evidence is-${theme.evidence}`}>{t(EVIDENCE_KEYS[theme.evidence])}</span>
                  </label>
                  {on && usefulThemeQuotes(theme, doc).length ? <div className="gw-theme-quotes">{usefulThemeQuotes(theme, doc).slice(0, 2).map((quote) => <blockquote key={quote.n} className="gw-quote" dir="auto">“{quote.text}” <cite>[{quote.n}]</cite></blockquote>)}</div> : null}
                </li>
              );
            })}
          </ul>
        )}
        <div className="lb-dialog-actions">
          <button type="button" className="lb-button lb-button-quiet" onClick={onClose}>{t("libCancel")}</button>
          <button type="button" className="lb-button lb-button-primary" disabled={!picked.length || busy} onClick={() => { setBusy(true); void onApply(picked.map((theme) => ({ label: theme.label, papers: theme.papers }))).finally(() => setBusy(false)); }}>{t("wrUseThemes", { count: picked.length })}</button>
        </div>
      </div>
    </div>
  );
}

function VersionsDialog({ t, language, versions, onClose, onRestore }: { t: SearchT; language: string; versions: Version[]; onClose: () => void; onRestore: (version: Version) => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useDismiss(true, [panel], onClose);
  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog" role="dialog" aria-modal="true" aria-labelledby="gw-versions-title">
        <h2 id="gw-versions-title">{t("wrVersions")}</h2>
        {!versions.length ? <p className="lb-dialog-sub">{t("wrNoVersions")}</p> : (
          <ul className="lb-collection-list">
            {versions.map((version) => (
              <li key={version.id} className="gw-version">
                <span><b>{version.label === "Saved version" ? t("wrSaveVersion") : version.label.startsWith("Before") ? t("wrAutoVersion") : version.label}</b><span className="lb-row-meta">{new Intl.DateTimeFormat(language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(version.created_at))} · {t("wrWords", { count: formatNumber(version.words, language) })}</span></span>
                <ConfirmButton label={t("wrRestore")} confirmLabel={t("wrConfirmRestore")} onConfirm={() => onRestore(version)} />
              </li>
            ))}
          </ul>
        )}
        <div className="lb-dialog-actions"><button type="button" className="lb-button lb-button-quiet" onClick={onClose}>{t("libClose")}</button></div>
      </div>
    </div>
  );
}

function AddSourcesDialog({ ctx, present, items, onClose, onAdd }: { ctx: Ctx; present: string[]; items: LibraryItem[]; onClose: () => void; onAdd: (ids: string[]) => void }) {
  const { t } = ctx;
  const [choice, setChoice] = useState<SourceChoice & { scope: string }>({ scope: "pick", item_ids: [] });
  const panel = useRef<HTMLDivElement>(null);
  useDismiss(true, [panel], onClose);
  const fresh = choice.item_ids.filter((id) => !present.includes(id));
  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog lb-dialog-wide" role="dialog" aria-modal="true" aria-labelledby="gw-add-title">
        <h2 id="gw-add-title">{t("wrAddSources")}</h2>
        <SourcePicker ctx={{ ...ctx, items: items.filter((item) => !present.includes(item.id)) }} value={choice} onChange={setChoice} />
        <div className="lb-dialog-actions">
          <button type="button" className="lb-button lb-button-quiet" onClick={onClose}>{t("libCancel")}</button>
          <button type="button" className="lb-button lb-button-primary" disabled={!fresh.length} onClick={() => onAdd(fresh)}>{t("libAddCount", { count: fresh.length })}</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- screening

function ScreeningsView({ ctx }: { ctx: Ctx }) {
  const { t, language, toast } = ctx;
  const navigate = useNavigate();
  const [list, setList] = useState<Screening[] | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [criteria, setCriteria] = useState("");
  const [sources, setSources] = useState<SourceChoice & { scope: string }>({ scope: "pick", item_ids: [] });
  useEffect(() => {
    writeApi.screenings().then((result) => setList(result.screenings)).catch((caught) => setError(errorTextFor(t, caught)));
  }, [t]);
  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const screening = await writeApi.createScreening({ name: name.trim(), criteria, project_id: sources.project_id || null, item_ids: sources.item_ids });
      navigate(`/writing/screening/${screening.id}`);
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }
  return (
    <div className="lb-section">
      <div className="lb-section-head">
        <p className="lb-section-note">{t("wrScreeningIntro")}</p>
        {!creating ? <button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{t("wrNewScreening")}</button> : null}
      </div>
      {creating ? (
        <form className="lb-panel gw-create" onSubmit={(event) => void create(event)}>
          <label className="lb-field"><span>{t("wrScreeningName")}</span><input autoFocus value={name} maxLength={200} dir="auto" onChange={(event) => setName(event.target.value)} placeholder={t("wrScreeningNamePlaceholder")} /></label>
          <label className="lb-field"><span>{t("wrCriteria")}</span><textarea rows={3} value={criteria} dir="auto" maxLength={4000} onChange={(event) => setCriteria(event.target.value)} placeholder={t("wrCriteriaPlaceholder")} /></label>
          <div className="lb-field"><span>{t("wrStartWith")}</span><SourcePicker ctx={ctx} value={sources} onChange={setSources} /></div>
          <p className="lb-section-note">{t("wrImportLater")}</p>
          <div className="lb-form-actions">
            <button type="button" className="lb-button lb-button-quiet" onClick={() => setCreating(false)}>{t("libCancel")}</button>
            <button type="submit" className="lb-button lb-button-primary" disabled={!name.trim()}>{t("wrCreateScreening")}</button>
          </div>
        </form>
      ) : null}
      {error ? <ErrorLine message={error} t={t} /> : null}
      {!list && !error ? <SkeletonRows rows={3} /> : null}
      {list && !list.length && !creating ? <EmptyState icon={<TaskGlyph />} title={t("wrNoScreenings")} body={t("wrNoScreeningsBody")} /> : null}
      {list?.length ? (
        <ul className="lb-collection-list">
          {list.map((screening) => (
            <li key={screening.id}>
              <Link to={`/writing/screening/${screening.id}`} className="lb-collection-row">
                <span className="lb-collection-icon" aria-hidden="true"><TaskGlyph /></span>
                <span className="lb-collection-name"><bdi>{screening.name}</bdi></span>
                <span className="lb-collection-count">{t("wrScreeningMeta", { screened: formatNumber(screening.prisma.screened, language), included: formatNumber(screening.prisma.included, language) })}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

const REASONS: SearchCopyKey[] = ["wrReasonTopic", "wrReasonDesign", "wrReasonPopulation", "wrReasonOutcome", "wrReasonLanguage", "wrReasonNoFullText"];

function ScreeningDetail({ ctx }: { ctx: Ctx }) {
  const { t, language, toast, lists, reloadLibrary } = ctx;
  const { screeningId = "" } = useParams();
  const [screening, setScreening] = useState<Screening | null>(null);
  const [missing, setMissing] = useState(false);
  const [stage, setStage] = useState<"title" | "full" | "included">("title");
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    writeApi.screening(screeningId).then(setScreening).catch(() => setMissing(true));
  }, [screeningId]);

  if (missing) return <EmptyState title={t("libErrorNotFound")} action={<Link className="lb-button lb-button-quiet" to="/writing/screening">{t("wrBack")}</Link>} />;
  if (!screening) return <SkeletonRows rows={5} />;
  const records = (screening.records || []).filter((record) => !record.duplicate_of);
  const shown = stage === "title" ? records : stage === "full" ? records.filter((record) => record.ta_decision === "include") : records.filter((record) => record.ta_decision === "include" && record.ft_decision === "include");

  async function decide(record: ScreeningRecord, changes: Partial<ScreeningRecord>) {
    setScreening((current) => current && ({ ...current, records: current.records?.map((entry) => (entry.id === record.id ? { ...entry, ...changes } : entry)) }));
    try {
      const result = await writeApi.decide(screening!.id, record.id, changes);
      setScreening((current) => current && ({ ...current, prisma: result.prisma, records: current.records?.map((entry) => (entry.id === record.id ? result.record : entry)) }));
    } catch (caught) {
      toast(errorTextFor(t, caught));
      setScreening(await writeApi.screening(screening!.id));
    }
  }

  async function importFile(file: File | undefined) {
    if (!file) return;
    setImporting(true);
    try {
      const result = await writeApi.importRecords(screening!.id, { content: await file.text(), filename: file.name });
      setScreening(result.screening);
      toast(t("wrImported", { added: result.added, duplicates: result.duplicates }));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    } finally {
      setImporting(false);
    }
  }

  async function sendToLibrary(projectId?: string) {
    try {
      const result = await writeApi.toLibrary(screening!.id, projectId);
      toast(t("wrSentToLibrary", { count: result.saved }));
      reloadLibrary();
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }

  const decisionField = stage === "full" ? "ft" : "ta";
  return (
    <div className="lb-section">
      <Link to="/writing/screening" className="lb-back"><BackGlyph />{t("wrTabScreening")}</Link>
      <header className="lb-detail-head">
        <div className="lb-detail-title"><h2><bdi>{screening.name}</bdi></h2>{screening.criteria ? <p dir="auto">{screening.criteria}</p> : null}</div>
        <div className="lb-detail-actions">
          <button type="button" className="lb-button lb-button-quiet" onClick={() => fileRef.current?.click()} disabled={importing}><UploadGlyph />{importing ? t("libImporting") : t("wrImportRecords")}</button>
          <input ref={fileRef} type="file" hidden accept=".bib,.ris,.json,.txt" onChange={(event) => { void importFile(event.target.files?.[0]); event.target.value = ""; }} />
          <Menu label={t("wrToLibrary")} trigger={<><span>{t("wrToLibrary")}</span><ChevronGlyph /></>} disabled={!screening.prisma.included} entries={[
            { label: t("libAllSavedPapers"), onSelect: () => void sendToLibrary() },
            ...lists.filter((list) => list.kind === "project").map((list) => ({ label: t("libProjectOption", { name: list.name }), onSelect: () => void sendToLibrary(list.id) })),
          ]} />
        </div>
      </header>

      <PrismaDiagram t={t} language={language} prisma={screening.prisma} name={screening.name} />

      <div className="lb-subtabs" role="tablist" aria-label={t("wrStages")}>
        {([["title", "wrStageTitle", screening.prisma.screened], ["full", "wrStageFull", screening.prisma.full_text_assessed], ["included", "wrStageIncluded", screening.prisma.included]] as const).map(([id, key, count]) => (
          <button key={id} type="button" role="tab" aria-selected={stage === id} className={stage === id ? "is-active" : ""} onClick={() => setStage(id)}>{t(key)} · {formatNumber(count, language)}</button>
        ))}
      </div>

      {!shown.length ? <EmptyState title={records.length ? t("wrStageEmpty") : t("wrNoRecords")} body={records.length ? undefined : t("wrNoRecordsBody")} /> : null}
      <ul className="gw-records">
        {shown.map((record) => {
          const decision = (decisionField === "ft" ? record.ft_decision : record.ta_decision) || null;
          const reason = decisionField === "ft" ? record.ft_reason : record.ta_reason;
          return (
            <li key={record.id} className={`gw-record${decision ? ` is-${decision}` : ""}`}>
              <div className="gw-record-main">
                <bdi className="gw-record-title">{record.title}</bdi>
                <p className="lb-row-meta"><bdi>{[record.authors.slice(0, 3).join(", "), record.venue, record.year].filter(Boolean).join(" · ")}</bdi></p>
                {record.abstract && stage !== "included" ? <details className="gw-abstract"><summary>{t("wrAbstract")}</summary><p dir="auto">{record.abstract}</p></details> : null}
              </div>
              {stage !== "included" ? (
                <div className="gw-record-actions">
                  <div className="lb-segmented" role="group" aria-label={t("wrDecision")}>
                    {(["include", "maybe", "exclude"] as Decision[]).map((value) => (
                      <button key={value} type="button" aria-pressed={decision === value} className={`gw-decision-${value}${decision === value ? " is-active" : ""}`} onClick={() => void decide(record, decisionField === "ft" ? { ft_decision: decision === value ? null : value } : { ta_decision: decision === value ? null : value })}>
                        {t(value === "include" ? "wrInclude" : value === "maybe" ? "wrMaybe" : "wrExclude")}
                      </button>
                    ))}
                  </div>
                  {decision === "exclude" ? (
                    <Select label={t("wrReason")} value={reason || ""} onChange={(next) => void decide(record, decisionField === "ft" ? { ft_reason: next } : { ta_reason: next })}
                      options={[{ value: "", label: t("wrChooseReason") }, ...REASONS.map((key) => ({ value: t(key), label: t(key) }))]} />
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function PrismaDiagram({ t, language, prisma, name }: { t: SearchT; language: string; prisma: Prisma; name: string }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const n = (value: number) => formatNumber(value, language);
  const reasons = prisma.full_text_reasons.slice(0, 4).map((entry) => `${entry.reason}: ${n(entry.count)}`);
  const boxes = [
    { x: 20, y: 20, w: 300, label: t("wrPrismaIdentified", { n: n(prisma.identified) }) },
    { x: 20, y: 120, w: 300, label: t("wrPrismaScreened", { n: n(prisma.screened) }) },
    { x: 20, y: 220, w: 300, label: t("wrPrismaAssessed", { n: n(prisma.full_text_assessed) }) },
    { x: 20, y: 320, w: 300, label: t("wrPrismaIncluded", { n: n(prisma.included) }) },
    { x: 380, y: 70, w: 300, label: t("wrPrismaDuplicates", { n: n(prisma.duplicates) }) },
    { x: 380, y: 170, w: 300, label: t("wrPrismaExcludedScreen", { n: n(prisma.screen_excluded) }) },
    { x: 380, y: 270, w: 300, label: t("wrPrismaExcludedFull", { n: n(prisma.full_text_excluded) }), extra: reasons },
  ];
  const svg = (
    <svg ref={svgRef} viewBox="0 0 700 400" className="gw-prisma" role="img" aria-label={t("wrPrisma")} xmlns="http://www.w3.org/2000/svg" direction={directionOf(language)}>
      <defs><marker id="gw-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 10 5 0 10z" fill="currentColor" /></marker></defs>
      {[[170, 70, 170, 120], [170, 170, 170, 220], [170, 270, 170, 320], [170, 95, 380, 95], [170, 195, 380, 195], [170, 295, 380, 295]].map(([x1, y1, x2, y2], index) => (
        <line key={index} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth="1.5" markerEnd="url(#gw-arrow)" />
      ))}
      {boxes.map((box) => (
        <g key={box.label}>
          <rect x={box.x} y={box.y} width={box.w} height={box.extra?.length ? 50 + box.extra.length * 14 : 50} rx="10" className={box.x > 300 ? "gw-prisma-side" : "gw-prisma-main"} />
          <text x={box.x + box.w / 2} y={box.y + 30} textAnchor="middle" className="gw-prisma-text">{box.label}</text>
          {box.extra?.map((line, index) => <text key={line} x={box.x + box.w / 2} y={box.y + 48 + index * 14} textAnchor="middle" className="gw-prisma-small">{line}</text>)}
        </g>
      ))}
    </svg>
  );

  function serialize() {
    const el = svgRef.current;
    if (!el) return "";
    const styles = getComputedStyle(el);
    const clone = el.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("style", `color:${styles.color};font-family:Manrope,Arial,sans-serif;background:#fff`);
    clone.querySelectorAll("rect").forEach((rect) => { rect.setAttribute("fill", rect.getAttribute("class")?.includes("side") ? "#f6f3ee" : "#ffffff"); rect.setAttribute("stroke", "#8a8178"); });
    clone.querySelectorAll("text").forEach((text) => { text.setAttribute("fill", "#1d1a16"); text.setAttribute("font-size", text.getAttribute("class")?.includes("small") ? "11" : "14"); });
    clone.querySelectorAll("line, path").forEach((line) => line.setAttribute("stroke", "#1d1a16"));
    clone.querySelectorAll("marker path").forEach((path) => path.setAttribute("fill", "#1d1a16"));
    return new XMLSerializer().serializeToString(clone);
  }
  function exportSvg() { download(serialize(), "prisma-flow.svg", "image/svg+xml"); }
  function exportPng() {
    const data = serialize();
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1400; canvas.height = 800;
      const context = canvas.getContext("2d")!;
      context.fillStyle = "#ffffff"; context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => { if (!blob) return; const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "prisma-flow.png"; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); });
    };
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(data)}`;
  }
  function exportPdf() { printHtml(`<!doctype html><html><head><meta charset="utf-8"><title>${name.replace(/</g, "")}</title><style>@page{size:A4 landscape;margin:16mm}body{margin:0}svg{width:100%;height:auto}</style></head><body>${serialize()}</body></html>`); }

  return (
    <section className="gw-panel">
      <div className="lb-section-head">
        <h3>{t("wrPrisma")}</h3>
        <Menu label={t("libExport")} trigger={<><span>{t("libExport")}</span><ChevronGlyph /></>} entries={[{ label: "SVG", onSelect: exportSvg }, { label: "PNG", onSelect: exportPng }, { label: "PDF", onSelect: exportPdf }]} />
      </div>
      <div className="gw-prisma-wrap">{svg}</div>
      {prisma.screen_pending || prisma.full_text_pending ? <p className="lb-section-note">{t("wrPending", { screen: n(prisma.screen_pending), full: n(prisma.full_text_pending) })}</p> : null}
    </section>
  );
}

// ---------------------------------------------------------------- check claims

const VERDICT_KEYS: Record<Verdict, SearchCopyKey> = { supported: "wrVerdictSupported", conflicting: "wrVerdictConflicting", mixed: "wrVerdictMixed", not_found: "wrVerdictNotFound" };
const STRENGTH_KEYS: Record<string, SearchCopyKey> = { strong: "gapLevelStrong", moderate: "gapLevelModerate", limited: "gapLevelLimited" };

function ClaimsView({ ctx }: { ctx: Ctx }) {
  const { t, language, toast } = ctx;
  const [text, setText] = useState("");
  const [sources, setSources] = useState<SourceChoice & { scope: string }>({ scope: "all", item_ids: [] });
  const [result, setResult] = useState<ClaimCheck | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (text.trim().length < 5) return;
    setBusy(true);
    try {
      setResult(await writeApi.claims({ text, language, project_id: sources.project_id || null, item_ids: sources.scope === "all" ? [] : sources.item_ids }));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lb-section">
      <p className="lb-section-note">{t("wrClaimsIntro")}</p>
      <form className="lb-panel gw-create" onSubmit={(event) => void run(event)}>
        <label className="lb-field"><span>{t("wrClaimsText")}</span><textarea rows={6} value={text} dir="auto" maxLength={20000} onChange={(event) => setText(event.target.value)} placeholder={t("wrClaimsPlaceholder")} /></label>
        <div className="lb-field"><span>{t("wrCheckAgainst")}</span><SourcePicker ctx={ctx} value={sources} onChange={setSources} /></div>
        <div className="lb-form-actions"><button type="submit" className="lb-button lb-button-primary" disabled={busy || text.trim().length < 5}>{busy ? t("gapThinking") : t("wrCheckClaims")}</button></div>
      </form>
      {busy ? <SkeletonRows rows={3} /> : null}
      {result && !busy ? (
        <>
          <ClaimResults t={t} toast={toast} result={result} />
        </>
      ) : null}
    </div>
  );
}

function ClaimResults({ t, toast, result }: { t: SearchT; toast: (message: string) => void; result: ClaimCheck }) {
  return (
    <>
      {result.mode === "keywords" ? <p className="gw-disclaimer" role="note">{t("wrClaimsKeywords")}</p> : null}
      <ul className="gw-claims">
        {result.claims.map((claim, index) => {
          const source = claim.evidence[0] ? result.sources.find((entry) => entry.n === claim.evidence[0].n) : undefined;
          return (
            <li key={index} className={`gw-claim is-${claim.verdict}`}>
              <div className="gw-signal-head">
                <span className={`gw-verdict gw-verdict-${claim.verdict}`}>{t(VERDICT_KEYS[claim.verdict])}</span>
                {claim.strength ? <span className="lb-badge">{t(STRENGTH_KEYS[claim.strength])}</span> : null}
              </div>
              <p className="gw-claim-text" dir="auto">{claim.claim}</p>
              {claim.evidence[0] ? <blockquote className="gw-quote" dir="auto">{normalizedText(claim.evidence[0].quote) !== normalizedText(source?.title || "") ? <>“{claim.evidence[0].quote}”</> : null}{source ? <cite>[{source.n}] <bdi>{source.title}</bdi>{source.year ? `, ${source.year}` : ""}</cite> : null}</blockquote> : <p className="lb-section-note">{t("wrNoEvidence")}</p>}
              {claim.safer ? (
                <div className="gw-safer">
                  <p><b>{t("wrSaferWording")}</b> <span dir="auto">{claim.safer}</span></p>
                  <button type="button" className="lb-text-button" onClick={() => void navigator.clipboard.writeText(claim.safer || "").then(() => toast(t("wrCopied"))).catch(() => toast(t("libClipboardBlocked")))}><CopyGlyph />{t("cmpCopy")}</button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function normalizedText(text: string) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
