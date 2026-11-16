/**
 * LaTeX Studio (/studio): Overleaf-style paper editor. Projects from journal templates (IEEE, ACM, Springer, Elsevier,
 * APA, thesis, slides), files + image upload, LaTeX editor with line numbers and snippets, autosave with conflict
 * protection, compile to PDF with clickable error lines, convert to another journal format, exports (PDF, LaTeX ZIP,
 * Word, HTML, Markdown), version history and sharing with a team. Import a Write draft as a paper.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { comparisonHeaders } from "./compare/compareApi";
import { LibraryError, libraryApiBase } from "./library/libraryApi";
import { formatNumber } from "./library/ui";
import { errorText, formatDateTime, PageShell, usePlatform } from "./platform/shared";
import type { SearchCopyKey, SearchT } from "./search/copy";
import "./StudioPage.css";

const base = `${libraryApiBase}/studio`;

type Template = { id: string; name: string; class: string };
type FileRow = { path: string; kind: "text" | "binary"; size: number; version: number; updated_by: string; updated_at: string };
type Project = { id: string; title: string; template: string; team_id: string | null; owner_id: string; main_file: string; access: "owner" | "edit" | "view"; updated_at: string; files?: FileRow[]; templates?: Template[] };
type CompileResult = { ok: boolean; has_pdf?: boolean; errors: Array<{ file: string; line: number | null; message: string }>; warnings: Array<{ line: number | null; message: string }>; seconds: number; pages?: number; exact_class?: boolean; timeout?: boolean };
type HistoryRow = { id: string; version: number; author: string; created_at: string; size: number };
type TeamRow = { id: string; name: string; role: string };

class ConflictError extends LibraryError {
  version: number;
  content: string;
  constructor(version: number, content: string) {
    super("conflict", 409);
    this.version = version;
    this.content = content;
  }
}

async function call<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { ...rest, headers: { ...comparisonHeaders(), ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...(rest.headers || {}) }, body: json !== undefined ? JSON.stringify(json) : rest.body });
  } catch {
    throw new LibraryError("network");
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { code?: string; version?: number; content?: string } } | null)?.detail;
    if (detail?.code === "conflict") throw new ConflictError(detail.version || 0, detail.content || "");
    throw new LibraryError(detail?.code || "unavailable", response.status);
  }
  return (await response.json()) as T;
}

async function blob(path: string): Promise<Blob> {
  const response = await fetch(`${base}${path}`, { headers: comparisonHeaders() });
  if (!response.ok) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { code?: string } } | null)?.detail;
    throw new LibraryError(detail?.code || "unavailable", response.status);
  }
  return response.blob();
}

const studioApi = {
  templates: () => call<{ templates: Template[]; compiler: boolean }>("/templates"),
  projects: () => call<{ projects: Project[] }>("/projects"),
  create: (title: string, template: string, team_id?: string | null) => call<Project>("/projects", { method: "POST", json: { title, template, team_id: team_id || null } }),
  fromWrite: (document_id: string, template: string) => call<Project>("/projects/from-write", { method: "POST", json: { document_id, template } }),
  project: (id: string) => call<Project>(`/projects/${id}`),
  update: (id: string, body: { title?: string; team_id?: string | null; clear_team?: boolean }) => call<Project>(`/projects/${id}`, { method: "PATCH", json: body }),
  remove: (id: string) => call<void>(`/projects/${id}`, { method: "DELETE" }),
  file: (id: string, path: string) => call<FileRow & { content: string | null }>(`/projects/${id}/file?path=${encodeURIComponent(path)}`),
  save: (id: string, path: string, content: string, base_version: number | null) => call<{ path: string; version: number }>(`/projects/${id}/file`, { method: "PUT", json: { path, content, base_version } }),
  upload: (id: string, file: File, folder: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("folder", folder);
    return call<{ path: string }>(`/projects/${id}/upload`, { method: "POST", body: form });
  },
  deleteFile: (id: string, path: string) => call<void>(`/projects/${id}/file?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
  history: (id: string, path: string) => call<{ history: HistoryRow[] }>(`/projects/${id}/history?path=${encodeURIComponent(path)}`),
  restore: (id: string, historyId: string) => call<{ version: number }>(`/projects/${id}/history/${historyId}/restore`, { method: "POST" }),
  convert: (id: string, template: string) => call<Project>(`/projects/${id}/convert`, { method: "POST", json: { template } }),
  compile: (id: string) => call<CompileResult>(`/projects/${id}/compile`, { method: "POST" }),
  pdf: (id: string) => blob(`/projects/${id}/pdf`),
  exportFile: (id: string, format: string) => blob(format === "pdf" ? `/projects/${id}/pdf?download=true` : `/projects/${id}/export?format=${format}`),
  raw: (id: string, path: string) => blob(`/projects/${id}/raw?path=${encodeURIComponent(path)}`),
};

const STUDIO_ERRORS: Record<string, SearchCopyKey> = {
  compiler_unavailable: "stuErrCompiler", converter_unavailable: "stuErrConverter", busy: "stuErrBusy", not_compiled: "stuErrNotCompiled",
  invalid_path: "stuErrPath", unsupported_file: "stuErrUnsupported", file_content_mismatch: "stuErrMismatch", file_too_large: "stuErrTooLarge",
  project_too_large: "stuErrProjectTooLarge", slides_and_papers_differ: "stuErrSlides", cannot_delete_main: "stuErrMain", conversion_failed: "stuErrConversion", forbidden: "stuErrForbidden",
};
function studioError(t: SearchT, caught: unknown) {
  const code = caught instanceof LibraryError ? caught.code : "";
  return STUDIO_ERRORS[code] ? t(STUDIO_ERRORS[code]) : errorText(t, caught);
}

function download(data: Blob, name: string) {
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const SNIPPETS: Array<{ key: SearchCopyKey; text: string }> = [
  { key: "stuSnipSection", text: "\\section{Title}\n" },
  { key: "stuSnipBold", text: "\\textbf{text}" },
  { key: "stuSnipItalic", text: "\\emph{text}" },
  { key: "stuSnipEquation", text: "\\begin{equation}\n  E = mc^2\n  \\label{eq:name}\n\\end{equation}\n" },
  { key: "stuSnipFigure", text: "\\begin{figure}[t]\n  \\centering\n  \\includegraphics[width=0.9\\linewidth]{figure.png}\n  \\caption{Caption.}\n  \\label{fig:name}\n\\end{figure}\n" },
  { key: "stuSnipTable", text: "\\begin{table}[t]\n  \\centering\n  \\caption{Caption.}\n  \\begin{tabular}{lcc}\n    \\toprule\n    A & B & C \\\\\n    \\midrule\n    1 & 2 & 3 \\\\\n    \\bottomrule\n  \\end{tabular}\n\\end{table}\n" },
  { key: "stuSnipList", text: "\\begin{itemize}\n  \\item First\n  \\item Second\n\\end{itemize}\n" },
  { key: "stuSnipCite", text: "~\\cite{key}" },
];

function StudioHome({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [compiler, setCompiler] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [template, setTemplate] = useState("ieee");
  const [drafts, setDrafts] = useState<Array<{ id: string; title: string }>>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    studioApi.projects().then((data) => setProjects(Array.isArray(data?.projects) ? data.projects : [])).catch(setError);
    studioApi.templates().then((data) => { setTemplates(Array.isArray(data?.templates) ? data.templates : []); setCompiler(data?.compiler !== false); }).catch(() => undefined);
    fetch(`${libraryApiBase}/write/documents`, { headers: comparisonHeaders() }).then((response) => (response.ok ? response.json() : [])).then((rows: unknown) => setDrafts(Array.isArray(rows) ? (rows as Array<{ id: string; title: string }>).slice(0, 12) : [])).catch(() => undefined);
  }, []);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const project = await studioApi.create(title.trim() || t("stuUntitled"), template);
      navigate(`/studio/${project.id}`);
    } catch (caught) {
      toast(studioError(t, caught));
    } finally {
      setBusy(false);
    }
  }
  async function importDraft(id: string) {
    try {
      const project = await studioApi.fromWrite(id, template === "beamer" ? "article" : template);
      navigate(`/studio/${project.id}`);
    } catch (caught) {
      toast(studioError(t, caught));
    }
  }
  return (
    <>
      {!compiler ? <p className="pf-empty" role="status">{t("stuErrCompiler")}</p> : null}
      <section className="gw-panel" aria-labelledby="stu-new">
        <h2 id="stu-new">{t("stuNewPaper")}</h2>
        <form className="stu-new" onSubmit={create}>
          <label className="lb-field"><span>{t("stuPaperTitle")}</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={t("stuUntitled")} maxLength={200} /></label>
          <fieldset className="pf-choice"><legend>{t("stuFormat")}</legend>
            {templates.map((item) => <button key={item.id} type="button" role="radio" aria-checked={template === item.id} className={template === item.id ? "is-active" : ""} onClick={() => setTemplate(item.id)}>{t(`stuTpl_${item.id}` as SearchCopyKey)}</button>)}
          </fieldset>
          <button type="submit" className="lb-button lb-button-primary" disabled={busy}>{t("stuCreate")}</button>
        </form>
        {drafts.length ? (
          <div className="stu-import">
            <h3>{t("stuImportTitle")}</h3>
            <p className="gw-small">{t("stuImportNote")}</p>
            <ul className="stu-draft-list">{drafts.map((draft) => <li key={draft.id}><bdi>{draft.title}</bdi><button type="button" className="lb-button" onClick={() => void importDraft(draft.id)}>{t("stuImport")}</button></li>)}</ul>
          </div>
        ) : null}
      </section>
      <section className="gw-panel" aria-labelledby="stu-projects">
        <h2 id="stu-projects">{t("stuYourPapers")}</h2>
        {error ? <p className="pf-empty" role="alert">{studioError(t, error)}</p> : !projects ? <div className="pf-skel" /> : !projects.length ? <p className="pf-empty">{t("stuNoPapers")}</p> : (
          <ul className="stu-project-list">
            {projects.map((project) => (
              <li key={project.id}>
                <Link to={`/studio/${project.id}`}><bdi>{project.title}</bdi></Link>
                <span className="gw-small">{t(`stuTpl_${project.template}` as SearchCopyKey)} · {project.team_id ? t("stuShared") : t("stuPrivate")} · {formatDateTime(project.updated_at, language)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function LineNumbers({ count, errorLines, onJump }: { count: number; errorLines: Set<number>; onJump: (line: number) => void }) {
  return (
    <div className="stu-gutter" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => <span key={index} className={errorLines.has(index + 1) ? "is-error" : ""} onClick={() => onJump(index + 1)}>{index + 1}</span>)}
    </div>
  );
}

function Editor({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [path, setPath] = useState("main.tex");
  const [content, setContent] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "dirty" | "conflict">("saved");
  const [compileResult, setCompileResult] = useState<CompileResult | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ path: string; url: string } | null>(null);
  const [panel, setPanel] = useState<"pdf" | "history" | "share">("pdf");
  const [historyRows, setHistoryRows] = useState<HistoryRow[]>([]);
  const [teams, setTeams] = useState<TeamRow[]>([]);
  const [newFile, setNewFile] = useState("");
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const gutterRef = useRef<HTMLDivElement | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const latest = useRef({ content, version, path });
  useEffect(() => { latest.current = { content, version, path }; });
  const readOnly = project?.access === "view";

  const loadProject = useCallback(() => studioApi.project(projectId).then(setProject).catch(setError), [projectId]);
  useEffect(() => { void loadProject(); }, [loadProject]);

  const openFile = useCallback(async (next: string) => {
    const row = project?.files?.find((file) => file.path === next);
    if (row?.kind === "binary") {
      try {
        const data = await studioApi.raw(projectId, next);
        setPreview((current) => { if (current) URL.revokeObjectURL(current.url); return { path: next, url: URL.createObjectURL(data) }; });
      } catch (caught) {
        toast(studioError(t, caught));
      }
      return;
    }
    try {
      const file = await studioApi.file(projectId, next);
      setPath(next);
      setContent(file.content || "");
      setVersion(file.version);
      setSaveState("saved");
    } catch (caught) {
      toast(studioError(t, caught));
    }
  }, [project?.files, projectId, t, toast]);

  useEffect(() => {
    if (project && version === null) void openFile(project.main_file);
  }, [openFile, project, version]);

  const save = useCallback(async () => {
    const { content: text, version: base, path: file } = latest.current;
    if (readOnly) return;
    setSaveState("saving");
    try {
      const result = await studioApi.save(projectId, file, text, base);
      if (latest.current.path === file) setVersion(result.version);
      setSaveState(latest.current.content === text ? "saved" : "dirty");
    } catch (caught) {
      if (caught instanceof ConflictError) {
        setSaveState("conflict");
        toast(t("stuConflict"));
      } else {
        setSaveState("dirty");
        toast(studioError(t, caught));
      }
    }
  }, [projectId, readOnly, t, toast]);

  function edit(value: string) {
    setContent(value);
    setSaveState("dirty");
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => void save(), 1500); // autosave
  }

  async function takeTheirs() {
    const file = await studioApi.file(projectId, path);
    setContent(file.content || "");
    setVersion(file.version);
    setSaveState("saved");
  }

  async function keepMine() {
    const file = await studioApi.file(projectId, path);
    setVersion(file.version);
    latest.current.version = file.version;
    await save();
  }

  const compile = useCallback(async () => {
    window.clearTimeout(saveTimer.current);
    if (saveState === "dirty") await save();
    setCompiling(true);
    try {
      const result = await studioApi.compile(projectId);
      setCompileResult(result);
      setPanel("pdf");
      if (result.has_pdf) {
        const data = await studioApi.pdf(projectId);
        setPdfUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(data); });
      }
    } catch (caught) {
      toast(studioError(t, caught));
    } finally {
      setCompiling(false);
    }
  }, [projectId, save, saveState, t, toast]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        window.clearTimeout(saveTimer.current);
        void save();
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        void compile();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [compile, save]);

  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  function insert(snippet: string) {
    const area = textRef.current;
    if (!area || readOnly) return;
    const start = area.selectionStart;
    const end = area.selectionEnd;
    const selected = content.slice(start, end);
    const text = selected && /\{text\}/.test(snippet) ? snippet.replace("text", selected) : snippet;
    edit(content.slice(0, start) + text + content.slice(end));
    window.requestAnimationFrame(() => { area.focus(); area.selectionStart = area.selectionEnd = start + text.length; });
  }

  function jumpTo(line: number) {
    const area = textRef.current;
    if (!area) return;
    const lines = content.split("\n");
    const offset = lines.slice(0, Math.max(0, line - 1)).reduce((sum, value) => sum + value.length + 1, 0);
    area.focus();
    area.selectionStart = offset;
    area.selectionEnd = offset + (lines[line - 1]?.length || 0);
    area.scrollTop = Math.max(0, (line - 5) * 20);
  }

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    for (const file of Array.from(files)) {
      try {
        await studioApi.upload(projectId, file, /\.(png|jpe?g|pdf|eps|svg)$/i.test(file.name) ? "images" : "");
        toast(t("stuUploaded", { name: file.name }));
      } catch (caught) {
        toast(studioError(t, caught));
      }
    }
    void loadProject();
  }

  async function createFile(event: React.FormEvent) {
    event.preventDefault();
    const name = newFile.trim();
    if (!name) return;
    const finalName = /\.(tex|bib|sty|txt|md|csv)$/i.test(name) ? name : `${name}.tex`;
    try {
      await studioApi.save(projectId, finalName, finalName.endsWith(".tex") ? "% New section\n" : "", null);
      setNewFile("");
      await loadProject();
      void openFile(finalName);
    } catch (caught) {
      toast(studioError(t, caught));
    }
  }

  async function exportAs(format: string) {
    try {
      if (format === "pdf" && !pdfUrl) await compile();
      const data = await studioApi.exportFile(projectId, format);
      download(data, `${(project?.title || "paper").replace(/[^\w-]+/g, "-")}.${format}`);
    } catch (caught) {
      toast(studioError(t, caught));
    }
  }

  async function convertTo(template: string) {
    if (!project || template === project.template) return;
    try {
      const next = await studioApi.convert(projectId, template);
      setProject(next);
      toast(t("stuConverted", { format: t(`stuTpl_${template}` as SearchCopyKey) }));
      setVersion(null);
    } catch (caught) {
      toast(studioError(t, caught));
    }
  }

  async function openHistory() {
    setPanel("history");
    try {
      setHistoryRows((await studioApi.history(projectId, path)).history);
    } catch (caught) {
      toast(studioError(t, caught));
    }
  }

  async function openShare() {
    setPanel("share");
    try {
      const response = await fetch(`${libraryApiBase}/teams`, { headers: comparisonHeaders() });
      const data = response.ok ? await response.json() : { teams: [] };
      setTeams(Array.isArray(data?.teams) ? data.teams : []);
    } catch {
      setTeams([]);
    }
  }

  const lineCount = useMemo(() => content.split("\n").length, [content]);
  const errorLines = useMemo(() => new Set((compileResult?.errors || []).filter((item) => !item.file || item.file === path).map((item) => item.line || 0)), [compileResult, path]);

  if (error) return <p className="pf-empty" role="alert">{studioError(t, error)} <Link to="/studio">{t("stuBack")}</Link></p>;
  if (!project) return <div className="pf-skel" role="status" aria-label={t("stuLoading")} />;
  const saveLabel = { saved: t("stuSaved"), saving: t("stuSaving"), dirty: t("stuUnsaved"), conflict: t("stuConflictShort") }[saveState];

  return (
    <div className="stu-workspace">
      <div className="stu-toolbar">
        <Link to="/studio" className="lb-link">{t("stuBack")}</Link>
        <b className="stu-title"><bdi>{project.title}</bdi></b>
        <span className={`stu-save is-${saveState}`} role="status">{saveLabel}</span>
        <div className="stu-toolbar-actions">
          <details className="stu-dropdown">
            <summary className="lb-button">{t("stuFormatIs", { format: t(`stuTpl_${project.template}` as SearchCopyKey) })}</summary>
            <div className="stu-dropdown-menu" role="menu" aria-label={t("stuConvert")}>
              <p className="gw-small">{t("stuConvertNote")}</p>
              {(project.templates || []).map((item) => <button key={item.id} type="button" role="menuitemradio" aria-checked={item.id === project.template} disabled={readOnly} onClick={() => void convertTo(item.id)}>{t(`stuTpl_${item.id}` as SearchCopyKey)}</button>)}
            </div>
          </details>
          <details className="stu-dropdown">
            <summary className="lb-button">{t("stuExport")}</summary>
            <div className="stu-dropdown-menu" role="menu" aria-label={t("stuExport")}>
              {[["pdf", "stuExportPdf"], ["zip", "stuExportZip"], ["docx", "stuExportWord"], ["html", "stuExportHtml"], ["md", "stuExportMd"]].map(([format, key]) => (
                <button key={format} type="button" role="menuitem" onClick={() => void exportAs(format)}>{t(key as SearchCopyKey)}</button>
              ))}
            </div>
          </details>
          <button type="button" className="lb-button" onClick={() => void openHistory()}>{t("stuHistory")}</button>
          {project.access === "owner" ? <button type="button" className="lb-button" onClick={() => void openShare()}>{t("stuShare")}</button> : null}
          <button type="button" className="lb-button lb-button-primary stu-compile" onClick={() => void compile()} disabled={compiling} aria-keyshortcuts="Control+Enter">{compiling ? t("stuCompiling") : t("stuCompile")}</button>
        </div>
      </div>
      <div className="stu-grid">
        <aside className="stu-files" aria-label={t("stuFiles")}>
          <h2>{t("stuFiles")}</h2>
          <ul>
            {(project.files || []).map((file) => (
              <li key={file.path} className={file.path === path ? "is-active" : ""}>
                <button type="button" onClick={() => void openFile(file.path)} title={file.path}><span className={`stu-file-icon is-${file.kind}`} aria-hidden="true" /><bdi>{file.path}</bdi></button>
                {!readOnly && file.path !== project.main_file ? <button type="button" className="stu-file-delete" aria-label={t("stuDeleteFile", { name: file.path })} onClick={() => studioApi.deleteFile(projectId, file.path).then(() => loadProject()).catch((caught) => toast(studioError(t, caught)))}>×</button> : null}
              </li>
            ))}
          </ul>
          {!readOnly ? (
            <>
              <label className="stu-upload">
                <input type="file" multiple accept=".png,.jpg,.jpeg,.pdf,.eps,.svg,.tex,.bib,.sty,.cls,.bst,.csv,.txt" onChange={(event) => { void upload(event.target.files); event.target.value = ""; }} />
                <span>{t("stuUpload")}</span>
              </label>
              <p className="gw-small">{t("stuUploadNote")}</p>
              <form className="stu-new-file" onSubmit={createFile}>
                <label className="rs-visually-hidden" htmlFor="stu-new-file">{t("stuNewFile")}</label>
                <input id="stu-new-file" className="lb-input" value={newFile} onChange={(event) => setNewFile(event.target.value)} placeholder={t("stuNewFilePlaceholder")} />
                <button type="submit" className="lb-button">{t("stuAdd")}</button>
              </form>
            </>
          ) : <p className="gw-small">{t("stuReadOnly")}</p>}
        </aside>
        <section className="stu-editor" aria-label={t("stuEditor")}>
          <div className="stu-snippets" role="toolbar" aria-label={t("stuInsert")}>
            {SNIPPETS.map((snippet) => <button key={snippet.key} type="button" disabled={readOnly} onClick={() => insert(snippet.text)}>{t(snippet.key)}</button>)}
          </div>
          {saveState === "conflict" ? (
            <div className="stu-conflict" role="alert">
              <p>{t("stuConflict")}</p>
              <button type="button" className="lb-button" onClick={() => void takeTheirs()}>{t("stuTakeTheirs")}</button>
              <button type="button" className="lb-button" onClick={() => void keepMine()}>{t("stuKeepMine")}</button>
            </div>
          ) : null}
          <div className="stu-code">
            <div ref={gutterRef} className="stu-gutter-wrap"><LineNumbers count={lineCount} errorLines={errorLines} onJump={jumpTo} /></div>
            <textarea
              ref={textRef}
              value={content}
              onChange={(event) => edit(event.target.value)}
              onScroll={(event) => { if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop; }}
              onKeyDown={(event) => {
                if (event.key === "Tab") {
                  event.preventDefault();
                  insert("  ");
                }
              }}
              spellCheck={false}
              readOnly={readOnly}
              dir="ltr"
              lang="en"
              aria-label={t("stuEditorLabel", { file: path })}
              wrap="off"
            />
          </div>
        </section>
        <section className="stu-output" aria-label={t("stuOutput")}>
          {panel === "pdf" ? (
            <>
              {compileResult ? (
                <div className={`stu-result ${compileResult.ok ? "is-ok" : "is-error"}`} role="status">
                  <b>{compileResult.ok ? t("stuCompiled", { pages: formatNumber(compileResult.pages || 0, language), seconds: formatNumber(compileResult.seconds, language) }) : t("stuCompileFailed", { count: formatNumber(compileResult.errors.length, language) })}</b>
                  {compileResult.exact_class === false ? <p className="gw-small">{t("stuPreviewLayout")}</p> : null}
                  {compileResult.errors.length ? (
                    <ul className="stu-errors">{compileResult.errors.map((item, index) => <li key={index}><button type="button" onClick={() => { if (item.file && item.file !== path) void openFile(item.file); if (item.line) window.setTimeout(() => jumpTo(item.line!), 50); }}>{item.line ? t("stuLine", { line: formatNumber(item.line, language) }) : ""} <span dir="ltr">{item.message}</span></button></li>)}</ul>
                  ) : null}
                  {compileResult.warnings.length ? <details><summary>{t("stuWarnings", { count: formatNumber(compileResult.warnings.length, language) })}</summary><ul className="stu-warnings">{compileResult.warnings.map((item, index) => <li key={index} dir="ltr">{item.message}</li>)}</ul></details> : null}
                </div>
              ) : null}
              {preview ? (
                <figure className="stu-image-preview"><figcaption><bdi>{preview.path}</bdi> <button type="button" className="lb-link" onClick={() => { URL.revokeObjectURL(preview.url); setPreview(null); }}>{t("stuClosePreview")}</button></figcaption>{/\.pdf$/i.test(preview.path) ? <iframe title={preview.path} src={preview.url} /> : <img src={preview.url} alt={preview.path} />}<code>{`\\includegraphics[width=0.9\\linewidth]{${preview.path.replace(/^images\//, "")}}`}</code></figure>
              ) : pdfUrl ? <iframe className="stu-pdf" title={t("stuPdfPreview")} src={pdfUrl} /> : <p className="pf-empty">{t("stuNoPdf")}</p>}
            </>
          ) : panel === "history" ? (
            <div className="stu-history">
              <h2>{t("stuHistoryOf", { file: path })}</h2>
              <ul>{historyRows.map((row) => <li key={row.id}><span>{t("stuVersion", { version: formatNumber(row.version, language) })} · <bdi>{row.author}</bdi> · {formatDateTime(row.created_at, language)}</span>{!readOnly ? <button type="button" className="lb-button" onClick={() => studioApi.restore(projectId, row.id).then(() => { toast(t("stuRestored")); void openFile(path); setPanel("pdf"); }).catch((caught) => toast(studioError(t, caught)))}>{t("stuRestore")}</button> : null}</li>)}</ul>
              <button type="button" className="lb-link" onClick={() => setPanel("pdf")}>{t("stuBackToPdf")}</button>
            </div>
          ) : (
            <div className="stu-history">
              <h2>{t("stuShareTitle")}</h2>
              <p className="gw-small">{t("stuShareNote")}</p>
              {teams.length ? (
                <ul>
                  {teams.map((team) => <li key={team.id}><bdi>{team.name}</bdi><button type="button" className="lb-button" aria-pressed={project.team_id === team.id} onClick={() => studioApi.update(projectId, project.team_id === team.id ? { clear_team: true } : { team_id: team.id }).then((next) => { setProject(next); toast(next.team_id ? t("stuSharedWith", { team: team.name }) : t("stuUnshared")); }).catch((caught) => toast(studioError(t, caught)))}>{project.team_id === team.id ? t("stuStopSharing") : t("stuShareWith")}</button></li>)}
                </ul>
              ) : <p className="pf-empty">{t("stuNoTeams")} <Link to="/teams">{t("stuCreateTeam")}</Link></p>}
              <button type="button" className="lb-link" onClick={() => setPanel("pdf")}>{t("stuBackToPdf")}</button>
            </div>
          )}
        </section>
      </div>
      {project.access === "owner" ? (
        <p className="stu-danger"><button type="button" className="lb-link" onClick={() => { if (window.confirm(t("stuDeleteConfirm"))) void studioApi.remove(projectId).then(() => navigate("/studio")).catch((caught) => toast(studioError(t, caught))); }}>{t("stuDeleteProject")}</button></p>
      ) : null}
    </div>
  );
}

export function StudioPage({ interfaceLanguage }: { interfaceLanguage: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  return (
    <PageShell language={interfaceLanguage} title={t("stuTitle")} subtitle={t("stuSubtitle")} toastText={toastText} className="stu-page">
      <Routes>
        <Route index element={<StudioHome t={t} language={interfaceLanguage} toast={toast} />} />
        <Route path=":projectId" element={<Editor t={t} language={interfaceLanguage} toast={toast} />} />
      </Routes>
    </PageShell>
  );
}
