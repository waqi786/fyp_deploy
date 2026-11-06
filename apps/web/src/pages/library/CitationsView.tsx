/** Citations: a live bibliography in six styles, export in seven formats, and import from files or identifiers. */
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { libraryApi, type CitationEntry, type CitationStyle, type ExportFormat, type ImportResult } from "./libraryApi";
import { ChevronGlyph, CopyGlyph, EmptyState, ErrorLine, Menu, QuoteGlyph, Select, SkeletonRows, UploadGlyph, formatNumber, useDismiss, useLib } from "./ui";

export const STYLES: Array<{ id: CitationStyle; label: string }> = [
  { id: "apa", label: "APA 7" },
  { id: "mla", label: "MLA 9" },
  { id: "chicago", label: "Chicago" },
  { id: "harvard", label: "Harvard" },
  { id: "ieee", label: "IEEE" },
  { id: "vancouver", label: "Vancouver" },
];
const FORMATS: Array<{ id: ExportFormat; label: string }> = [
  { id: "bibtex", label: "BibTeX (.bib)" },
  { id: "biblatex", label: "BibLaTeX (.bib)" },
  { id: "ris", label: "RIS (.ris)" },
  { id: "endnote", label: "EndNote (.enw)" },
  { id: "csljson", label: "CSL-JSON (.json)" },
  { id: "markdown", label: "Markdown (.md)" },
  { id: "text", label: "Text (.txt)" },
];
const STYLE_KEY = "resora-library-style";

function readStyle(): CitationStyle {
  try {
    const value = window.localStorage.getItem(STYLE_KEY) as CitationStyle | null;
    return STYLES.some((style) => style.id === value) ? value! : "apa";
  } catch {
    return "apa";
  }
}

