/** Notes (with an optional quote and page from a paper) and Ideas (with a simple status). */
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { SearchCopyKey } from "../search/copy";
import { libraryApi, type IdeaStatus, type LibraryNote } from "./libraryApi";
import { BulbGlyph, ChevronGlyph, ConfirmButton, EmptyState, ErrorLine, Menu, NoteGlyph, Select, SearchGlyph, SkeletonRows, formatDay, useLib } from "./ui";

const IDEA_STATUS: Record<IdeaStatus, SearchCopyKey> = { new: "libIdeaNew", exploring: "libIdeaExploring", parked: "libIdeaParked", done: "libIdeaDone" };

export function NotesView({ kind, projectId, onChange }: { kind: "note" | "idea"; projectId?: string; onChange?: () => void }) {
  const { t, language, items, lists, toast, errorText, openItem } = useLib();
  const [notes, setNotes] = useState<LibraryNote[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<LibraryNote | null>(null);
  const [ideaFilter, setIdeaFilter] = useState<"open" | IdeaStatus>("open");

  async function load() {
    setError("");
    try {
      setNotes(await libraryApi.notes({ kind, project_id: projectId }));
    } catch (caught) {
      setError(errorText(caught));
    }
  }
  useEffect(() => { void load(); }, [kind, projectId]);

  const projects = lists.filter((list) => list.kind === "project");
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(language);
    return (notes || []).filter((note) =>
      (kind !== "idea" || (ideaFilter === "open" ? note.status !== "done" : note.status === ideaFilter)) &&
      (!needle || `${note.title || ""} ${note.body} ${note.quote || ""}`.toLocaleLowerCase(language).includes(needle)));
  }, [notes, query, language, kind, ideaFilter]);

  async function save(draft: Partial<LibraryNote>, existing?: LibraryNote) {
    try {
      const saved = existing ? await libraryApi.updateNote(existing.id, draft) : await libraryApi.createNote({ ...draft, kind, project_id: projectId || draft.project_id || null });
      setNotes((current) => [saved, ...(current || []).filter((note) => note.id !== saved.id)]);
      setEditing(null);
      toast(existing ? t("libSaved") : kind === "idea" ? t("libIdeaAdded") : t("libNoteAdded"));
      onChange?.();
      return true;
    } catch (caught) {
      toast(errorText(caught));
      return false;
    }
  }

  async function remove(note: LibraryNote) {
    try {
      await libraryApi.deleteNote(note.id);
      setNotes((current) => (current || []).filter((entry) => entry.id !== note.id));
      toast(t("libDeleted"));
      onChange?.();
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  return (
    <div className="lb-section">
      <NoteComposer kind={kind} projectId={projectId} onSubmit={(draft) => save(draft)} />
      {notes && notes.length ? (
        <div className="lb-toolbar">
          <label className="lb-search">
            <SearchGlyph />
            <span className="rs-visually-hidden">{kind === "idea" ? t("libFilterIdeas") : t("libFilterNotes")}</span>
            <input type="search" value={query} dir="auto" onChange={(event) => setQuery(event.target.value)} placeholder={kind === "idea" ? t("libFilterIdeas") : t("libFilterNotes")} />
          </label>
          {kind === "idea" ? (
            <div className="lb-segmented" role="group" aria-label={t("libIdeaStatus")}>
              {(["open", "exploring", "parked", "done"] as const).map((value) => (
                <button key={value} type="button" aria-pressed={ideaFilter === value} className={ideaFilter === value ? "is-active" : ""} onClick={() => setIdeaFilter(value)}>
                  {value === "open" ? t("libIdeaOpen") : t(IDEA_STATUS[value])}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {error ? <ErrorLine message={error} onRetry={() => void load()} t={t} /> : null}
      {!notes && !error ? <SkeletonRows rows={3} /> : null}
      {notes && !notes.length ? (
        <EmptyState icon={kind === "idea" ? <BulbGlyph /> : <NoteGlyph />} title={kind === "idea" ? t("libNoIdeas") : t("libNoNotes")} body={kind === "idea" ? t("libNoIdeasBody") : t("libNoNotesBody")} />
      ) : null}
      {notes && notes.length && !visible.length ? <EmptyState title={t("libNoMatches")} /> : null}
      <ul className="lb-notes">
        {visible.map((note) => {
          const item = items.find((entry) => entry.id === note.item_id);
          const project = projects.find((entry) => entry.id === note.project_id);
          if (editing?.id === note.id) {
            return <li key={note.id} className="lb-note is-editing"><NoteComposer kind={kind} projectId={projectId} initial={note} onSubmit={(draft) => save(draft, note)} onCancel={() => setEditing(null)} /></li>;
          }
          return (
            <li key={note.id} className="lb-note">
              {note.title ? <h3 dir="auto">{note.title}</h3> : null}
              {note.body ? <p className="lb-note-body" dir="auto">{note.body}</p> : null}
              {note.quote ? <blockquote dir="auto">{note.quote}{note.page ? <cite>{t("libPageN", { page: note.page })}</cite> : null}</blockquote> : null}
              <div className="lb-note-foot">
                {kind === "idea" ? (
                  <Menu
                    label={t("libIdeaStatus")}
                    className={`lb-status lb-idea-${note.status || "new"}`}
                    trigger={<><span className="lb-status-dot" aria-hidden="true" />{t(IDEA_STATUS[note.status || "new"])}<ChevronGlyph /></>}
                    align="start"
                    entries={(Object.keys(IDEA_STATUS) as IdeaStatus[]).map((value) => ({ label: t(IDEA_STATUS[value]), checked: (note.status || "new") === value, onSelect: () => void save({ status: value }, note) }))}
                  />
                ) : null}
                {item ? <button type="button" className="lb-chip" onClick={() => openItem(item)}><bdi>{item.title}</bdi></button> : null}
                {project && !projectId ? <span className="lb-chip is-quiet"><bdi>{project.name}</bdi></span> : null}
                <span className="lb-note-date">{formatDay(note.updated_at, language)}</span>
                <span className="rs-spacer" />
                <button type="button" className="lb-text-button" onClick={() => setEditing(note)}>{t("libEdit")}</button>
                <ConfirmButton className="lb-text-button" label={t("libDelete")} confirmLabel={t("libConfirmDelete")} onConfirm={() => void remove(note)} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function NoteComposer({ kind, projectId, initial, onSubmit, onCancel }: {
  kind: "note" | "idea";
  projectId?: string;
  initial?: LibraryNote;
  onSubmit: (draft: Partial<LibraryNote>) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const { t, items, lists } = useLib();
  const [open, setOpen] = useState(Boolean(initial));
  const [title, setTitle] = useState(initial?.title || "");
  const [body, setBody] = useState(initial?.body || "");
  const [quote, setQuote] = useState(initial?.quote || "");
  const [page, setPage] = useState(initial?.page ? String(initial.page) : "");
  const [itemId, setItemId] = useState(initial?.item_id || "");
  const [project, setProject] = useState(initial?.project_id || "");
  const [busy, setBusy] = useState(false);
  const projects = lists.filter((list) => list.kind === "project");
  const empty = !title.trim() && !body.trim() && !quote.trim();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (empty) return;
    setBusy(true);
    const ok = await onSubmit({
      title: title.trim() || null,
      body: body.trim(),
      quote: kind === "note" ? quote.trim() || null : null,
      page: kind === "note" && page ? Number(page) : null,
      item_id: itemId || null,
      ...(projectId ? {} : { project_id: project || null }),
    });
    setBusy(false);
    if (ok && !initial) {
      setTitle(""); setBody(""); setQuote(""); setPage(""); setItemId(""); setProject(""); setOpen(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="lb-composer-collapsed" onClick={() => setOpen(true)}>
        {kind === "idea" ? <BulbGlyph /> : <NoteGlyph />}
        <span>{kind === "idea" ? t("libWriteIdea") : t("libWriteNote")}</span>
      </button>
    );
  }
  return (
    <form className="lb-composer" onSubmit={(event) => void submit(event)}>
      <input className="lb-composer-title" value={title} maxLength={300} dir="auto" autoFocus={!initial} onChange={(event) => setTitle(event.target.value)} placeholder={kind === "idea" ? t("libIdeaTitlePlaceholder") : t("libNoteTitlePlaceholder")} aria-label={t("libTitle")} />
      <textarea value={body} maxLength={20000} dir="auto" rows={kind === "idea" ? 2 : 4} onChange={(event) => setBody(event.target.value)} placeholder={kind === "idea" ? t("libIdeaBodyPlaceholder") : t("libNoteBodyPlaceholder")} aria-label={t("libNoteText")} />
      {kind === "note" ? (
        <div className="lb-composer-quote">
          <input value={quote} maxLength={2000} dir="auto" onChange={(event) => setQuote(event.target.value)} placeholder={t("libQuotePlaceholder")} aria-label={t("libQuote")} />
          <input value={page} inputMode="numeric" pattern="[0-9]*" maxLength={5} onChange={(event) => setPage(event.target.value.replace(/\D/g, ""))} placeholder={t("libPage")} aria-label={t("libPage")} className="lb-page-input" />
        </div>
      ) : null}
      <div className="lb-composer-foot">
        {items.length ? (
          <Select label={t("libLinkPaper")} filterLabel={t("libFilterPapers")} value={itemId} onChange={setItemId} up
            options={[{ value: "", label: t("libNoPaperLinked") }, ...items.slice(0, 500).map((item) => ({ value: item.id, label: item.title.length > 80 ? `${item.title.slice(0, 80)}…` : item.title }))]} />
        ) : null}
        {!projectId && projects.length ? (
          <Select label={t("libProject")} value={project} onChange={setProject} up
            options={[{ value: "", label: t("libNoProject") }, ...projects.map((entry) => ({ value: entry.id, label: entry.name }))]} />
        ) : null}
        <span className="rs-spacer" />
        <button type="button" className="lb-button lb-button-quiet" onClick={() => (onCancel ? onCancel() : setOpen(false))}>{t("libCancel")}</button>
        <button type="submit" className="lb-button lb-button-primary" disabled={empty || busy}>{initial ? t("libSave") : kind === "idea" ? t("libAddIdea") : t("libAddNote")}</button>
      </div>
    </form>
  );
}
