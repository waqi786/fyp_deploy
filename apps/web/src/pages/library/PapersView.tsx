/** Saved papers: filter, sort, reading status, tags, bulk actions, cite, compare, add to projects and collections. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { MAX_COMPARE, readTray, toggleTray } from "../compare/compareTray";
import type { SearchCopyKey } from "../search/copy";
import { libraryApi, type LibraryItem, type ReadingStatus } from "./libraryApi";
import {
  BookGlyph, CheckGlyph, ChevronGlyph, CloseGlyph, CompareGlyph, CopyGlyph, EmptyState, ErrorLine, Menu, MoreGlyph, SearchGlyph, SkeletonRows, StarGlyph,
  STATUS_KEYS, authorLine, countLabel, formatDay, formatNumber, useDismiss, useLib, type MenuEntry,
} from "./ui";

type SortKey = "added" | "opened" | "title" | "year";
const SORTS: Array<{ id: SortKey; key: SearchCopyKey }> = [
  { id: "added", key: "libSortAdded" },
  { id: "opened", key: "libSortOpened" },
  { id: "title", key: "libSortTitle" },
  { id: "year", key: "libSortYear" },
];
const STATUS_FILTERS: Array<{ id: "all" | ReadingStatus; key: SearchCopyKey }> = [
  { id: "all", key: "libFilterAll" },
  { id: "to_read", key: "libStatusToRead" },
  { id: "reading", key: "libStatusReading" },
  { id: "read", key: "libStatusRead" },
];

export function PapersView({ items, emptyTitle, emptyBody, emptyAction, listId, listKind, onRemoveFromList, toolbarExtra }: {
  items: LibraryItem[];
  emptyTitle: string;
  emptyBody?: string;
  emptyAction?: ReactNode;
  /** When the view shows one project or collection. */
  listId?: string;
  listKind?: "project" | "collection";
  onRemoveFromList?: () => void;
  toolbarExtra?: ReactNode;
}) {
  const { t, language, lists, loading, error, refresh, setItems, toast, openItem, errorText } = useLib();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | ReadingStatus>("all");
  const [tag, setTag] = useState("");
  const [onlyImportant, setOnlyImportant] = useState(false);
  const [sort, setSort] = useState<SortKey>("added");
  const [selected, setSelected] = useState<string[]>([]);
  const [tagging, setTagging] = useState<{ ids: string[] } | null>(null);

  const tags = useMemo(() => {
    const counts = new Map<string, number>();
    items.forEach((item) => item.tags.forEach((value) => counts.set(value, (counts.get(value) || 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], language));
  }, [items, language]);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(language);
    const filtered = items.filter((item) =>
      (status === "all" || item.status === status) &&
      (!tag || item.tags.includes(tag)) &&
      (!onlyImportant || item.important) &&
      (!needle || [item.title, item.authors.join(" "), item.venue || "", item.tags.join(" "), item.doi || "", String(item.year || "")].join(" ").toLocaleLowerCase(language).includes(needle)),
    );
    const collator = new Intl.Collator(language, { sensitivity: "base", numeric: true });
    return filtered.sort((a, b) => {
      if (sort === "title") return collator.compare(a.title, b.title);
      if (sort === "year") return (b.year || 0) - (a.year || 0) || collator.compare(a.title, b.title);
      if (sort === "opened") return (b.opened_at || "").localeCompare(a.opened_at || "") || b.added_at.localeCompare(a.added_at);
      return b.added_at.localeCompare(a.added_at);
    });
  }, [items, query, status, tag, onlyImportant, sort, language]);

  useEffect(() => {
    setSelected((current) => current.filter((id) => items.some((item) => item.id === id)));
  }, [items]);

  const allVisibleSelected = visible.length > 0 && visible.every((item) => selected.includes(item.id));
  const projects = lists.filter((list) => list.kind === "project");
  const collections = lists.filter((list) => list.kind === "collection");

  function patchLocal(ids: string[], change: (item: LibraryItem) => LibraryItem) {
    setItems((current) => current.map((item) => (ids.includes(item.id) ? change(item) : item)));
  }

  async function update(item: LibraryItem, changes: Partial<Pick<LibraryItem, "status" | "important" | "read_later" | "tags">>, message?: string) {
    patchLocal([item.id], (current) => ({ ...current, ...changes }));
    try {
      const saved = await libraryApi.update(item.id, changes);
      patchLocal([item.id], () => saved);
      if (message) toast(message);
    } catch (caught) {
      patchLocal([item.id], () => item);
      toast(errorText(caught));
    }
  }

  async function bulk(ids: string[], action: Parameters<typeof libraryApi.bulk>[1], value: string | boolean | undefined, message: string) {
    try {
      await libraryApi.bulk(ids, action, value);
      toast(message);
      if (action === "delete") setSelected([]);
      await refresh();
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  async function copyCitation(ids: string[]) {
    try {
      const result = await libraryApi.cite({ item_ids: ids }, "apa");
      await navigator.clipboard.writeText(result.entries.map((entry) => entry.text).join("\n"));
      toast(t("libCitationCopied"));
    } catch (caught) {
      toast(caught instanceof Error && caught.name === "NotAllowedError" ? t("libClipboardBlocked") : errorText(caught));
    }
  }

  function addToCompare(ids: string[]) {
    let added = 0;
    for (const item of items.filter((entry) => ids.includes(entry.id))) {
      if (readTray().some((entry) => entry.key === `lib:${item.id}`)) continue;
      const result = toggleTray({ key: `lib:${item.id}`, title: item.title, authors: item.authors, year: item.year ?? null, venue: item.venue || null, doi: item.doi || null, url: item.url || null, pdf_url: item.pdf_url || null, abstract: item.abstract || null, reader_doc_id: item.reader_doc_id || null, has_pdf: Boolean(item.reader_doc_id) });
      if (result === "full") { toast(t("libCompareFull", { max: MAX_COMPARE })); break; }
      added += 1;
    }
    if (added) toast(t("libAddedToCompare", { count: added }));
    return added;
  }

  function listEntries(ids: string[]): MenuEntry[] {
    const entries: MenuEntry[] = [];
    if (projects.length) {
      entries.push({ kind: "label", label: t("libTabProjects") });
      projects.forEach((project) => entries.push({ label: project.name, onSelect: () => void bulk(ids, "add_to_list", project.id, t("libAddedToList", { name: project.name })) }));
    }
    if (collections.length) {
      entries.push({ kind: "label", label: t("libTabCollections") });
      collections.forEach((collection) => entries.push({ label: collection.name, onSelect: () => void bulk(ids, "add_to_list", collection.id, t("libAddedToList", { name: collection.name })) }));
    }
    if (!entries.length) entries.push({ label: t("libNoListsYet"), onSelect: () => navigate("/library/projects"), disabled: false });
    return entries;
  }

  if (loading && !items.length) return <SkeletonRows rows={5} />;
  if (error && !items.length) return <ErrorLine message={error} onRetry={() => void refresh()} t={t} />;

  return (
    <div className="lb-papers">
      <div className="lb-toolbar" role="search">
        <label className="lb-search">
          <SearchGlyph />
          <span className="rs-visually-hidden">{t("libFilterPapers")}</span>
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("libFilterPapers")} dir="auto" />
        </label>
        <div className="lb-segmented" role="group" aria-label={t("libReadingStatus")}>
          {STATUS_FILTERS.map((filter) => (
            <button key={filter.id} type="button" aria-pressed={status === filter.id} className={status === filter.id ? "is-active" : ""} onClick={() => setStatus(filter.id)}>
              {t(filter.key)}
            </button>
          ))}
        </div>
        <button type="button" className={`lb-pill${onlyImportant ? " is-active" : ""}`} aria-pressed={onlyImportant} onClick={() => setOnlyImportant((value) => !value)}>
          <StarGlyph filled={onlyImportant} />{t("libImportant")}
        </button>
        {tags.length ? (
          <Menu
            label={t("libFilterByTag")}
            trigger={<><span>{tag ? `#${tag}` : t("libAllTags")}</span><ChevronGlyph /></>}
            className={tag ? "is-active" : ""}
            entries={[{ label: t("libAllTags"), checked: !tag, onSelect: () => setTag("") }, { kind: "divider" }, ...tags.map(([value, count]) => ({ label: `#${value} · ${formatNumber(count, language)}`, checked: tag === value, onSelect: () => setTag(value) }))]}
          />
        ) : null}
        <span className="rs-spacer" />
        <Menu
          label={t("libSortBy")}
          trigger={<><span>{t(SORTS.find((entry) => entry.id === sort)!.key)}</span><ChevronGlyph /></>}
          entries={SORTS.map((entry) => ({ label: t(entry.key), checked: sort === entry.id, onSelect: () => setSort(entry.id) }))}
        />
        {toolbarExtra}
      </div>

      {items.length === 0 ? (
        <EmptyState icon={<BookGlyph />} title={emptyTitle} body={emptyBody} action={emptyAction} />
      ) : visible.length === 0 ? (
        <EmptyState title={t("libNoMatches")} action={<button type="button" className="lb-button lb-button-quiet" onClick={() => { setQuery(""); setStatus("all"); setTag(""); setOnlyImportant(false); }}>{t("libClearFilters")}</button>} />
      ) : (
        <>
          <div className="lb-list-head">
            <label className="lb-check">
              <input type="checkbox" checked={allVisibleSelected} onChange={() => setSelected(allVisibleSelected ? [] : visible.map((item) => item.id))} aria-label={t("libSelectAll")} />
              <span aria-hidden="true"><CheckGlyph /></span>
            </label>
            <span className="lb-count">{countLabel(t, visible.length, "libPaperCountOne", "libPaperCount", language)}</span>
          </div>
          <ul className="lb-rows">
            {visible.map((item) => (
              <PaperRow
                key={item.id}
                item={item}
                selected={selected.includes(item.id)}
                onSelect={() => setSelected((current) => (current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id]))}
                onStatus={(value) => void update(item, { status: value })}
                onImportant={() => void update(item, { important: !item.important })}
                menu={[
                  { label: t("libOpen"), onSelect: () => openItem(item) },
                  { label: t("libCopyCitation"), onSelect: () => void copyCitation([item.id]) },
                  { label: t("libAddToCompare"), onSelect: () => { if (addToCompare([item.id])) navigate("/comparison?from=tray"); } },
                  { label: item.read_later ? t("libRemoveReadLater") : t("libAddReadLater"), onSelect: () => void update(item, { read_later: !item.read_later }, item.read_later ? t("libRemovedReadLater") : t("libAddedReadLater")) },
                  { label: t("libEditTags"), onSelect: () => setTagging({ ids: [item.id] }) },
                  { kind: "divider" },
                  { kind: "label", label: t("libAddTo") },
                  ...listEntries([item.id]),
                  { kind: "divider" },
                  ...(listId && onRemoveFromList ? [{ label: listKind === "project" ? t("libRemoveFromProject") : t("libRemoveFromCollection"), onSelect: () => void bulk([item.id], "remove_from_list", listId, t("libRemovedFromList")).then(onRemoveFromList) } as MenuEntry] : []),
                  { label: t("libRemoveFromLibrary"), danger: true, onSelect: () => void bulk([item.id], "delete", undefined, t("libRemoved")) },
                ]}
                onTagClick={(value) => setTag(value)}
              />
            ))}
          </ul>
        </>
      )}

      {selected.length ? (
        <div className="lb-bulk" role="region" aria-label={t("libSelection")}>
          <strong>{t("libSelectedCount", { count: formatNumber(selected.length, language) })}</strong>
          <Menu up label={t("libMarkAs")} trigger={<><span>{t("libMarkAs")}</span><ChevronGlyph /></>} align="start"
            entries={(["to_read", "reading", "read"] as ReadingStatus[]).map((value) => ({ label: t(STATUS_KEYS[value]), onSelect: () => void bulk(selected, "set_status", value, t("libUpdatedCount", { count: selected.length })) }))} />
          <button type="button" className="lb-button lb-button-quiet" onClick={() => setTagging({ ids: selected })}>{t("libTag")}</button>
          <Menu up label={t("libAddTo")} trigger={<><span>{t("libAddTo")}</span><ChevronGlyph /></>} align="start" entries={listEntries(selected)} />
          <button type="button" className="lb-button lb-button-quiet" onClick={() => { if (addToCompare(selected)) navigate("/comparison?from=tray"); }}><CompareGlyph />{t("libCompare")}</button>
          <button type="button" className="lb-button lb-button-quiet" onClick={() => void copyCitation(selected)}><CopyGlyph />{t("libCite")}</button>
          <span className="rs-spacer" />
          <button type="button" className="lb-button lb-button-danger" onClick={() => void bulk(selected, "delete", undefined, t("libRemovedCount", { count: selected.length }))}>{t("libRemove")}</button>
          <button type="button" className="lb-icon-button" aria-label={t("libClearSelection")} title={t("libClearSelection")} onClick={() => setSelected([])}><CloseGlyph /></button>
        </div>
      ) : null}

      {tagging ? (
        <TagEditor
          key={tagging.ids.join(",")}
          single={tagging.ids.length === 1 ? items.find((item) => item.id === tagging.ids[0]) || null : null}
          suggestions={tags.map(([value]) => value)}
          onClose={() => setTagging(null)}
          onSave={async (next, added) => {
            const ids = tagging.ids;
            setTagging(null);
            if (ids.length === 1) {
              const item = items.find((entry) => entry.id === ids[0]);
              if (item) await update(item, { tags: next }, t("libTagsSaved"));
            } else {
              for (const value of added) await libraryApi.bulk(ids, "add_tag", value).catch(() => undefined);
              toast(t("libTagsSaved"));
              await refresh();
            }
          }}
        />
      ) : null}
    </div>
  );
}

