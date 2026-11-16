/** Research Insights: the deduplicated catalog built by the Big Data pipeline (collectors → Data Lake → Spark ETL →
 *  analytics → search index). Coverage and deduplication, trends, hot and emerging topics, citation patterns,
 *  gap candidates with evidence, hybrid semantic + keyword search, and pipeline runs. */
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import type { SearchCopyKey, SearchT } from "./search/copy";
import { EmptyState, ErrorLine, SearchGlyph, SkeletonRows, SparkGlyph, formatNumber } from "./library/ui";
import { openInReader } from "./gaps/shared";
import { catalogApi, type CatalogAnalytics, type CatalogOverview, type CatalogPaper, type CatalogRun } from "./platform/platformApi";
import { PageShell, Stat, errorText, formatDateTime, usePlatform } from "./platform/shared";

const SOURCE_NAMES: Record<string, string> = { openalex: "OpenAlex", arxiv: "arXiv", crossref: "Crossref", semantic_scholar: "Semantic Scholar" };
const LEVEL_KEYS: Record<string, SearchCopyKey> = { strong: "gapLevelStrong", moderate: "gapLevelModerate", limited: "gapLevelLimited" };
const RUN_KEYS: Record<CatalogRun["status"], SearchCopyKey> = { running: "insRunRunning", succeeded: "insRunSucceeded", failed: "insRunFailed" };

function Bars({ rows, label, language }: { rows: Array<{ label: string; value: number }>; label: string; language: string }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="gw-chart" role="img" aria-label={label}>
      {rows.map((row) => (
        <div key={row.label} className="gw-bar" title={`${row.label}: ${row.value}`}>
          <span className="gw-bar-fill" style={{ blockSize: `${Math.max(2, (row.value / max) * 100)}%` }} />
          <span className="gw-bar-value">{formatNumber(row.value, language)}</span>
          <span className="gw-bar-label">{row.label}</span>
        </div>
      ))}
    </div>
  );
}

function HBars({ rows, language }: { rows: Array<{ label: string; value: number; note?: string }>; language: string }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <ul className="pf-hbars">
      {rows.map((row) => (
        <li key={row.label}>
          <span className="pf-hbar-label"><bdi>{row.label}</bdi></span>
          <span className="pf-hbar-track"><span style={{ inlineSize: `${Math.max(2, (row.value / max) * 100)}%` }} /></span>
          <span className="pf-hbar-value">{formatNumber(row.value, language)}{row.note ? <span className="gw-small"> {row.note}</span> : null}</span>
        </li>
      ))}
    </ul>
  );
}

