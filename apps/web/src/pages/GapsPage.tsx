/** Gaps — Gap signals · Consensus · Trends · People · Datasets · Ideas.
 *  Scope: a Library project or collection, the whole Library, or a topic (the most relevant papers from Search).
 *  Signals are observations about the evidence with an evidence level and the papers behind every count — never a verdict. */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useSearchCopy, type SearchCopyKey, type SearchT } from "./search/copy";
import { libraryApi, type LibraryList, type LibraryNote } from "./library/libraryApi";
import { BulbGlyph, ChevronGlyph, EmptyState, ErrorLine, Menu, SearchGlyph, SkeletonRows, SparkGlyph, directionOf, formatDay, formatNumber } from "./library/ui";
import { gapsApi, scopePapers, type Analysis, type Consensus, type GapPaper, type Level, type Scope, type Signal, type SignalState, type Stance } from "./gaps/gapsApi";
import { errorTextFor, openInReader } from "./gaps/shared";
import "./SearchPage.css";
import "./LibraryPage.css";
import "./GapsWritePage.css";

type TabId = "signals" | "consensus" | "trends" | "people" | "datasets" | "ideas";
const TABS: Array<{ id: TabId; key: SearchCopyKey }> = [
  { id: "signals", key: "gapTabSignals" },
  { id: "consensus", key: "gapTabConsensus" },
  { id: "trends", key: "gapTabTrends" },
  { id: "people", key: "gapTabPeople" },
  { id: "datasets", key: "gapTabDatasets" },
  { id: "ideas", key: "gapTabIdeas" },
];
const LEVEL_KEYS: Record<Level, SearchCopyKey> = { strong: "gapLevelStrong", moderate: "gapLevelModerate", limited: "gapLevelLimited", hypothesis: "gapLevelHypothesis" };
const LEVEL_HINTS: Record<Level, SearchCopyKey> = { strong: "gapLevelStrongHint", moderate: "gapLevelModerateHint", limited: "gapLevelLimitedHint", hypothesis: "gapLevelHypothesisHint" };
const LAST_KEY = "resora-gaps-last";

function readLast(): Scope | null {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(LAST_KEY) || "null") as Scope | null;
    return value && typeof value.kind === "string" ? value : null;
  } catch {
    return null;
  }
}