function PaperRow({ item, selected, onSelect, onStatus, onImportant, menu, onTagClick }: {
  item: LibraryItem;
  selected: boolean;
  onSelect: () => void;
  onStatus: (value: ReadingStatus) => void;
  onImportant: () => void;
  menu: MenuEntry[];
  onTagClick: (tag: string) => void;
}) {
  const { t, language, openItem } = useLib();
  const meta = [authorLine(item, t), item.venue, item.year ? String(item.year) : ""].filter(Boolean);
  return (
    <li className={`lb-row${selected ? " is-selected" : ""}`}>
      <label className="lb-check">
        <input type="checkbox" checked={selected} onChange={onSelect} aria-label={t("libSelectPaper", { title: item.title })} />
        <span aria-hidden="true"><CheckGlyph /></span>
      </label>
      <div className="lb-row-main">
        <button type="button" className="lb-row-title" onClick={() => openItem(item)}><bdi>{item.title}</bdi></button>
        {meta.length ? <p className="lb-row-meta"><bdi>{meta.join(" · ")}</bdi></p> : null}
        <div className="lb-row-tags">
          {item.read_later ? <span className="lb-badge">{t("libTabReadLater")}</span> : null}
          {item.tags.map((value) => <button key={value} type="button" className="lb-tag" onClick={() => onTagClick(value)}>#<bdi>{value}</bdi></button>)}
          <span className="lb-row-date">{t("libAddedOn", { date: formatDay(item.added_at, language) })}</span>
        </div>
      </div>
      <div className="lb-row-actions">
        <Menu
          label={t("libReadingStatus")}
          className={`lb-status lb-status-${item.status}`}
          trigger={<><span className="lb-status-dot" aria-hidden="true" />{t(STATUS_KEYS[item.status])}<ChevronGlyph /></>}
          entries={(["to_read", "reading", "read"] as ReadingStatus[]).map((value) => ({ label: t(STATUS_KEYS[value]), checked: item.status === value, onSelect: () => onStatus(value) }))}
        />
        <button type="button" className={`lb-icon-button lb-star${item.important ? " is-on" : ""}`} aria-pressed={item.important} aria-label={t("libMarkImportant")} title={t("libMarkImportant")} onClick={onImportant}>
          <StarGlyph filled={item.important} />
        </button>
        <Menu label={t("libMoreActions")} trigger={<MoreGlyph />} icon entries={menu} />
      </div>
    </li>
  );
}

function TagEditor({ single, suggestions, onClose, onSave }: { single: LibraryItem | null; suggestions: string[]; onClose: () => void; onSave: (tags: string[], added: string[]) => void }) {
  const { t } = useLib();
  const [tags, setTags] = useState<string[]>(single?.tags || []);
  const [draft, setDraft] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  useDismiss(true, [panel], onClose);
  const add = (value: string) => {
    const clean = value.trim().replace(/^#/, "").slice(0, 40);
    if (clean && !tags.some((tag) => tag.toLowerCase() === clean.toLowerCase())) setTags((current) => [...current, clean]);
    setDraft("");
  };
  const original = single?.tags || [];
  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog" role="dialog" aria-modal="true" aria-labelledby="lb-tag-title">
        <h2 id="lb-tag-title">{t("libEditTags")}</h2>
        {single ? <p className="lb-dialog-sub"><bdi>{single.title}</bdi></p> : null}
        <div className="lb-tag-input">
          {tags.map((tag) => (
            <span key={tag} className="lb-tag is-removable">#<bdi>{tag}</bdi><button type="button" aria-label={t("libRemoveTag", { tag })} onClick={() => setTags((current) => current.filter((value) => value !== tag))}><CloseGlyph /></button></span>
          ))}
          <input
            autoFocus
            value={draft}
            dir="auto"
            placeholder={t("libAddTagPlaceholder")}
            aria-label={t("libAddTagPlaceholder")}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === ",") { event.preventDefault(); add(draft); }
              if (event.key === "Backspace" && !draft && tags.length) setTags((current) => current.slice(0, -1));
            }}
          />
        </div>
        {suggestions.filter((value) => !tags.includes(value)).length ? (
          <div className="lb-suggestions">
            {suggestions.filter((value) => !tags.includes(value)).slice(0, 12).map((value) => <button key={value} type="button" className="lb-tag" onClick={() => add(value)}>#<bdi>{value}</bdi></button>)}
          </div>
        ) : null}
        <div className="lb-dialog-actions">
          <button type="button" className="lb-button lb-button-quiet" onClick={onClose}>{t("libCancel")}</button>
          <button type="button" className="lb-button lb-button-primary" onClick={() => { const final = draft.trim() ? [...tags, draft.trim().replace(/^#/, "")] : tags; onSave(final, final.filter((tag) => !original.includes(tag))); }}>{t("libSave")}</button>
        </div>
      </div>
    </div>
  );
}
