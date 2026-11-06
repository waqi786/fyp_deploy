/** "For you" inside a project: papers worth reading next, each with one reason the user can check
 *  (shared dataset, builds on a saved paper, addresses a noted limitation). Built from the project's own papers. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { SearchCopyKey } from "../search/copy";
import { paperFromItem, recommendFor, type GapPaper, type RecommendationReason } from "../gaps/gapsApi";
import { errorTextFor, openInReader } from "../gaps/shared";
import { libraryApi, type LibraryItem } from "./libraryApi";
import { EmptyState, ErrorLine, SkeletonRows, SparkGlyph, useLib } from "./ui";

const REASONS: Record<RecommendationReason["kind"], SearchCopyKey> = {
  extends: "libRecExtends",
  same_dataset: "libRecSameDataset",
  same_method: "libRecSameMethod",
  similar_topic: "libRecSimilarTopic",
  addresses_limitation: "libRecLimitation",
};

/** A short search query from what the project is about: its name, goal and the words its papers share. */
function projectQuery(name: string, description: string | null | undefined, members: LibraryItem[]) {
  const counts = new Map<string, number>();
  for (const item of members) {
    for (const word of new Set(item.title.toLowerCase().match(/[\p{L}][\p{L}-]{4,}/gu) || [])) counts.set(word, (counts.get(word) || 0) + 1);
  }
  const shared = [...counts.entries()].filter(([, count]) => count >= 2).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([word]) => word);
  return [name, description && description.length < 120 ? description : "", shared.join(" ")].filter(Boolean).join(" ").slice(0, 280);
}

export function RecommendationsView({ name, description, members, listId }: { name: string; description?: string | null; members: LibraryItem[]; listId: string }) {
  const { t, toast, refresh } = useLib();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Array<{ paper: GapPaper; reason: RecommendationReason }> | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!members.length) return;
    let alive = true;
    setRows(null);
    setError("");
    (async () => {
      try {
        const notes = (await libraryApi.notes({ project_id: listId }).catch(() => [])).map((note) => `${note.title || ""} ${note.body || ""}`);
        const result = await recommendFor(members.map(paperFromItem), projectQuery(name, description, members), notes);
        if (alive) setRows(result);
      } catch (caught) {
        if (alive) setError(errorTextFor(t, caught));
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listId, members.length, attempt]);

  async function save(paper: GapPaper) {
    try {
      await libraryApi.save([{ title: paper.title, authors: paper.authors, year: paper.year ?? null, venue: paper.venue || null, doi: paper.doi || null, url: paper.url || null, pdf_url: paper.pdf_url || null, abstract: paper.abstract || null }], { source: "search", list_id: listId });
      setSaved((current) => new Set(current).add(paper.id));
      toast(t("libRecSaved"));
      void refresh();
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }

  if (!members.length) return <EmptyState icon={<SparkGlyph />} title={t("libRecNeedPapers")} />;
  if (error) return <ErrorLine message={error} onRetry={() => setAttempt((value) => value + 1)} t={t} />;
  if (!rows) return <SkeletonRows rows={4} />;
  if (!rows.length) return <EmptyState icon={<SparkGlyph />} title={t("libRecEmpty")} body={t("libRecEmptyBody")} />;
  return (
    <div className="lb-section">
      <p className="lb-section-note">{t("libRecNote")}</p>
      <ul className="lb-rows lb-recs">
        {rows.map(({ paper, reason }) => (
          <li key={paper.id} className="lb-row lb-rec">
            <div className="lb-row-main">
              <button type="button" className="lb-row-title" onClick={() => openInReader(navigate, paper)}><bdi>{paper.title}</bdi></button>
              <span className="lb-row-meta"><bdi>{[paper.authors.slice(0, 3).join(", "), paper.venue, paper.year].filter(Boolean).join(" · ")}</bdi></span>
              <span className="lb-rec-reason"><SparkGlyph />{t(REASONS[reason.kind], { label: reason.label, title: reason.paper_title || t("libRecYourNotes") })}</span>
            </div>
            <div className="lb-row-actions">
              <button type="button" className="lb-button lb-button-quiet" disabled={saved.has(paper.id)} onClick={() => void save(paper)}>{saved.has(paper.id) ? t("gapStateSaved") : t("libSave")}</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