export function GapsPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const t = useSearchCopy(interfaceLanguage);
  const location = useLocation();
  const [lists, setLists] = useState<LibraryList[]>([]);
  const [scope, setScope] = useState<Scope | null>(() => readLast());
  const [papers, setPapers] = useState<GapPaper[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [toastText, setToastText] = useState("");
  const timer = useRef<number | undefined>(undefined);

  const toast = useCallback((message: string) => {
    setToastText(message);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToastText(""), 3200);
  }, []);

  useEffect(() => {
    libraryApi.lists().then(setLists).catch(() => undefined);
  }, []);

  const run = useCallback(async (next: Scope) => {
    setScope(next);
    try { window.sessionStorage.setItem(LAST_KEY, JSON.stringify(next)); } catch { /* per-tab convenience only */ }
    setLoading(true);
    setError("");
    try {
      const found = await scopePapers(next);
      setPapers(found);
      if (found.length < 2) {
        setAnalysis(null);
        setError(t("gapNeedPapers"));
        return;
      }
      setAnalysis(await gapsApi.signals(found.slice(0, 300), next));
    } catch (caught) {
      setAnalysis(null);
      setError(errorTextFor(t, caught));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // /gaps?topic=… (for links from Search) wins over the last scope used in this tab.
    const topic = new URLSearchParams(location.search).get("topic")?.trim();
    const last = topic ? ({ kind: "topic", label: topic.slice(0, 300) } as Scope) : readLast();
    if (last) void run(last);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const byId = useMemo(() => new Map(papers.map((paper) => [paper.id, paper])), [papers]);
  const shared = { t, language: interfaceLanguage, scope, papers, byId, analysis, setAnalysis, toast, lists };

  return (
    <section className="rs-search lb-library gw-page" dir={directionOf(interfaceLanguage)} lang={interfaceLanguage} data-no-translate="">
      <div className="lb-shell">
        <header className="lb-head">
          <div className="lb-head-text">
            <h1>{t("gapTitle")}</h1>
            <p className="lb-head-sub">{analysis && scope ? t("gapScopeSummary", { count: formatNumber(analysis.paper_count, interfaceLanguage), scope: scopeName(scope, lists, t) }) : t("gapSubtitle")}</p>
          </div>
        </header>

        <ScopePicker key={scope ? `${scope.kind}:${scope.id || scope.label}` : "none"} t={t} lists={lists} scope={scope} loading={loading} onRun={(next) => void run(next)} />

        <nav className="lb-tabs" aria-label={t("gapTitle")}>
          {TABS.map((tab) => (
            <NavLink key={tab.id} to={`/gaps/${tab.id}`} className={({ isActive }) => `lb-tab${isActive || (tab.id === "signals" && location.pathname.replace(/\/$/, "") === "/gaps") ? " is-active" : ""}`}>
              <span>{t(tab.key)}</span>
              {tab.id === "signals" && analysis ? <span className="lb-tab-count">{formatNumber(analysis.signals.filter((signal) => analysis.states[signal.id] !== "dismissed").length, interfaceLanguage)}</span> : null}
            </NavLink>
          ))}
        </nav>

        <main className="lb-main">
          {error ? <ErrorLine message={error} onRetry={scope ? () => void run(scope) : undefined} t={t} /> : null}
          <Routes>
            <Route index element={<Gate {...shared} loading={loading}><SignalsView {...shared} /></Gate>} />
            <Route path="signals" element={<Gate {...shared} loading={loading}><SignalsView {...shared} /></Gate>} />
            <Route path="consensus" element={<Gate {...shared} loading={loading}><ConsensusView {...shared} /></Gate>} />
            <Route path="trends" element={<Gate {...shared} loading={loading}><TrendsView {...shared} /></Gate>} />
            <Route path="people" element={<Gate {...shared} loading={loading}><PeopleView {...shared} /></Gate>} />
            <Route path="datasets" element={<Gate {...shared} loading={loading}><DatasetsView {...shared} /></Gate>} />
            <Route path="ideas" element={<IdeasView {...shared} />} />
            <Route path="*" element={<Navigate to="/gaps/signals" replace />} />
          </Routes>
        </main>
      </div>
      <div className="lb-toast-region" aria-live="polite">{toastText ? <div className="lb-toast" role="status">{toastText}</div> : null}</div>
    </section>
  );
}

type Shared = {
  t: SearchT;
  language: string;
  scope: Scope | null;
  papers: GapPaper[];
  byId: Map<string, GapPaper>;
  analysis: Analysis | null;
  setAnalysis: (update: (current: Analysis | null) => Analysis | null) => void;
  toast: (message: string) => void;
  lists: LibraryList[];
};

function scopeName(scope: Scope, lists: LibraryList[], t: SearchT) {
  if (scope.kind === "library") return t("gapScopeLibrary");
  if (scope.kind === "topic") return `\u2068“${scope.label}”\u2069`;
  return lists.find((list) => list.id === scope.id)?.name || scope.label;
}

function ScopePicker({ t, lists, scope, loading, onRun }: { t: SearchT; lists: LibraryList[]; scope: Scope | null; loading: boolean; onRun: (scope: Scope) => void }) {
  const [topic, setTopic] = useState(scope?.kind === "topic" ? scope.label : "");
  const projects = lists.filter((list) => list.kind === "project");
  const collections = lists.filter((list) => list.kind === "collection");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (topic.trim().length >= 2) onRun({ kind: "topic", label: topic.trim() });
  };
  return (
    <div className="gw-scope" role="search">
      <form className="gw-scope-topic" onSubmit={submit}>
        <SearchGlyph />
        <input value={topic} dir="auto" onChange={(event) => setTopic(event.target.value)} placeholder={t("gapTopicPlaceholder")} aria-label={t("gapTopicLabel")} />
        <button type="submit" className="lb-button lb-button-primary" disabled={loading || topic.trim().length < 2}>{loading ? t("gapAnalyzing") : t("gapAnalyze")}</button>
      </form>
      <span className="gw-scope-or">{t("gapOrUse")}</span>
      <Menu
        label={t("gapUseLibrary")}
        trigger={<><span>{scope && scope.kind !== "topic" ? scopeName(scope, lists, t) : t("gapUseLibrary")}</span><ChevronGlyph /></>}
        className={scope && scope.kind !== "topic" ? "is-active" : ""}
        entries={[
          { label: t("gapScopeLibrary"), checked: scope?.kind === "library", onSelect: () => onRun({ kind: "library", label: "library" }) },
          ...(projects.length ? [{ kind: "label" as const, label: t("libTabProjects") }, ...projects.map((list) => ({ label: list.name, checked: scope?.id === list.id, onSelect: () => onRun({ kind: "project", id: list.id, label: list.name }) }))] : []),
          ...(collections.length ? [{ kind: "label" as const, label: t("libTabCollections") }, ...collections.map((list) => ({ label: list.name, checked: scope?.id === list.id, onSelect: () => onRun({ kind: "collection", id: list.id, label: list.name }) }))] : []),
        ]}
      />
    </div>
  );
}

function Gate({ analysis, t, children, loading }: Shared & { children: ReactNode; loading: boolean }) {
  if (loading) return <SkeletonRows rows={4} />;
  if (!analysis) return <EmptyState icon={<SparkGlyph />} title={t("gapStartTitle")} body={t("gapStartBody")} />;
  return <>{children}</>;
}

// ---------------------------------------------------------------- signals

function signalTitle(signal: Signal, t: SearchT) {
  const a = signal.a.label;
  const b = signal.b?.label || "";
  switch (signal.kind) {
    case "combination_untested": return t("gapSigUntested", { a, b });
    case "combination_thin": return t("gapSigThin", { a, b });
    case "head_to_head": return t("gapSigHeadToHead", { a, b });
    case "repeated_limitation": return t("gapSigLimitation", { a });
    case "benchmark_concentration": return t("gapSigConcentration", { a });
    case "growing_thin": return t("gapSigGrowing", { a });
    default: return a;
  }
}

function signalCounts(signal: Signal, t: SearchT, language: string) {
  const n = (value: number | undefined) => formatNumber(value || 0, language);
  switch (signal.kind) {
    case "combination_untested":
    case "combination_thin":
      return t("gapCountsCombination", { a: signal.a.label, na: n(signal.counts.a), b: signal.b?.label || "", nb: n(signal.counts.b), both: n(signal.counts.both) });
    case "head_to_head":
      return t("gapCountsHeadToHead", { a: signal.a.label, na: n(signal.counts.a), b: signal.b?.label || "", nb: n(signal.counts.b), shared: (signal.shared || []).join(", ") });
    case "repeated_limitation": return t("gapCountsLimitation", { n: n(signal.counts.a) });
    case "benchmark_concentration": return t("gapCountsConcentration", { n: n(signal.counts.a), of: n(signal.counts.of), share: n(signal.counts.share) });
    case "growing_thin": return t("gapCountsGrowing", { recent: n(signal.counts.recent), n: n(signal.counts.a), since: String(signal.counts.since || "") });
    default: return t("gapCountsHypothesis", { n: n(signal.counts.a) });
  }
}

function SignalsView({ t, language, analysis, setAnalysis, byId, papers, scope, toast, lists }: Shared) {
  const [level, setLevel] = useState<"all" | Level>("all");
  const [showHidden, setShowHidden] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [limit, setLimit] = useState(12);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  if (!analysis || !scope) return null;
  const states = analysis.states;
  const visible = analysis.signals.filter((signal) => (level === "all" || signal.level === level) && (showHidden || !["dismissed", "explored"].includes(states[signal.id] || "")));
  const hiddenCount = analysis.signals.filter((signal) => ["dismissed", "explored"].includes(states[signal.id] || "")).length;
  const projectId = scope.kind === "project" ? scope.id : undefined;

  async function setState(signal: Signal, state: SignalState | null, message: string) {
    const previous = states[signal.id];
    setAnalysis((current) => current && ({ ...current, states: { ...Object.fromEntries(Object.entries(current.states).filter(([key]) => key !== signal.id)), ...(state ? { [signal.id]: state } : {}) } }));
    try {
      await gapsApi.setState(signal.id, analysis!.scope_key, state, { title: signalTitle(signal, t), kind: signal.kind, level: signal.level });
      toast(message);
    } catch (caught) {
      setAnalysis((current) => current && ({ ...current, states: { ...current.states, ...(previous ? { [signal.id]: previous } : {}) } }));
      toast(errorTextFor(t, caught));
    }
  }

  async function toIdea(signal: Signal) {
    try {
      await gapsApi.toIdea(signal.id, analysis!.scope_key, signalTitle(signal, t), [signalCounts(signal, t, language), ...signal.quotes.map((quote) => `“${quote.text}” — ${byId.get(quote.paper_id)?.title || ""}`)].join("\n"), projectId);
      setAnalysis((current) => current && ({ ...current, states: { ...current.states, [signal.id]: "idea" } }));
      toast(t("gapIdeaCreated"));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    }
  }

  async function suggest() {
    setBusy(true);
    try {
      const result = await gapsApi.hypotheses(papers.slice(0, 300), scopeName(scope!, lists, t), analysis!.signals, language);
      setAnalysis((current) => current && ({ ...current, signals: [...result.hypotheses, ...current.signals.filter((signal) => signal.kind !== "ai_hypothesis")] }));
      toast(t("gapHypothesesAdded", { count: result.hypotheses.length }));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lb-section">
      <p className="gw-disclaimer" role="note">{t("gapDisclaimer", { count: formatNumber(analysis.paper_count, language) })}</p>
      <div className="lb-toolbar">
        <div className="lb-segmented lb-segmented-scroll" role="group" aria-label={t("gapEvidenceLevel")}>
          {(["all", "strong", "moderate", "limited", "hypothesis"] as const).map((value) => (
            <button key={value} type="button" aria-pressed={level === value} className={level === value ? "is-active" : ""} onClick={() => setLevel(value)}>
              {value === "all" ? t("libFilterAll") : t(LEVEL_KEYS[value])}
            </button>
          ))}
        </div>
        {hiddenCount ? <button type="button" className={`lb-pill${showHidden ? " is-active" : ""}`} aria-pressed={showHidden} onClick={() => setShowHidden((value) => !value)}>{t("gapShowHidden", { count: hiddenCount })}</button> : null}
        <span className="rs-spacer" />
        <button type="button" className="lb-button lb-button-quiet" onClick={() => void suggest()} disabled={busy || papers.length < 3}><SparkGlyph />{busy ? t("gapThinking") : t("gapSuggestHypotheses")}</button>
      </div>
      {!visible.length ? <EmptyState title={analysis.signals.length ? t("libNoMatches") : t("gapNoSignals")} body={analysis.signals.length ? undefined : t("gapNoSignalsBody")} /> : null}
      <ul className="gw-signals">
        {visible.slice(0, limit).map((signal) => {
          const state = states[signal.id];
          const quotes = usefulQuotes(signal, byId);
          const expanded = open === signal.id;
          const groups = Object.entries(signal.papers).filter(([, ids]) => ids.length);
          return (
            <li key={signal.id} className={`gw-signal${state ? ` is-${state}` : ""}`}>
              <div className="gw-signal-head">
                <span className={`gw-level gw-level-${signal.level}`} title={t(LEVEL_HINTS[signal.level])}>{t(LEVEL_KEYS[signal.level])}</span>
                {state ? <span className="lb-badge">{t(state === "saved" ? "gapStateSaved" : state === "dismissed" ? "gapStateDismissed" : state === "explored" ? "gapStateExplored" : "gapStateIdea")}</span> : null}
              </div>
              <h3 className="gw-signal-title" dir="auto">{signalTitle(signal, t)}</h3>
              {signal.detail ? <p className="gw-signal-detail" dir="auto">{signal.detail}</p> : null}
              <p className="gw-signal-counts">{signalCounts(signal, t, language)}</p>
              {quotes[0] ? <blockquote className="gw-quote" dir="auto">“{quotes[0].text}”<cite><bdi>{byId.get(quotes[0].paper_id)?.title}</bdi></cite></blockquote> : null}
              <div className="gw-signal-actions">
                <button type="button" className="lb-text-button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : signal.id)}>{expanded ? t("gapHidePapers") : t("gapShowPapers")}</button>
                <span className="rs-spacer" />
                <button type="button" className={`lb-button lb-button-quiet gw-small${state === "saved" ? " is-on" : ""}`} aria-pressed={state === "saved"} onClick={() => void setState(signal, state === "saved" ? null : "saved", state === "saved" ? t("gapUnsaved") : t("gapSaved"))}>{state === "saved" ? t("gapStateSaved") : t("gapSave")}</button>
                <button type="button" className="lb-button lb-button-quiet gw-small" onClick={() => void toIdea(signal)} disabled={state === "idea"}><BulbGlyph />{t("gapToIdea")}</button>
                <Menu label={t("libMoreActions")} icon trigger={<span aria-hidden="true">⋯</span>} entries={[
                  { label: t("gapMarkExplored"), checked: state === "explored", onSelect: () => void setState(signal, state === "explored" ? null : "explored", t("gapMarkedExplored")) },
                  { label: state === "dismissed" ? t("gapRestore") : t("gapDismiss"), onSelect: () => void setState(signal, state === "dismissed" ? null : "dismissed", state === "dismissed" ? t("gapRestored") : t("gapDismissed")) },
                ]} />
              </div>
              {expanded ? (
                <>
                <div className="gw-paper-groups">
                  {groups.map(([group, ids]) => (
                    <div key={group}>
                      <p className="gw-group-label">{group === "both" ? t("gapGroupBoth") : group === "a" ? signal.a.label : signal.b?.label || ""} · {formatNumber(ids.length, language)}</p>
                      <ul>{ids.map((id) => { const paper = byId.get(id); return paper ? <li key={id}><button type="button" className="gw-paper-link" onClick={() => openInReader(navigate, paper)}><bdi>{paper.title}</bdi>{paper.year ? <span> · {paper.year}</span> : null}</button></li> : null; })}</ul>
                    </div>
                  ))}
                </div>
                {quotes.length > 1 ? <div className="gw-quote-list">{quotes.slice(1).map((quote) => <blockquote key={quote.paper_id} className="gw-quote" dir="auto">“{quote.text}”<cite><bdi>{byId.get(quote.paper_id)?.title}</bdi></cite></blockquote>)}</div> : null}
                </>
              ) : null}
            </li>
          );
        })}
      </ul>
      {visible.length > limit ? <div className="gw-more"><button type="button" className="lb-button lb-button-quiet" onClick={() => setLimit((value) => value + 12)}>{t("showMoreResults")}</button></div> : null}
    </div>
  );
}

const normalized = (text: string) => text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();

/** Quotes worth showing: not just the paper's own title, and each wording only once. */
function usefulQuotes(signal: Signal, byId: Map<string, GapPaper>) {
  const seen = new Set<string>();
  return signal.quotes.filter((quote) => {
    const text = normalized(quote.text || "");
    const title = normalized(byId.get(quote.paper_id)?.title || "");
    if (!text || text === title || seen.has(text)) return false;
    seen.add(text);
    return true;
  });
}

// ---------------------------------------------------------------- consensus

const STANCE_KEYS: Record<Stance, SearchCopyKey> = { supports: "gapStanceSupports", opposes: "gapStanceOpposes", mixed: "gapStanceMixed", not_addressed: "gapStanceNotAddressed" };

function ConsensusView({ t, language, papers, byId, toast }: Shared) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Consensus | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const sample = useMemo(() => [...papers].sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0) || (b.year || 0) - (a.year || 0)).slice(0, 40), [papers]);

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (question.trim().length < 3) return;
    setBusy(true);
    try {
      setResult(await gapsApi.consensus(question.trim(), sample, language));
    } catch (caught) {
      toast(errorTextFor(t, caught));
    } finally {
      setBusy(false);
    }
  }

  const total = result ? Object.values(result.counts).reduce((sum, value) => sum + value, 0) || 1 : 1;
  return (
    <div className="lb-section">
      <form className="gw-question" onSubmit={(event) => void ask(event)}>
        <input value={question} dir="auto" maxLength={500} onChange={(event) => setQuestion(event.target.value)} placeholder={t("gapConsensusPlaceholder")} aria-label={t("gapConsensusLabel")} />
        <button type="submit" className="lb-button lb-button-primary" disabled={busy || question.trim().length < 3}>{busy ? t("gapThinking") : t("gapCheckConsensus")}</button>
      </form>
      <p className="lb-section-note">{t("gapConsensusNote", { count: formatNumber(sample.length, language) })}</p>
      {busy ? <SkeletonRows rows={4} /> : null}
      {result && !busy ? (
        <>
          <div className="gw-stance-bar" role="img" aria-label={(Object.keys(STANCE_KEYS) as Stance[]).map((stance) => `${t(STANCE_KEYS[stance])}: ${result.counts[stance] || 0}`).join(", ")}>
            {(Object.keys(STANCE_KEYS) as Stance[]).map((stance) => (result.counts[stance] ? <span key={stance} className={`gw-stance-${stance}`} style={{ flexGrow: result.counts[stance] / total }} /> : null))}
          </div>
          <ul className="gw-stance-legend">
            {(Object.keys(STANCE_KEYS) as Stance[]).map((stance) => <li key={stance}><span className={`gw-dot gw-stance-${stance}`} aria-hidden="true" />{t(STANCE_KEYS[stance])} <b>{formatNumber(result.counts[stance] || 0, language)}</b></li>)}
          </ul>
          {result.mode === "keywords" ? <p className="gw-disclaimer" role="note">{t("gapConsensusKeywords")}</p> : null}
          {(["supports", "opposes", "mixed"] as Stance[]).map((stance) => {
            const rows = result.rows.filter((row) => row.stance === stance);
            return rows.length ? (
              <section key={stance} className="gw-stance-group" aria-label={t(STANCE_KEYS[stance])}>
                <h3><span className={`gw-dot gw-stance-${stance}`} aria-hidden="true" />{t(STANCE_KEYS[stance])}</h3>
                <ul>
                  {rows.map((row) => {
                    const paper = byId.get(row.paper_id);
                    return paper ? (
                      <li key={row.paper_id} className="gw-stance-row">
                        <button type="button" className="gw-paper-link" onClick={() => openInReader(navigate, paper)}><bdi>{paper.title}</bdi></button>
                        <p className="lb-row-meta">{[paper.year, paper.venue, paper.study_type, paper.sample_size ? t("gapSampleSize", { n: formatNumber(paper.sample_size, language) }) : ""].filter(Boolean).join(" · ")}</p>
                        {row.reason ? <p className="gw-reason" dir="auto">{row.reason}</p> : null}
                        {row.quote ? <blockquote className="gw-quote" dir="auto">“{row.quote}”</blockquote> : null}
                      </li>
                    ) : null;
                  })}
                </ul>
              </section>
            ) : null;
          })}
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- trends

function BarChart({ rows, label, valueLabel, language }: { rows: Array<{ label: string; value: number }>; label: string; valueLabel: string; language: string }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="gw-chart" role="img" aria-label={label}>
      {rows.map((row) => (
        <div key={row.label} className="gw-bar" title={`${row.label}: ${row.value} ${valueLabel}`}>
          <span className="gw-bar-fill" style={{ blockSize: `${Math.max(2, (row.value / max) * 100)}%` }} />
          <span className="gw-bar-value">{formatNumber(row.value, language)}</span>
          <span className="gw-bar-label">{row.label}</span>
        </div>
      ))}
    </div>
  );
}

function TrendsView({ t, language, analysis }: Shared) {
  const [asTable, setAsTable] = useState(false);
  if (!analysis) return null;
  const { years, series, keywords } = analysis.trends;
  const yearKeys = years.map((row) => String(row.year));
  return (
    <div className="lb-section">
      <div className="lb-toolbar">
        <p className="lb-section-note">{t("gapTrendsNote", { count: formatNumber(analysis.paper_count, language) })}</p>
        <span className="rs-spacer" />
        <button type="button" className={`lb-pill${asTable ? " is-active" : ""}`} aria-pressed={asTable} onClick={() => setAsTable((value) => !value)}>{t("gapViewAsTable")}</button>
      </div>
      {!years.length ? <EmptyState title={t("gapNoYears")} /> : (
        <section className="gw-panel">
          <h3>{t("gapPublications")}</h3>
          {asTable ? (
            <div className="gw-table-wrap"><table className="gw-table"><thead><tr><th>{t("gapYear")}</th><th>{t("libStatPapers")}</th><th>{t("gapCitations")}</th></tr></thead>
              <tbody>{years.map((row) => <tr key={row.year}><td>{row.year}</td><td>{formatNumber(row.papers, language)}</td><td>{formatNumber(row.citations, language)}</td></tr>)}</tbody></table></div>
          ) : <BarChart rows={years.map((row) => ({ label: String(row.year), value: row.papers }))} label={t("gapPublications")} valueLabel={t("libStatPapers")} language={language} />}
        </section>
      )}
      {(["method", "dataset", "task"] as const).map((kind) => series[kind]?.length ? (
        <section key={kind} className="gw-panel">
          <h3>{t(kind === "method" ? "gapTopMethods" : kind === "dataset" ? "gapTopDatasets" : "gapTopTasks")}</h3>
          <div className="gw-table-wrap">
            <table className="gw-table">
              <thead><tr><th>{t("gapName")}</th>{asTable ? yearKeys.map((year) => <th key={year}>{year}</th>) : <th>{t("gapOverTime")}</th>}<th>{t("gapTotal")}</th></tr></thead>
              <tbody>
                {series[kind].map((row) => {
                  const peak = Math.max(1, ...yearKeys.map((year) => row.by_year[year] || 0));
                  return (
                    <tr key={row.label}>
                      <th scope="row"><bdi>{row.label}</bdi></th>
                      {asTable ? yearKeys.map((year) => <td key={year}>{row.by_year[year] || 0}</td>) : (
                        <td><span className="gw-spark" aria-hidden="true">{yearKeys.map((year) => <i key={year} style={{ blockSize: `${Math.max(6, ((row.by_year[year] || 0) / peak) * 100)}%`, opacity: row.by_year[year] ? 1 : 0.25 }} />)}</span></td>
                      )}
                      <td>{formatNumber(row.total, language)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null)}
      {keywords.length ? (
        <section className="gw-panel">
          <h3>{t("gapKeywords")}</h3>
          <div className="lb-suggestions">{keywords.map((keyword) => <Link key={keyword.label} className="lb-tag" to={`/search?q=${encodeURIComponent(keyword.label)}`}><bdi>{keyword.label}</bdi> · {keyword.count}</Link>)}</div>
        </section>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- people

function PeopleView({ t, language, analysis }: Shared) {
  if (!analysis) return null;
  const { researchers, institutions } = analysis.people;
  if (!researchers.length) return <EmptyState title={t("gapNoPeople")} />;
  return (
    <div className="lb-section">
      <p className="lb-section-note">{t("gapPeopleNote")}</p>
      <section className="gw-panel">
        <h3>{t("gapResearchers")}</h3>
        <div className="gw-table-wrap">
          <table className="gw-table">
            <thead><tr><th>{t("gapName")}</th><th>{t("libStatPapers")}</th><th>{t("gapCitations")}</th><th>{t("gapActive")}</th><th>{t("gapWorksWith")}</th></tr></thead>
            <tbody>
              {researchers.map((person) => (
                <tr key={person.name}>
                  <th scope="row"><Link to={`/search?q=${encodeURIComponent(person.name)}`} className="lb-link"><bdi>{person.name}</bdi></Link></th>
                  <td>{formatNumber(person.papers, language)}</td>
                  <td>{formatNumber(person.citations, language)}</td>
                  <td>{person.first_year ? (person.first_year === person.last_year ? person.first_year : <bdi dir="ltr">{`${person.first_year}–${person.last_year}`}</bdi>) : "—"}</td>
                  <td><bdi>{person.collaborators.join(", ") || "—"}</bdi></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {researchers.some((person) => person.suggested?.length) ? (
        <section className="gw-panel">
          <h3>{t("gapSuggestedCollaborators")}</h3>
          <p className="lb-section-note">{t("gapSuggestedNote")}</p>
          <ul className="gw-plain-list">
            {researchers.filter((person) => person.suggested?.length).slice(0, 8).map((person) => (
              <li key={person.name} className="gw-suggest">
                <bdi className="gw-suggest-name">{person.name}</bdi>
                <span className="gw-small">{person.suggested!.map((option) => t("gapSuggestedPair", { name: option.name, shared: option.shared.join(", ") })).join(" · ")}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {institutions.length ? (
        <section className="gw-panel">
          <h3>{t("gapInstitutions")}</h3>
          <ul className="gw-plain-list">{institutions.map((institution) => <li key={institution.name}><bdi>{institution.name}</bdi><span>{formatNumber(institution.papers, language)}</span></li>)}</ul>
        </section>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- datasets

function DatasetsView({ t, language, analysis, byId }: Shared) {
  const navigate = useNavigate();
  const [open, setOpen] = useState<string | null>(null);
  if (!analysis) return null;
  if (!analysis.datasets.length) return <EmptyState title={t("gapNoDatasets")} body={t("gapNoDatasetsBody")} />;
  return (
    <div className="lb-section">
      <p className="lb-section-note">{t("gapDatasetsNote")}</p>
      <div className="gw-table-wrap">
        <table className="gw-table">
          <thead><tr><th>{t("cmpColDataset")}</th><th>{t("libStatPapers")}</th><th>{t("gapTasks")}</th><th>{t("gapMethods")}</th><th>{t("gapMetrics")}</th><th>{t("gapYears")}</th><th>{t("gapAccess")}</th></tr></thead>
          <tbody>
            {analysis.datasets.map((row) => (
              <Fragment key={row.name}>
                <tr>
                  <th scope="row"><button type="button" className="lb-text-button" aria-expanded={open === row.name} onClick={() => setOpen(open === row.name ? null : row.name)}><bdi>{row.name}</bdi></button></th>
                  <td>{formatNumber(row.papers, language)}</td>
                  <td><bdi>{row.tasks.join(", ") || "—"}</bdi></td>
                  <td><bdi>{row.methods.join(", ") || "—"}</bdi></td>
                  <td><bdi>{row.metrics.join(", ") || "—"}</bdi></td>
                  <td>{row.first_year ? (row.first_year === row.last_year ? row.first_year : <bdi dir="ltr">{`${row.first_year}–${row.last_year}`}</bdi>) : "—"}</td>
                  <td>{t("gapAccessNotStated")}</td>
                </tr>
                {open === row.name ? (
                  <tr className="gw-detail-row">
                    <td colSpan={7}>
                      {row.quote ? <blockquote className="gw-quote" dir="auto">“{row.quote}”</blockquote> : null}
                      <ul className="gw-plain-list">{row.paper_ids.map((id) => { const paper = byId.get(id); return paper ? <li key={id}><button type="button" className="gw-paper-link" onClick={() => openInReader(navigate, paper)}><bdi>{paper.title}</bdi></button><span>{paper.year || ""}</span></li> : null; })}</ul>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- ideas

function IdeasView({ t, language }: Shared) {
  const [ideas, setIdeas] = useState<LibraryNote[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    libraryApi.notes({ kind: "idea" }).then(setIdeas).catch((caught) => setError(errorTextFor(t, caught)));
  }, [t]);
  if (error) return <ErrorLine message={error} t={t} />;
  if (!ideas) return <SkeletonRows rows={3} />;
  if (!ideas.length) return <EmptyState icon={<BulbGlyph />} title={t("libNoIdeas")} body={t("gapIdeasEmpty")} />;
  return (
    <div className="lb-section">
      <div className="lb-section-head">
        <p className="lb-section-note">{t("gapIdeasNote")}</p>
        <Link to="/library/ideas" className="lb-button lb-button-quiet">{t("gapOpenIdeas")}</Link>
      </div>
      <ul className="lb-notes">
        {ideas.map((idea) => (
          <li key={idea.id} className="lb-note">
            <h3 dir="auto">{idea.title || idea.body.slice(0, 80)}</h3>
            {idea.title && idea.body ? <p className="lb-note-body" dir="auto">{idea.body}</p> : null}
            <div className="lb-note-foot"><span className={`lb-badge`}>{t(idea.status === "exploring" ? "libIdeaExploring" : idea.status === "parked" ? "libIdeaParked" : idea.status === "done" ? "libIdeaDone" : "libIdeaNew")}</span><span className="lb-note-date">{formatDay(idea.updated_at, language)}</span></div>
          </li>
        ))}
      </ul>
    </div>
  );
}