export function InsightsPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const [overview, setOverview] = useState<CatalogOverview | null>(null);
  const [analytics, setAnalytics] = useState<CatalogAnalytics | null>(null);
  const [runs, setRuns] = useState<CatalogRun[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [next, data, history] = await Promise.all([catalogApi.overview(), catalogApi.analytics(), catalogApi.runs()]);
      setOverview(next);
      setAnalytics(data);
      setRuns(history.runs);
      setError("");
    } catch (caught) {
      setError(errorText(t, caught));
    }
  }, [t]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!overview?.running.length) return undefined;
    const timer = window.setInterval(() => void load(), 4000);  // poll while a pipeline run is in progress
    return () => window.clearInterval(timer);
  }, [overview?.running.length, load]);

  const language = interfaceLanguage;
  return (
    <PageShell language={language} title={t("insTitle")} subtitle={t("insSubtitle")} toastText={toastText}>
      {error ? <ErrorLine message={error} onRetry={() => void load()} t={t} /> : !overview || !analytics ? <SkeletonRows rows={6} /> : (
        <>
          <section className="pf-stats pf-stats-wide" aria-label={t("insCoverage")}>
            <Stat label={t("insUniquePapers")} value={formatNumber(overview.papers, language)} note={overview.index ? t("insIndexed", { count: formatNumber(overview.index.papers, language) }) : t("insNotIndexed")} />
            <Stat label={t("insRawRecords")} value={overview.raw_records != null ? formatNumber(overview.raw_records, language) : "—"} />
            <Stat label={t("insDuplicatesMerged")} value={overview.duplicates_merged != null ? formatNumber(overview.duplicates_merged, language) : "—"} note={overview.duplicate_rate != null ? t("insDuplicateRate", { rate: Math.round(overview.duplicate_rate * 100) }) : undefined} />
            <Stat label={t("insSources")} value={formatNumber(Object.keys(overview.papers_per_source).length, language)} note={overview.last_run ? t("insLastRun", { time: formatDateTime(overview.last_run.finished_at || overview.last_run.started_at, language) }) : t("insNoRuns")} />
          </section>

          <CatalogSearch t={t} language={language} disabled={!overview.index} />

          {!overview.papers ? <EmptyState icon={<SparkGlyph />} title={t("insEmpty")} body={t("insEmptyBody")} /> : (
            <div className="pf-grid-2">
              <section className="gw-panel" aria-labelledby="ins-coverage">
                <h2 id="ins-coverage">{t("insCoverage")}</h2>
                <p className="lb-section-note">{t("insCoverageNote")}</p>
                <HBars language={language} rows={Object.entries(overview.papers_per_source).sort((a, b) => b[1] - a[1]).map(([source, value]) => ({ label: SOURCE_NAMES[source] || source, value, note: overview.unique_to_source[source] ? t("insOnlyHere", { count: formatNumber(overview.unique_to_source[source], language) }) : undefined }))} />
                <p className="gw-small">{Object.entries(overview.papers_by_source_count).map(([count, value]) => t("insFoundIn", { sources: count, count: formatNumber(value, language) })).join(" · ")}</p>
              </section>

              <section className="gw-panel" aria-labelledby="ins-trends">
                <h2 id="ins-trends">{t("insTrends")}</h2>
                {analytics.publication_trends?.length ? <Bars label={t("insTrends")} language={language} rows={analytics.publication_trends.map((row) => ({ label: String(row.year), value: row.papers }))} /> : <p className="gw-small">{t("gapNoYears")}</p>}
              </section>

              <section className="gw-panel" aria-labelledby="ins-hot">
                <h2 id="ins-hot">{t("insHotTopics")}</h2>
                <p className="lb-section-note">{t("insHotNote")}</p>
                {!analytics.hot_topics?.length ? <p className="gw-small">{t("insNoHot")}</p> : (
                  <ul className="pf-hot">
                    {analytics.hot_topics.map((row) => (
                      <li key={row.topic}>
                        <span className={`pf-hot-badge is-${row.status}`}>{t(row.status === "emerging" ? "insEmerging" : "insGrowing")}</span>
                        <bdi className="pf-hot-topic">{row.topic}</bdi>
                        <span className="gw-small">{t("insGrowth", { recent: row.recent, prior: row.prior, from: `${row.recent_years[0]}–${row.recent_years[1]}`, to: `${row.prior_years[0]}–${row.prior_years[1]}`, growth: row.growth })}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="gw-panel" aria-labelledby="ins-topics">
                <h2 id="ins-topics">{t("insTopTopics")}</h2>
                <HBars language={language} rows={(analytics.topic_trends || []).slice(0, 10).map((row) => ({ label: row.topic, value: row.total }))} />
              </section>

              <section className="gw-panel" aria-labelledby="ins-citations">
                <h2 id="ins-citations">{t("insCitations")}</h2>
                {analytics.citation_patterns ? (
                  <>
                    <p className="lb-section-note">{t("insCitationNote", { uncited: Math.round((analytics.citation_patterns.uncited_share || 0) * 100), top: Math.round((analytics.citation_patterns.top_decile_share || 0) * 100) })}</p>
                    <ol className="gw-plain-list pf-cited">
                      {(analytics.citation_patterns.most_cited || []).slice(0, 6).map((paper) => <li key={paper.paper_id}><bdi>{paper.title}</bdi> <span className="gw-small">{paper.year} · {t("insCitedTimes", { count: formatNumber(paper.citation_count, language) })}</span></li>)}
                    </ol>
                  </>
                ) : null}
              </section>

              <section className="gw-panel" aria-labelledby="ins-gaps">
                <h2 id="ins-gaps">{t("insGapCandidates")}</h2>
                <p className="gw-disclaimer" role="note">{t("insGapNote")}</p>
                {!analytics.gap_candidates?.length ? <p className="gw-small">{t("insNoGaps")}</p> : (
                  <ul className="gw-plain-list">
                    {analytics.gap_candidates.slice(0, 8).map((gap) => (
                      <li key={gap.topics.join("|")} className="pf-gap">
                        <span className={`gw-level gw-level-${gap.level}`}>{t(LEVEL_KEYS[gap.level])}</span>
                        <b><bdi>{gap.topics[0]}</bdi> × <bdi>{gap.topics[1]}</bdi></b>
                        <span className="gw-small">{t("insGapCounts", { a: gap.papers_a, b: gap.papers_b, together: gap.together, expected: gap.expected })}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {analytics.collaboration?.top_authors?.length ? (
                <section className="gw-panel" aria-labelledby="ins-people">
                  <h2 id="ins-people">{t("insPeople")}</h2>
                  <HBars language={language} rows={analytics.collaboration.top_authors.slice(0, 8).map((row) => ({ label: row.name, value: row.papers }))} />
                  <p className="gw-small">{t("insTeamSize", { size: analytics.collaboration.median_team_size })}</p>
                </section>
              ) : null}
            </div>
          )}

          <RunsPanel t={t} language={language} runs={runs} running={overview.running} onStarted={() => { toast(t("insRunStarted")); void load(); }} onError={(caught) => toast(errorText(t, caught))} />
        </>
      )}
    </PageShell>
  );
}

function CatalogSearch({ t, language, disabled }: { t: SearchT; language: string; disabled: boolean }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CatalogPaper[] | null>(null);
  const [openAccess, setOpenAccess] = useState(false);
  const [busy, setBusy] = useState(false);

  async function search(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setBusy(true);
    try {
      setResults((await catalogApi.search(query.trim(), { openAccess })).results);
    } catch {
      setResults([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="gw-panel" aria-labelledby="ins-search">
      <h2 id="ins-search">{t("insSearchTitle")}</h2>
      <p className="lb-section-note">{t("insSearchNote")}</p>
      <form className="gw-scope-topic" onSubmit={search} role="search">
        <label className="rs-visually-hidden" htmlFor="ins-query">{t("insSearchTitle")}</label>
        <input id="ins-query" value={query} dir="auto" disabled={disabled} placeholder={t(disabled ? "insNotIndexed" : "insSearchPlaceholder")} onChange={(event) => setQuery(event.target.value)} />
        <button type="button" className={`lb-pill${openAccess ? " is-active" : ""}`} aria-pressed={openAccess} onClick={() => setOpenAccess((value) => !value)}>{t("insOpenAccess")}</button>
        <button type="submit" className="lb-button lb-button-primary" disabled={disabled || busy || query.trim().length < 2}><SearchGlyph />{t("insSearch")}</button>
      </form>
      {results ? (!results.length ? <p className="gw-small">{t("insNoResults")}</p> : (
        <ul className="lb-rows">
          {results.map((paper) => (
            <li key={paper.paper_id} className="lb-row pf-row">
              <div className="lb-row-main">
                <button type="button" className="lb-row-title" onClick={() => openInReader(navigate, { id: paper.paper_id, title: paper.title, abstract: paper.abstract, year: paper.year, authors: paper.authors.map((author) => author.name), doi: paper.doi, url: paper.oa_url, pdf_url: paper.pdf_url })}><bdi>{paper.title}</bdi></button>
                <span className="lb-row-meta"><bdi>{[paper.authors.slice(0, 3).map((author) => author.name).join(", "), paper.venue, paper.year].filter(Boolean).join(" · ")}</bdi></span>
                <span className="pf-match">
                  {paper.match?.matched.map((side) => <span key={side} className={`pf-match-badge is-${side}`}>{t(side === "keyword" ? "insMatchKeyword" : "insMatchSemantic")}</span>)}
                  <span className="gw-small">{t("insSourcesList", { list: paper.sources.map((source) => SOURCE_NAMES[source] || source).join(", ") })}{paper.duplicate_count ? ` · ${t("insMerged", { count: paper.duplicate_count + 1 })}` : ""}</span>
                </span>
              </div>
              <span className="gw-small">{t("insCitedTimes", { count: formatNumber(paper.citation_count, language) })}</span>
            </li>
          ))}
        </ul>
      )) : null}
    </section>
  );
}

function RunsPanel({ t, language, runs, running, onStarted, onError }: { t: SearchT; language: string; runs: CatalogRun[]; running: string[]; onStarted: () => void; onError: (caught: unknown) => void }) {
  const [queries, setQueries] = useState("");
  const [sources, setSources] = useState<string[]>(["openalex", "arxiv", "crossref", "semantic_scholar"]);
  const [max, setMax] = useState(200);
  const [busy, setBusy] = useState(false);

  async function start(event: FormEvent) {
    event.preventDefault();
    const list = queries.split(/\n|;/).map((value) => value.trim()).filter(Boolean).slice(0, 10);
    if (!list.length || !sources.length) return;
    setBusy(true);
    try {
      await catalogApi.startRun(list, sources, max, "local");
      onStarted();
    } catch (caught) {
      onError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="gw-panel" aria-labelledby="ins-runs">
      <h2 id="ins-runs">{t("insRunsTitle")}</h2>
      <p className="lb-section-note">{t("insRunsNote")}</p>
      <form className="gw-create" onSubmit={start}>
        <label className="lb-field"><span>{t("insQueries")}</span><textarea value={queries} rows={2} dir="auto" placeholder={t("insQueriesPlaceholder")} onChange={(event) => setQueries(event.target.value)} /></label>
        <fieldset className="pf-sources">
          <legend>{t("insSources")}</legend>
          {Object.entries(SOURCE_NAMES).map(([id, name]) => (
            <label key={id} className="lb-pick pf-source-pick">
              <input type="checkbox" checked={sources.includes(id)} onChange={() => setSources((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])} />
              <span>{name}</span>
            </label>
          ))}
        </fieldset>
        <label className="lb-field pf-narrow"><span>{t("insMaxRecords")}</span><input type="number" min={10} max={5000} value={max} onChange={(event) => setMax(Math.max(10, Math.min(5000, Number(event.target.value) || 200)))} /></label>
        <div><button type="submit" className="lb-button lb-button-primary" disabled={busy || running.length > 0 || !queries.trim() || !sources.length}>{running.length ? t("insRunRunning") : t("insStartRun")}</button></div>
      </form>
      {runs.length ? (
        <div className="gw-table-wrap"><table className="gw-table">
          <thead><tr><th>{t("insRunStartedAt")}</th><th>{t("insRunStatus")}</th><th>{t("insQueries")}</th><th className="num">{t("insRawRecords")}</th><th className="num">{t("insUniquePapers")}</th><th className="num">{t("insDuplicatesMerged")}</th></tr></thead>
          <tbody>{runs.map((run) => (
            <tr key={run.run_id}>
              <th scope="row">{formatDateTime(run.started_at, language)}</th>
              <td><span className={`pf-run-status is-${run.status}`}>{t(RUN_KEYS[run.status])}</span></td>
              <td><bdi>{(run.params.queries || []).join("; ") || "—"}</bdi></td>
              <td className="num">{run.stats.etl?.raw_records != null ? formatNumber(run.stats.etl.raw_records, language) : "—"}</td>
              <td className="num">{run.stats.etl?.unique_papers != null ? formatNumber(run.stats.etl.unique_papers, language) : "—"}</td>
              <td className="num">{run.stats.etl?.duplicates_merged != null ? formatNumber(run.stats.etl.duplicates_merged, language) : "—"}</td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : null}
    </section>
  );
}