export function download(content: string, filename: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function CitationsView({ onImport }: { onImport: () => void }) {
  const { t, language, items, lists, toast, errorText } = useLib();
  const [style, setStyle] = useState<CitationStyle>(readStyle);
  const [scope, setScope] = useState("");
  const [entries, setEntries] = useState<CitationEntry[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    try { window.localStorage.setItem(STYLE_KEY, style); } catch { /* per-browser preference only */ }
  }, [style]);

  useEffect(() => {
    if (!items.length) { setEntries([]); return; }
    let cancelled = false;
    setError("");
    libraryApi.cite(scope ? { list_id: scope } : {}, style)
      .then((result) => { if (!cancelled) setEntries(result.entries); })
      .catch((caught) => { if (!cancelled) setError(errorText(caught)); });
    return () => { cancelled = true; };
  }, [style, scope, items]);

  async function copyAll() {
    if (!entries?.length) return;
    try {
      await navigator.clipboard.writeText(entries.map((entry) => entry.text).join("\n"));
      toast(t("libBibliographyCopied"));
    } catch {
      toast(t("libClipboardBlocked"));
    }
  }

  async function exportAs(format: ExportFormat) {
    try {
      const result = await libraryApi.exportCitations(scope ? { list_id: scope } : {}, format, style);
      download(result.content, result.filename, result.mime);
      toast(t("libExported", { count: formatNumber(result.count, language) }));
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  if (!items.length) {
    return <EmptyState icon={<QuoteGlyph />} title={t("libNoCitations")} body={t("libNoCitationsBody")} action={<button type="button" className="lb-button lb-button-primary" onClick={onImport}><UploadGlyph />{t("libImportReferences")}</button>} />;
  }

  return (
    <div className="lb-section">
      <div className="lb-toolbar">
        <div className="lb-segmented lb-segmented-scroll" role="group" aria-label={t("libCitationStyle")}>
          {STYLES.map((entry) => <button key={entry.id} type="button" aria-pressed={style === entry.id} className={style === entry.id ? "is-active" : ""} onClick={() => setStyle(entry.id)}>{entry.label}</button>)}
        </div>
        <Select label={t("libCiteFrom")} value={scope} onChange={setScope}
          options={[{ value: "", label: t("libAllSavedPapers") }, ...lists.filter((list) => list.kind === "project").map((list) => ({ value: list.id, label: t("libProjectOption", { name: list.name }) })), ...lists.filter((list) => list.kind === "collection").map((list) => ({ value: list.id, label: t("libCollectionOption", { name: list.name }) }))]} />
        <span className="rs-spacer" />
        <button type="button" className="lb-button lb-button-quiet" onClick={onImport}><UploadGlyph />{t("libImport")}</button>
        <Menu label={t("libExport")} trigger={<><span>{t("libExport")}</span><ChevronGlyph /></>} entries={FORMATS.map((format) => ({ label: format.label, onSelect: () => void exportAs(format.id) }))} />
        <button type="button" className="lb-button lb-button-primary" onClick={() => void copyAll()} disabled={!entries?.length}><CopyGlyph />{t("libCopyAll")}</button>
      </div>
      {error ? <ErrorLine message={error} t={t} /> : null}
      {!entries && !error ? <SkeletonRows rows={4} /> : null}
      {entries && !entries.length ? <EmptyState title={t("libScopeEmpty")} /> : null}
      {entries?.length ? (
        <ol className={`lb-bibliography${style === "ieee" || style === "vancouver" ? " is-numbered" : ""}`} aria-label={t("libBibliography")}>
          {entries.map((entry) => (
            <li key={entry.id} dir="ltr">
              {entry.parts.map((part, index) => (part.italic ? <i key={index}>{part.text}</i> : <span key={index}>{part.text}</span>))}
            </li>
          ))}
        </ol>
      ) : null}
      <p className="lb-section-note">{t("libCitationNote")}</p>
    </div>
  );
}

/** Import .bib / .ris / CSL-JSON files, or DOIs and arXiv ids pasted as text. Duplicates are merged. */
export function ImportDialog({ listId, onClose, onDone }: { listId?: string; onClose: () => void; onDone: (result: ImportResult) => void }) {
  const { t, language, toast, errorText } = useLib();
  const [text, setText] = useState("");
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  useDismiss(!busy, [panel], onClose);

  async function readFile(picked: File | undefined) {
    if (!picked) return;
    if (picked.size > 2_000_000) { setError(t("libFileTooLarge")); return; }
    setError("");
    setFile({ name: picked.name, content: await picked.text() });
  }

  async function submit() {
    const content = file?.content || text;
    if (!content.trim()) return;
    setBusy(true);
    setError("");
    try {
      const imported = await libraryApi.importCitations(content, { filename: file?.name, list_id: listId });
      setResult(imported);
      onDone(imported);
      toast(t("libImportedCount", { count: formatNumber(imported.added, language) }));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog" role="dialog" aria-modal="true" aria-labelledby="lb-import-title">
        <h2 id="lb-import-title">{t("libImportReferences")}</h2>
        {result ? (
          <div className="lb-import-result" role="status">
            <p><strong>{t("libImportedCount", { count: formatNumber(result.added, language) })}</strong></p>
            {result.already_saved ? <p>{t("libImportDuplicates", { count: formatNumber(result.already_saved, language) })}</p> : null}
            {result.not_found.length ? <p>{t("libImportNotFound", { list: result.not_found.join(", ") })}</p> : null}
            <div className="lb-dialog-actions"><button type="button" className="lb-button lb-button-primary" onClick={onClose}>{t("libDone")}</button></div>
          </div>
        ) : (
          <>
            <p className="lb-dialog-sub">{t("libImportHint")}</p>
            <div
              className={`lb-drop${dragging ? " is-dragging" : ""}`}
              onDragOver={(event: DragEvent) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event: DragEvent) => { event.preventDefault(); setDragging(false); void readFile(event.dataTransfer.files?.[0]); }}
            >
              {file ? (
                <p className="lb-drop-file"><bdi>{file.name}</bdi><button type="button" className="lb-text-button" onClick={() => setFile(null)}>{t("libRemove")}</button></p>
              ) : (
                <>
                  <UploadGlyph />
                  <span>{t("libDropFile")}</span>
                  <button type="button" className="lb-button lb-button-quiet" onClick={() => fileRef.current?.click()}>{t("libChooseFile")}</button>
                </>
              )}
              <input ref={fileRef} type="file" hidden accept=".bib,.bibtex,.ris,.json,.txt,application/json,text/plain" onChange={(event: ChangeEvent<HTMLInputElement>) => { void readFile(event.target.files?.[0]); event.target.value = ""; }} />
            </div>
            {!file ? (
              <label className="lb-field">
                <span>{t("libPasteIds")}</span>
                <textarea rows={4} value={text} dir="ltr" onChange={(event) => setText(event.target.value)} placeholder={"10.1038/s41586-020-2649-2\n2301.01234"} />
              </label>
            ) : null}
            {error ? <ErrorLine message={error} t={t} /> : null}
            {busy ? <SkeletonRows rows={1} /> : null}
            <div className="lb-dialog-actions">
              <button type="button" className="lb-button lb-button-quiet" onClick={onClose} disabled={busy}>{t("libCancel")}</button>
              <button type="button" className="lb-button lb-button-primary" onClick={() => void submit()} disabled={busy || !(file?.content || text).trim()}>{busy ? t("libImporting") : t("libImport")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
