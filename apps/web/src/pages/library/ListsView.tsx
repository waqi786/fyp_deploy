/** Projects (research workspaces) and Collections (simple paper groups). */
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { SearchCopyKey } from "../search/copy";
import { libraryApi, type LibraryList } from "./libraryApi";
import { NotesView } from "./NotesView";
import { PapersView } from "./PapersView";
import { TasksView } from "./TasksView";
import { AddPapersDialog } from "./AddPapersDialog";
import { RecommendationsView } from "./RecommendationsView";
import { BackGlyph, ConfirmButton, countLabel, EmptyState, FolderGlyph, PlusGlyph, SkeletonRows, formatDay, formatNumber, useLib } from "./ui";

// ---------------------------------------------------------------- shared create form

function NewListForm({ kind, onCreated, onCancel }: { kind: "project" | "collection"; onCreated: (list: LibraryList) => void; onCancel?: () => void }) {
  const { t, toast, errorText } = useLib();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const list = await libraryApi.createList(kind, name.trim(), description.trim());
      setName("");
      setDescription("");
      onCreated(list);
    } catch (caught) {
      toast(errorText(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="lb-new-list" onSubmit={(event) => void submit(event)}>
      <label className="lb-field">
        <span>{kind === "project" ? t("libProjectName") : t("libCollectionName")}</span>
        <input autoFocus value={name} maxLength={160} dir="auto" onChange={(event) => setName(event.target.value)} placeholder={kind === "project" ? t("libProjectNamePlaceholder") : t("libCollectionNamePlaceholder")} />
      </label>
      {kind === "project" ? (
        <label className="lb-field">
          <span>{t("libProjectGoal")}</span>
          <input value={description} maxLength={2000} dir="auto" onChange={(event) => setDescription(event.target.value)} placeholder={t("libProjectGoalPlaceholder")} />
        </label>
      ) : null}
      <div className="lb-form-actions">
        {onCancel ? <button type="button" className="lb-button lb-button-quiet" onClick={onCancel}>{t("libCancel")}</button> : null}
        <button type="submit" className="lb-button lb-button-primary" disabled={!name.trim() || busy}>{kind === "project" ? t("libCreateProject") : t("libCreateCollection")}</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- projects

export function ProjectsView() {
  const { t, language, lists, loading, refresh } = useLib();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const projects = lists.filter((list) => list.kind === "project");
  if (loading && !lists.length) return <SkeletonRows rows={3} />;
  return (
    <div className="lb-section">
      <div className="lb-section-head">
        <p className="lb-section-note">{t("libProjectsIntro")}</p>
        {!creating && projects.length ? <button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{t("libNewProject")}</button> : null}
      </div>
      {creating || !projects.length ? (
        <div className={projects.length ? "lb-panel" : ""}>
          {!projects.length && !creating ? (
            <EmptyState icon={<FolderGlyph />} title={t("libNoProjects")} body={t("libNoProjectsBody")} action={<button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{t("libNewProject")}</button>} />
          ) : (
            <NewListForm kind="project" onCancel={() => setCreating(false)} onCreated={(list) => { setCreating(false); void refresh(); navigate(`/library/projects/${list.id}`); }} />
          )}
        </div>
      ) : null}
      {projects.length ? (
        <ul className="lb-project-grid">
          {projects.map((project) => (
            <li key={project.id}>
              <Link to={`/library/projects/${project.id}`} className="lb-project-card">
                <span className="lb-project-name"><bdi>{project.name}</bdi></span>
                {project.description ? <span className="lb-project-goal"><bdi>{project.description}</bdi></span> : null}
                <span className="lb-project-stats">
                  <span><b>{formatNumber(project.stats?.papers || 0, language)}</b>{t("libStatPapers")}</span>
                  <span><b>{formatNumber(project.stats?.to_read || 0, language)}</b>{t("libStatusToRead")}</span>
                  <span><b>{formatNumber(project.stats?.notes || 0, language)}</b>{t("libStatNotes")}</span>
                  <span><b>{formatNumber(project.stats?.tasks_open || 0, language)}</b>{t("libStatTasks")}</span>
                </span>
                <span className="lb-project-updated">{t("libUpdatedOn", { date: formatDay(project.updated_at, language) })}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

type ProjectSection = "papers" | "recommended" | "notes" | "ideas" | "tasks";
const PROJECT_SECTIONS: Array<{ id: ProjectSection; key: SearchCopyKey }> = [
  { id: "papers", key: "libStatPapers" },
  { id: "recommended", key: "libRecTab" },
  { id: "notes", key: "libTabNotes" },
  { id: "ideas", key: "libTabIdeas" },
  { id: "tasks", key: "libTabTasks" },
];

export function ProjectDetail() {
  const { projectId = "" } = useParams();
  return <ListDetail key={projectId} listId={projectId} kind="project" />;
}

export function CollectionDetail() {
  const { collectionId = "" } = useParams();
  return <ListDetail key={collectionId} listId={collectionId} kind="collection" />;
}

function ListDetail({ listId, kind }: { listId: string; kind: "project" | "collection" }) {
  const { t, language, items, refresh, toast, errorText } = useLib();
  const navigate = useNavigate();
  const [list, setList] = useState<LibraryList | null>(null);
  const [missing, setMissing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [section, setSection] = useState<ProjectSection>("papers");
  const [adding, setAdding] = useState(false);

  async function load() {
    try {
      const record = await libraryApi.list(listId);
      if (record.kind !== kind) throw new Error("kind");
      setList(record);
      setName(record.name);
      setDescription(record.description || "");
    } catch {
      setMissing(true);
    }
  }
  useEffect(() => { void load(); }, [listId]);

  const members = useMemo(() => items.filter((item) => item.list_ids.includes(listId)), [items, listId]);
  const back = kind === "project" ? "/library/projects" : "/library/collections";

  if (missing) return <EmptyState title={t("libListMissing")} action={<Link className="lb-button lb-button-quiet" to={back}>{kind === "project" ? t("libBackToProjects") : t("libBackToCollections")}</Link>} />;
  if (!list) return <SkeletonRows rows={3} />;

  async function saveDetails(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const record = await libraryApi.updateList(listId, { name: name.trim(), description: description.trim() });
      setList((current) => ({ ...record, stats: current?.stats }));
      setEditing(false);
      toast(t("libSaved"));
      void refresh();
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  async function remove() {
    try {
      await libraryApi.deleteList(listId);
      toast(kind === "project" ? t("libProjectDeleted") : t("libCollectionDeleted"));
      await refresh();
      navigate(back);
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  const stats = list.stats;
  const reload = () => { void load(); void refresh(); };
  return (
    <div className="lb-section">
      <Link to={back} className="lb-back"><BackGlyph />{kind === "project" ? t("libTabProjects") : t("libTabCollections")}</Link>
      <header className="lb-detail-head">
        {editing ? (
          <form className="lb-new-list lb-inline-edit" onSubmit={(event) => void saveDetails(event)}>
            <label className="lb-field"><span>{kind === "project" ? t("libProjectName") : t("libCollectionName")}</span><input autoFocus value={name} maxLength={160} dir="auto" onChange={(event) => setName(event.target.value)} /></label>
            {kind === "project" ? <label className="lb-field"><span>{t("libProjectGoal")}</span><input value={description} maxLength={2000} dir="auto" onChange={(event) => setDescription(event.target.value)} /></label> : null}
            <div className="lb-form-actions">
              <button type="button" className="lb-button lb-button-quiet" onClick={() => setEditing(false)}>{t("libCancel")}</button>
              <button type="submit" className="lb-button lb-button-primary" disabled={!name.trim()}>{t("libSave")}</button>
            </div>
          </form>
        ) : (
          <>
            <div className="lb-detail-title">
              <h2><bdi>{list.name}</bdi></h2>
              {list.description ? <p><bdi>{list.description}</bdi></p> : null}
            </div>
            <div className="lb-detail-actions">
              <button type="button" className="lb-button lb-button-quiet" onClick={() => setEditing(true)}>{t("libRename")}</button>
              <ConfirmButton label={t("libDelete")} confirmLabel={t("libConfirmDelete")} onConfirm={() => void remove()} />
              <button type="button" className="lb-button lb-button-primary" onClick={() => setAdding(true)}><PlusGlyph />{t("libAddPapers")}</button>
            </div>
          </>
        )}
      </header>

      {kind === "project" && stats ? (
        <dl className="lb-stats" aria-label={t("libOverview")}>
          {([
            ["papers", "libStatPapers"], ["to_read", "libStatusToRead"], ["important", "libImportant"], ["notes", "libStatNotes"], ["ideas", "libTabIdeas"], ["tasks_open", "libStatTasks"],
          ] as Array<[keyof typeof stats, SearchCopyKey]>).map(([key, label]) => (
            <div key={key}><dt>{t(label)}</dt><dd>{formatNumber(stats[key], language)}</dd></div>
          ))}
        </dl>
      ) : null}

      {kind === "project" ? (
        <div className="lb-subtabs" role="tablist" aria-label={t("libProjectSections")}>
          {PROJECT_SECTIONS.map((entry) => (
            <button key={entry.id} type="button" role="tab" aria-selected={section === entry.id} className={section === entry.id ? "is-active" : ""} onClick={() => setSection(entry.id)}>{t(entry.key)}</button>
          ))}
        </div>
      ) : null}

      {section === "papers" || kind === "collection" ? (
        <PapersView
          items={members}
          listId={listId}
          listKind={kind}
          onRemoveFromList={reload}
          emptyTitle={kind === "project" ? t("libProjectEmpty") : t("libCollectionEmpty")}
          emptyBody={t("libListEmptyBody")}
          emptyAction={<button type="button" className="lb-button lb-button-primary" onClick={() => setAdding(true)}><PlusGlyph />{t("libAddPapers")}</button>}
        />
      ) : section === "recommended" ? (
        <RecommendationsView name={list.name} description={list.description} members={members} listId={listId} />
      ) : section === "notes" ? (
        <NotesView kind="note" projectId={listId} onChange={reload} />
      ) : section === "ideas" ? (
        <NotesView kind="idea" projectId={listId} onChange={reload} />
      ) : (
        <TasksView projectId={listId} onChange={reload} />
      )}

      {adding ? <AddPapersDialog listId={listId} listName={list.name} memberIds={members.map((item) => item.id)} onClose={() => setAdding(false)} onAdded={reload} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------- collections

export function CollectionsView() {
  const { t, language, lists, loading, refresh } = useLib();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const collections = lists.filter((list) => list.kind === "collection");
  if (loading && !lists.length) return <SkeletonRows rows={3} />;
  return (
    <div className="lb-section">
      <div className="lb-section-head">
        <p className="lb-section-note">{t("libCollectionsIntro")}</p>
        {!creating && collections.length ? <button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{t("libNewCollection")}</button> : null}
      </div>
      {creating ? <div className="lb-panel"><NewListForm kind="collection" onCancel={() => setCreating(false)} onCreated={(list) => { setCreating(false); void refresh(); navigate(`/library/collections/${list.id}`); }} /></div> : null}
      {!collections.length && !creating ? (
        <EmptyState icon={<FolderGlyph />} title={t("libNoCollections")} body={t("libNoCollectionsBody")} action={<button type="button" className="lb-button lb-button-primary" onClick={() => setCreating(true)}><PlusGlyph />{t("libNewCollection")}</button>} />
      ) : (
        <ul className="lb-collection-list">
          {collections.map((collection) => (
            <li key={collection.id}>
              <Link to={`/library/collections/${collection.id}`} className="lb-collection-row">
                <span className="lb-collection-icon" aria-hidden="true"><FolderGlyph /></span>
                <span className="lb-collection-name"><bdi>{collection.name}</bdi></span>
                <span className="lb-collection-count">{countLabel(t, collection.item_count, "libPaperCountOne", "libPaperCount", language)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
