/** Pick saved papers to add to a project or collection. */
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { libraryApi } from "./libraryApi";
import { CheckGlyph, SearchGlyph, authorLine, formatNumber, useDismiss, useLib } from "./ui";

export function AddPapersDialog({ listId, listName, memberIds, onClose, onAdded }: { listId: string; listName: string; memberIds: string[]; onClose: () => void; onAdded: () => void }) {
  const { t, language, items, toast, errorText } = useLib();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  useDismiss(true, [panel], onClose);
  const candidates = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(language);
    return items.filter((item) => !memberIds.includes(item.id) && (!needle || `${item.title} ${item.authors.join(" ")} ${item.tags.join(" ")}`.toLocaleLowerCase(language).includes(needle)));
  }, [items, memberIds, query, language]);

  async function add() {
    setBusy(true);
    try {
      await libraryApi.bulk(chosen, "add_to_list", listId);
      toast(t("libAddedToList", { name: listName }));
      onAdded();
      onClose();
    } catch (caught) {
      toast(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog lb-dialog-wide" role="dialog" aria-modal="true" aria-labelledby="lb-add-title">
        <h2 id="lb-add-title">{t("libAddPapersTo", { name: listName })}</h2>
        {items.length === memberIds.length ? (
          <p className="lb-dialog-sub">{t("libAllPapersAdded")} <Link to="/search" className="lb-link">{t("libFindPapers")}</Link></p>
        ) : (
          <>
            <label className="lb-search lb-search-full">
              <SearchGlyph />
              <span className="rs-visually-hidden">{t("libFilterPapers")}</span>
              <input autoFocus type="search" value={query} dir="auto" onChange={(event) => setQuery(event.target.value)} placeholder={t("libFilterPapers")} />
            </label>
            <ul className="lb-pick-list">
              {candidates.slice(0, 200).map((item) => {
                const on = chosen.includes(item.id);
                return (
                  <li key={item.id}>
                    <label className={`lb-pick${on ? " is-on" : ""}`}>
                      <span className="lb-check">
                        <input type="checkbox" checked={on} onChange={() => setChosen((current) => (on ? current.filter((id) => id !== item.id) : [...current, item.id]))} />
                        <span aria-hidden="true"><CheckGlyph /></span>
                      </span>
                      <span className="lb-pick-text"><bdi className="lb-pick-title">{item.title}</bdi><span className="lb-row-meta"><bdi>{[authorLine(item, t), item.year].filter(Boolean).join(" · ")}</bdi></span></span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <div className="lb-dialog-actions">
          <button type="button" className="lb-button lb-button-quiet" onClick={onClose}>{t("libCancel")}</button>
          <button type="button" className="lb-button lb-button-primary" disabled={!chosen.length || busy} onClick={() => void add()}>
            {chosen.length ? t("libAddCount", { count: formatNumber(chosen.length, language) }) : t("libAddPapers")}
          </button>
        </div>
      </div>
    </div>
  );
}
