/**
 * Admin console (/admin): Overview (business metrics), Users (plan, usage, grant credits, suspend), AI providers
 * (health, quotas, routing, voices), Feature flags (rollout %), Jobs (pipeline runs, dead letters with retry),
 * Messages (contact form), Status (incidents for the public status page) and the Audit log.
 * The server enforces the admin role on every call; this page only shows what the server returns.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";
import { comparisonHeaders } from "./compare/compareApi";
import { LibraryError, libraryApiBase } from "./library/libraryApi";
import { formatNumber } from "./library/ui";
import { money, type Currency } from "./platform/platformApi";
import { errorText, formatDateTime, Meter, PageShell, Stat, usePlatform } from "./platform/shared";
import type { SearchCopyKey, SearchT } from "./search/copy";

async function call<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${libraryApiBase}/admin${path}`, { method, headers: { ...comparisonHeaders(), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new LibraryError("network");
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
    throw new LibraryError(detail?.detail?.code || "unavailable", response.status);
  }
  return (await response.json()) as T;
}

type Overview = {
  mrr: Record<string, number>; revenue_30d: Record<string, number>; subscriptions: Record<string, number>; plans: Record<string, number>; paying: number; trialing: number;
  churn_risk: number; churn_risk_rate: number; signups_30d: number; activation_rate: number; active_users_7d: number; active_users_30d: number;
  credits_by_action_30d: Record<string, number>; credits_by_day: Array<{ day: string; credits: number }>; credit_packs_sold: number;
  traffic: { pageviews: number; visitors: number; by_day: Array<{ day: string; views: number; visitors: number }>; top_paths: Array<{ path: string; views: number }>; top_referrers: Array<{ referrer: string; views: number }>; devices: Record<string, number> };
  referrals: { redemptions: number; codes: number }; waitlist: Record<string, number>; open_messages: number;
};
type UserRow = { user_id: string; display_name: string; plan: string; subscription_status: string | null; seats: number; credits_30d: number; topup_balance: number; teams: number; suspended: boolean; first_seen: string | null; last_seen: string | null };
type UserDetail = { user_id: string; plan: string; seats: number; usage: { windows: Array<{ scope: "session" | "week" | "month"; used: number; limit: number; remaining: number; percent: number; resets_at: string }>; topup_balance: number }; history: Array<{ day: string; action: string; credits: number }>; invoices: Array<{ id: string; number: string; description: string; amount: number; currency: Currency; status: string; created_at: string }>; credit_grants: Array<{ id: string; credits_total: number; credits_used: number; session_id: string | null; created_at: string }>; teams: Array<{ id: string; name: string; role: string }>; suspended: boolean; suspension_reason?: string | null; audit: AuditEntry[] };
type Flag = { key: string; description: string; enabled: boolean; rollout: number; allow_users: string[]; updated_by: string | null; updated_at: string };
type AuditEntry = { id: string; actor_id: string; action: string; target: string | null; detail: Record<string, unknown>; created_at: string };
type DeadLetter = { id: string; kind: string; source: string; error: string; attempts: number; status: string; created_at: string; updated_at: string };
type Run = { run_id: string; engine: string; status: string; started_at: string; finished_at?: string | null; params?: { queries?: string[] }; error?: string | null };
type ProviderHealth = { configured: boolean; healthy: boolean; cooldown_seconds: number; daily_quota: { limit: number | null; used: number; remaining: number | null }; last_probe: { reason?: string; checked_at?: string } };
type Providers = { ai: Record<string, ProviderHealth>; routes: Record<string, string[]>; tts: { engines: Record<string, { configured: boolean; healthy: boolean; failures: number }>; metrics: Record<string, number> }; voices: Array<{ language: string; voices: number }> };
type Message = { id: string; name: string; email: string; topic: string; message: string; language: string; status: string; created_at: string };
type Incident = { id: string; title: string; component: string; severity: string; status: string; message: string; created_at: string; updated_at: string; resolved_at: string | null };

const adminApi = {
  me: () => call<{ user_id: string }>("/me"),
  overview: () => call<Overview>("/overview"),
  users: (q: string) => call<{ total: number; users: UserRow[] }>(`/users?q=${encodeURIComponent(q)}`),
  user: (id: string) => call<UserDetail>(`/users/${encodeURIComponent(id)}`),
  grant: (id: string, credits: number, reason: string) => call<{ balance: number }>(`/users/${encodeURIComponent(id)}/credits`, { credits, reason }),
  suspend: (id: string, suspended: boolean, reason?: string) => call(`/users/${encodeURIComponent(id)}/suspension`, { suspended, reason }),
  providers: () => call<Providers>("/providers"),
  probe: (name: string) => call<{ healthy: boolean | null; reason: string }>(`/providers/${encodeURIComponent(name)}/probe`, {}),
  flags: () => call<{ flags: Flag[] }>("/flags"),
  setFlag: (key: string, body: { enabled: boolean; rollout: number; description?: string }) => call<Flag>(`/flags/${encodeURIComponent(key)}`, body, "PUT"),
  jobs: () => call<{ pipeline_runs: Run[]; dead_letters: DeadLetter[] }>("/jobs"),
  retry: (id: string) => call<{ status: string }>(`/jobs/dead-letters/${encodeURIComponent(id)}/retry`, {}),
  discard: (id: string) => call<void>(`/jobs/dead-letters/${encodeURIComponent(id)}/discard`, {}),
  audit: () => call<{ entries: AuditEntry[] }>("/audit"),
  messages: () => call<{ messages: Message[] }>("/messages"),
  messageStatus: (id: string, status: "open" | "closed") => call(`/messages/${encodeURIComponent(id)}/status`, { status }),
  incidents: () => call<{ incidents: Incident[] }>("/incidents"),
  saveIncident: (body: Omit<Incident, "id" | "created_at" | "updated_at" | "resolved_at">, id?: string) => (id ? call<Incident>(`/incidents/${encodeURIComponent(id)}`, body, "PUT") : call<Incident>("/incidents", body)),
};

const TABS: Array<[string, SearchCopyKey]> = [["", "admTabOverview"], ["users", "admTabUsers"], ["providers", "admTabProviders"], ["flags", "admTabFlags"], ["jobs", "admTabJobs"], ["messages", "admTabMessages"], ["status", "admTabStatus"], ["audit", "admTabAudit"]];
const COMPONENTS = ["search", "reader", "listen", "billing", "ai", "catalog", "website"] as const;
const SEVERITIES = ["minor", "major", "critical", "maintenance"] as const;
const STATES = ["investigating", "identified", "monitoring", "resolved"] as const;

function useLoad<T>(load: () => Promise<T>, key = "") {
  const [state, setState] = useState<{ key: string; data: T | null; error: unknown }>({ key, data: null, error: null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    load().then((data) => { if (!cancelled) setState({ key, data, error: null }); }).catch((error: unknown) => { if (!cancelled) setState({ key, data: null, error }); });
    return () => { cancelled = true; };
  }, [key, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  const current = state.key === key ? state : { key, data: null, error: null };
  return { data: current.data, error: current.error, reload: () => setTick((value) => value + 1) };
}

function Bars({ rows, label }: { rows: Array<{ label: string; value: number }>; label: string }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="pf-bars" role="img" aria-label={label}>
      {rows.map((row) => (
        <div key={row.label} className="pf-bar-row">
          <span className="pf-bar-label"><bdi>{row.label}</bdi></span>
          <span className="pf-bar-track"><span style={{ inlineSize: `${(row.value / max) * 100}%` }} /></span>
          <span className="pf-bar-value">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

function moneyMap(values: Record<string, number>, language: string, t: SearchT) {
  const entries = Object.entries(values).filter(([, amount]) => amount);
  return entries.length ? entries.map(([currency, amount]) => money(amount, currency as Currency, language)).join(" · ") : t("admNone");
}

function OverviewTab({ t, language }: { t: SearchT; language: string }) {
  const { data, error } = useLoad(adminApi.overview);
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" role="status" aria-label={t("admLoading")} />;
  const percent = (value: number) => `${formatNumber(Math.round(value * 1000) / 10, language)}%`;
  return (
    <>
      <section className="pf-stats pf-stats-wide" aria-label={t("admBusiness")}>
        <Stat label={t("admMrr")} value={moneyMap(data.mrr, language, t)} note={t("admPaying", { count: formatNumber(data.paying, language) })} />
        <Stat label={t("admRevenue30")} value={moneyMap(data.revenue_30d, language, t)} />
        <Stat label={t("admTrialing")} value={formatNumber(data.trialing, language)} />
        <Stat label={t("admChurnRisk")} value={formatNumber(data.churn_risk, language)} note={percent(data.churn_risk_rate)} />
        <Stat label={t("admSignups30")} value={formatNumber(data.signups_30d, language)} note={t("admActivation", { rate: percent(data.activation_rate) })} />
        <Stat label={t("admActive7")} value={formatNumber(data.active_users_7d, language)} note={t("admActive30", { count: formatNumber(data.active_users_30d, language) })} />
        <Stat label={t("admPacksSold")} value={formatNumber(data.credit_packs_sold, language)} />
        <Stat label={t("admOpenMessages")} value={formatNumber(data.open_messages, language)} />
      </section>
      <div className="pf-grid-2">
        <section className="gw-panel" aria-labelledby="adm-credits">
          <h2 id="adm-credits">{t("admCreditsByAction")}</h2>
          {Object.keys(data.credits_by_action_30d).length ? <Bars label={t("admCreditsByAction")} rows={Object.entries(data.credits_by_action_30d).map(([label, value]) => ({ label, value }))} /> : <p className="gw-small">{t("admNone")}</p>}
        </section>
        <section className="gw-panel" aria-labelledby="adm-plans">
          <h2 id="adm-plans">{t("admPlans")}</h2>
          {Object.keys(data.plans).length ? <Bars label={t("admPlans")} rows={Object.entries(data.plans).map(([label, value]) => ({ label, value }))} /> : <p className="gw-small">{t("admNone")}</p>}
        </section>
        <section className="gw-panel" aria-labelledby="adm-traffic">
          <h2 id="adm-traffic">{t("admTraffic")}</h2>
          <p className="gw-small">{t("admTrafficNote", { views: formatNumber(data.traffic.pageviews, language), visitors: formatNumber(data.traffic.visitors, language) })}</p>
          {data.traffic.top_paths.length ? <Bars label={t("admTopPages")} rows={data.traffic.top_paths.map((row) => ({ label: row.path, value: row.views }))} /> : null}
        </section>
        <section className="gw-panel" aria-labelledby="adm-growth">
          <h2 id="adm-growth">{t("admGrowth")}</h2>
          <ul className="gw-plain-list">
            <li>{t("admReferrals", { count: formatNumber(data.referrals.redemptions, language) })}</li>
            <li>{t("admNewsletter", { confirmed: formatNumber(data.waitlist.confirmed || 0, language), pending: formatNumber(data.waitlist.pending || 0, language) })}</li>
          </ul>
          {data.traffic.top_referrers.length ? <Bars label={t("admReferrers")} rows={data.traffic.top_referrers.map((row) => ({ label: row.referrer, value: row.views }))} /> : null}
        </section>
      </div>
    </>
  );
}

function UsersTab({ t, language }: { t: SearchT; language: string }) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, error } = useLoad(() => adminApi.users(submitted), submitted);
  return (
    <section className="gw-panel" aria-labelledby="adm-users">
      <h2 id="adm-users">{t("admTabUsers")}</h2>
      <form className="pf-inline-form" role="search" onSubmit={(event) => { event.preventDefault(); setSubmitted(query.trim()); }}>
        <label className="rs-visually-hidden" htmlFor="adm-user-q">{t("admSearchUsers")}</label>
        <input id="adm-user-q" className="lb-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("admSearchUsers")} />
        <button type="submit" className="lb-button">{t("admSearch")}</button>
      </form>
      {error ? <p className="pf-empty" role="alert">{errorText(t, error)}</p> : !data ? <div className="pf-skel" /> : !data.users.length ? <p className="pf-empty">{t("admNoUsers")}</p> : (
        <div className="gw-table-wrap">
          <table className="gw-table">
            <thead><tr><th>{t("admUser")}</th><th>{t("admPlan")}</th><th>{t("admCredits30")}</th><th>{t("admPackBalance")}</th><th>{t("admLastSeen")}</th><th>{t("admState")}</th></tr></thead>
            <tbody>
              {data.users.map((row) => (
                <tr key={row.user_id}>
                  <td><Link to={`/admin/users/${encodeURIComponent(row.user_id)}`}><bdi>{row.display_name || row.user_id}</bdi></Link>{row.display_name ? <span className="gw-small"> <bdi>{row.user_id}</bdi></span> : null}</td>
                  <td>{row.plan}{row.subscription_status ? <span className="gw-small"> · {row.subscription_status}</span> : null}</td>
                  <td>{formatNumber(row.credits_30d, language)}</td>
                  <td>{formatNumber(row.topup_balance, language)}</td>
                  <td>{row.last_seen ? formatDateTime(row.last_seen, language) : "—"}</td>
                  <td>{row.suspended ? <span className="lb-badge is-warn">{t("admSuspended")}</span> : <span className="lb-badge">{t("admActive")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="gw-small">{t("admUsersTotal", { count: formatNumber(data.total, language) })}</p>
        </div>
      )}
    </section>
  );
}

function UserView({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { userId = "" } = useParams();
  const { data, error, reload } = useLoad(() => adminApi.user(userId), userId);
  const [credits, setCredits] = useState("50");
  const [reason, setReason] = useState("");
  const [suspendReason, setSuspendReason] = useState("");
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" />;
  async function grant() {
    try {
      await adminApi.grant(userId, Number(credits), reason);
      setReason("");
      toast(t("admGranted"));
      reload();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }
  async function suspend(next: boolean) {
    try {
      await adminApi.suspend(userId, next, suspendReason || undefined);
      toast(next ? t("admSuspendedToast") : t("admRestoredToast"));
      reload();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }
  return (
    <>
      <p><Link to="/admin/users" className="lb-link">{t("admBackToUsers")}</Link></p>
      <section className="gw-panel" aria-labelledby="adm-user-title">
        <h2 id="adm-user-title"><bdi>{data.user_id}</bdi> · {data.plan}{data.suspended ? <span className="lb-badge is-warn"> {t("admSuspended")}</span> : null}</h2>
        <div className="pf-meters">{data.usage.windows.map((window) => <Meter key={window.scope} t={t} language={language} window={window} />)}</div>
        <p className="gw-small">{t("admPackBalanceIs", { count: formatNumber(data.usage.topup_balance, language) })}{data.teams.length ? ` · ${t("admTeamsList", { list: data.teams.map((team) => `${team.name} (${team.role})`).join(", ") })}` : ""}</p>
      </section>
      <div className="pf-grid-2">
        <section className="gw-panel" aria-labelledby="adm-grant">
          <h2 id="adm-grant">{t("admGrantCredits")}</h2>
          <form className="pf-form" onSubmit={(event) => { event.preventDefault(); void grant(); }}>
            <label className="lb-field"><span>{t("admCreditsAmount")}</span><input type="number" min={1} max={100000} value={credits} onChange={(event) => setCredits(event.target.value)} required /></label>
            <label className="lb-field"><span>{t("admReason")}</span><input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} required placeholder={t("admReasonPlaceholder")} /></label>
            <button type="submit" className="lb-button lb-button-primary">{t("admGrant")}</button>
          </form>
        </section>
        <section className="gw-panel" aria-labelledby="adm-suspend">
          <h2 id="adm-suspend">{t("admAccess")}</h2>
          <p className="gw-small">{data.suspended ? t("admSuspendedBecause", { reason: data.suspension_reason || "—" }) : t("admSuspendNote")}</p>
          {data.suspended ? (
            <button type="button" className="lb-button" onClick={() => void suspend(false)}>{t("admRestore")}</button>
          ) : (
            <form className="pf-form" onSubmit={(event) => { event.preventDefault(); void suspend(true); }}>
              <label className="lb-field"><span>{t("admReason")}</span><input value={suspendReason} onChange={(event) => setSuspendReason(event.target.value)} /></label>
              <button type="submit" className="lb-button pf-danger">{t("admSuspend")}</button>
            </form>
          )}
        </section>
      </div>
      <section className="gw-panel" aria-labelledby="adm-history">
        <h2 id="adm-history">{t("admRecentUsage")}</h2>
        {data.history.length ? <Bars label={t("admRecentUsage")} rows={Object.entries(data.history.reduce<Record<string, number>>((sum, row) => ({ ...sum, [row.action]: (sum[row.action] || 0) + row.credits }), {})).map(([label, value]) => ({ label, value }))} /> : <p className="gw-small">{t("admNone")}</p>}
        <h3>{t("admInvoices")}</h3>
        {data.invoices.length ? (
          <div className="gw-table-wrap"><table className="gw-table"><tbody>{data.invoices.map((invoice) => <tr key={invoice.id}><td>{invoice.number}</td><td><bdi>{invoice.description}</bdi></td><td>{money(invoice.amount, invoice.currency, language)}</td><td>{invoice.status}</td><td>{formatDateTime(invoice.created_at, language)}</td></tr>)}</tbody></table></div>
        ) : <p className="gw-small">{t("admNone")}</p>}
        <h3>{t("admAudit")}</h3>
        <AuditList t={t} language={language} entries={data.audit} />
      </section>
    </>
  );
}

function ProvidersTab({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { data, error, reload } = useLoad(adminApi.providers);
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" />;
  return (
    <>
      <section className="gw-panel" aria-labelledby="adm-ai">
        <h2 id="adm-ai">{t("admAiProviders")}</h2>
        <div className="gw-table-wrap">
          <table className="gw-table">
            <thead><tr><th>{t("admProvider")}</th><th>{t("admState")}</th><th>{t("admQuota")}</th><th>{t("admLastCheck")}</th><th /></tr></thead>
            <tbody>
              {Object.entries(data.ai).map(([name, health]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{!health.configured ? <span className="lb-badge">{t("admNotConfigured")}</span> : health.healthy ? <span className="lb-badge is-good">{t("admHealthy")}</span> : <span className="lb-badge is-warn">{t("admCoolingDown", { seconds: formatNumber(health.cooldown_seconds, language) })}</span>}</td>
                  <td>{health.daily_quota.limit ? t("admQuotaUsed", { used: formatNumber(health.daily_quota.used, language), limit: formatNumber(health.daily_quota.limit, language) }) : t("admNoLimit")}</td>
                  <td>{health.last_probe?.checked_at ? formatDateTime(health.last_probe.checked_at, language) : "—"}</td>
                  <td>{health.configured ? <button type="button" className="lb-button" onClick={() => adminApi.probe(name).then((result) => { toast(result.healthy ? t("admProbeOk") : t("admProbeFailed")); reload(); }).catch((caught) => toast(errorText(t, caught)))}>{t("admProbe")}</button> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="pf-grid-2">
        <section className="gw-panel" aria-labelledby="adm-routes">
          <h2 id="adm-routes">{t("admRouting")}</h2>
          <ul className="gw-plain-list">{Object.entries(data.routes).map(([task, routes]) => <li key={task}><b>{task}</b>: {routes.join(" → ")}</li>)}</ul>
        </section>
        <section className="gw-panel" aria-labelledby="adm-voices">
          <h2 id="adm-voices">{t("admVoices")}</h2>
          <ul className="gw-plain-list">
            {Object.entries(data.tts.engines).map(([name, engine]) => <li key={name}>{t("admVoiceEngine")}: {engine.configured ? (engine.healthy ? t("admHealthy") : t("admUnhealthy")) : t("admNotConfigured")}</li>)}
            <li>{t("admVoiceMetrics", { requests: formatNumber(data.tts.metrics.requests || 0, language), hits: formatNumber(data.tts.metrics.cache_hits || 0, language) })}</li>
            {data.voices.map((row) => <li key={row.language}>{row.language}: {formatNumber(row.voices, language)}</li>)}
          </ul>
        </section>
      </div>
    </>
  );
}

function FlagsTab({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { data, error, reload } = useLoad(adminApi.flags);
  const [key, setKey] = useState("");
  const [description, setDescription] = useState("");
  // Optimistic: the switch moves at once; it moves back if the server refuses the change.
  const [overrides, setOverrides] = useState<Record<string, { enabled: boolean; rollout: number }>>({});
  async function save(flag: { key: string; enabled: boolean; rollout: number; description?: string }) {
    setOverrides((current) => ({ ...current, [flag.key]: { enabled: flag.enabled, rollout: flag.rollout } }));
    try {
      await adminApi.setFlag(flag.key, flag);
      toast(t("admSaved"));
      reload();
    } catch (caught) {
      setOverrides((current) => {
        const next = { ...current };
        delete next[flag.key];
        return next;
      });
      toast(errorText(t, caught));
    }
  }
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" />;
  return (
    <section className="gw-panel" aria-labelledby="adm-flags">
      <h2 id="adm-flags">{t("admTabFlags")}</h2>
      <p className="gw-small">{t("admFlagsNote")}</p>
      <ul className="pf-flag-list">
        {data.flags.map((loaded) => ({ ...loaded, ...overrides[loaded.key] })).map((flag) => (
          <li key={flag.key} className="pf-flag">
            <div><b><code>{flag.key}</code></b><span className="gw-small"><bdi>{flag.description}</bdi></span></div>
            <label className="pf-switch"><input type="checkbox" checked={flag.enabled} onChange={(event) => void save({ key: flag.key, enabled: event.target.checked, rollout: flag.rollout })} /><span>{flag.enabled ? t("admOn") : t("admOff")}</span></label>
            <label className="pf-rollout">{t("admRollout")}
              <input type="range" min={0} max={100} step={5} defaultValue={flag.rollout} aria-valuetext={`${flag.rollout}%`} onMouseUp={(event) => void save({ key: flag.key, enabled: flag.enabled, rollout: Number(event.currentTarget.value) })} onKeyUp={(event) => void save({ key: flag.key, enabled: flag.enabled, rollout: Number(event.currentTarget.value) })} />
              <span>{formatNumber(flag.rollout, language)}%</span>
            </label>
          </li>
        ))}
      </ul>
      <form className="pf-inline-form" onSubmit={(event) => { event.preventDefault(); void save({ key, enabled: false, rollout: 100, description }).then(() => { setKey(""); setDescription(""); }); }}>
        <label className="rs-visually-hidden" htmlFor="adm-flag-key">{t("admFlagKey")}</label>
        <input id="adm-flag-key" className="lb-input" value={key} onChange={(event) => setKey(event.target.value)} placeholder={t("admFlagKey")} pattern="[a-z0-9_.\-]{2,64}" required />
        <label className="rs-visually-hidden" htmlFor="adm-flag-desc">{t("admFlagDescription")}</label>
        <input id="adm-flag-desc" className="lb-input" value={description} onChange={(event) => setDescription(event.target.value)} placeholder={t("admFlagDescription")} />
        <button type="submit" className="lb-button">{t("admAddFlag")}</button>
      </form>
    </section>
  );
}

function JobsTab({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { data, error, reload } = useLoad(adminApi.jobs);
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" />;
  return (
    <>
      <section className="gw-panel" aria-labelledby="adm-dead">
        <h2 id="adm-dead">{t("admDeadLetters")}</h2>
        <p className="gw-small">{t("admDeadLettersNote")}</p>
        {data.dead_letters.length ? (
          <div className="gw-table-wrap">
            <table className="gw-table">
              <thead><tr><th>{t("admJob")}</th><th>{t("admError")}</th><th>{t("admAttempts")}</th><th>{t("admState")}</th><th /></tr></thead>
              <tbody>
                {data.dead_letters.map((row) => (
                  <tr key={row.id}>
                    <td>{row.kind} · {row.source}<span className="gw-small"> {formatDateTime(row.created_at, language)}</span></td>
                    <td><code className="pf-code">{row.error}</code></td>
                    <td>{formatNumber(row.attempts, language)}</td>
                    <td>{row.status}</td>
                    <td className="pf-actions">
                      {row.status === "failed" ? <>
                        <button type="button" className="lb-button" onClick={() => adminApi.retry(row.id).then((result) => { toast(result.status === "resolved" ? t("admRetryOk") : t("admRetryFailed")); reload(); }).catch((caught) => toast(errorText(t, caught)))}>{t("admRetry")}</button>
                        <button type="button" className="lb-button" onClick={() => adminApi.discard(row.id).then(reload).catch((caught) => toast(errorText(t, caught)))}>{t("admDiscard")}</button>
                      </> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="pf-empty">{t("admNoDeadLetters")}</p>}
      </section>
      <section className="gw-panel" aria-labelledby="adm-runs">
        <h2 id="adm-runs">{t("admPipelineRuns")}</h2>
        {data.pipeline_runs.length ? (
          <div className="gw-table-wrap"><table className="gw-table"><tbody>{data.pipeline_runs.map((run) => (
            <tr key={run.run_id}><td><code>{run.run_id}</code></td><td>{run.engine}</td><td>{run.status}</td><td>{formatDateTime(run.started_at, language)}</td><td><bdi>{(run.params?.queries || []).join(", ")}</bdi></td></tr>
          ))}</tbody></table></div>
        ) : <p className="gw-small">{t("admNone")}</p>}
      </section>
    </>
  );
}

function MessagesTab({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { data, error, reload } = useLoad(adminApi.messages);
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" />;
  return (
    <section className="gw-panel" aria-labelledby="adm-messages">
      <h2 id="adm-messages">{t("admTabMessages")}</h2>
      {data.messages.length ? (
        <ul className="pf-messages">
          {data.messages.map((message) => (
            <li key={message.id} className={message.status === "closed" ? "is-closed" : ""}>
              <div className="pf-message-head"><b><bdi>{message.name}</bdi></b> <span className="gw-small"><bdi>{message.email}</bdi> · {message.topic} · {formatDateTime(message.created_at, language)}</span></div>
              <p dir="auto">{message.message}</p>
              <button type="button" className="lb-button" onClick={() => adminApi.messageStatus(message.id, message.status === "open" ? "closed" : "open").then(() => { toast(t("admSaved")); reload(); }).catch((caught) => toast(errorText(t, caught)))}>{message.status === "open" ? t("admMarkDone") : t("admReopen")}</button>
            </li>
          ))}
        </ul>
      ) : <p className="pf-empty">{t("admNoMessages")}</p>}
    </section>
  );
}

function StatusTab({ t, language, toast }: { t: SearchT; language: string; toast: (message: string) => void }) {
  const { data, error, reload } = useLoad(adminApi.incidents);
  const blank = { title: "", component: "ai", severity: "minor", status: "investigating", message: "" };
  const [form, setForm] = useState<typeof blank>(blank);
  const [editing, setEditing] = useState<string | undefined>(undefined);
  async function save() {
    try {
      await adminApi.saveIncident(form, editing);
      setForm(blank);
      setEditing(undefined);
      toast(t("admSaved"));
      reload();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }
  const choice = (name: keyof typeof blank, values: readonly string[], label: string, keyOf: (value: string) => SearchCopyKey) => (
    <fieldset className="pf-choice"><legend>{label}</legend>
      {values.map((value) => <button key={value} type="button" role="radio" aria-checked={form[name] === value} className={form[name] === value ? "is-active" : ""} onClick={() => setForm({ ...form, [name]: value })}>{t(keyOf(value))}</button>)}
    </fieldset>
  );
  return (
    <>
      <section className="gw-panel" aria-labelledby="adm-incident-form">
        <h2 id="adm-incident-form">{editing ? t("admUpdateIncident") : t("admNewIncident")}</h2>
        <form className="pf-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <label className="lb-field"><span>{t("admIncidentTitle")}</span><input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} minLength={3} required /></label>
          {choice("component", COMPONENTS, t("admComponent"), (value) => `siteComponent_${value}` as SearchCopyKey)}
          {choice("severity", SEVERITIES, t("admSeverity"), (value) => `admSeverity_${value}` as SearchCopyKey)}
          {choice("status", STATES, t("admState"), (value) => `siteIncident_${value}` as SearchCopyKey)}
          <label className="lb-field"><span>{t("admIncidentMessage")}</span><textarea rows={3} value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} /></label>
          <div className="pf-actions"><button type="submit" className="lb-button lb-button-primary">{t("admPublish")}</button>{editing ? <button type="button" className="lb-button" onClick={() => { setEditing(undefined); setForm(blank); }}>{t("admCancel")}</button> : null}</div>
        </form>
      </section>
      <section className="gw-panel" aria-labelledby="adm-incidents">
        <h2 id="adm-incidents">{t("admIncidents")}</h2>
        {error ? <p className="pf-empty" role="alert">{errorText(t, error)}</p> : !data ? <div className="pf-skel" /> : data.incidents.length ? (
          <ul className="pf-messages">
            {data.incidents.map((incident) => (
              <li key={incident.id} className={incident.status === "resolved" ? "is-closed" : ""}>
                <div className="pf-message-head"><b><bdi>{incident.title}</bdi></b> <span className="gw-small">{t(`siteComponent_${incident.component}` as SearchCopyKey)} · {t(`admSeverity_${incident.severity}` as SearchCopyKey)} · {t(`siteIncident_${incident.status}` as SearchCopyKey)} · {formatDateTime(incident.updated_at, language)}</span></div>
                {incident.message ? <p dir="auto">{incident.message}</p> : null}
                <button type="button" className="lb-button" onClick={() => { setEditing(incident.id); setForm({ title: incident.title, component: incident.component, severity: incident.severity, status: incident.status, message: incident.message }); }}>{t("admEdit")}</button>
              </li>
            ))}
          </ul>
        ) : <p className="pf-empty">{t("admNoIncidents")}</p>}
      </section>
    </>
  );
}

function AuditList({ t, language, entries }: { t: SearchT; language: string; entries: AuditEntry[] }) {
  if (!entries.length) return <p className="gw-small">{t("admNone")}</p>;
  return (
    <div className="gw-table-wrap">
      <table className="gw-table">
        <thead><tr><th>{t("admWhen")}</th><th>{t("admWho")}</th><th>{t("admAction")}</th><th>{t("admTarget")}</th><th>{t("admDetails")}</th></tr></thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}><td>{formatDateTime(entry.created_at, language)}</td><td><bdi>{entry.actor_id}</bdi></td><td><code>{entry.action}</code></td><td><bdi>{entry.target || "—"}</bdi></td><td><code className="pf-code">{JSON.stringify(entry.detail)}</code></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTab({ t, language }: { t: SearchT; language: string }) {
  const { data, error } = useLoad(adminApi.audit);
  if (error) return <p className="pf-empty" role="alert">{errorText(t, error)}</p>;
  if (!data) return <div className="pf-skel" />;
  return <section className="gw-panel" aria-labelledby="adm-audit"><h2 id="adm-audit">{t("admTabAudit")}</h2><p className="gw-small">{t("admAuditNote")}</p><AuditList t={t} language={language} entries={data.entries} /></section>;
}

export function AdminPage({ interfaceLanguage }: { interfaceLanguage: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const [access, setAccess] = useState<"checking" | "ok" | "denied">("checking");
  const [deniedCode, setDeniedCode] = useState<unknown>(null);
  useEffect(() => {
    adminApi.me().then(() => setAccess("ok")).catch((caught) => { setDeniedCode(caught); setAccess("denied"); });
  }, []);
  const props = useMemo(() => ({ t, language: interfaceLanguage, toast }), [interfaceLanguage, t, toast]);
  return (
    <PageShell language={interfaceLanguage} title={t("admTitle")} subtitle={t("admSubtitle")} toastText={toastText} className="pf-admin">
      {access === "checking" ? <div className="pf-skel" role="status" aria-label={t("admLoading")} /> : access === "denied" ? (
        <div className="pf-empty" role="alert"><h2>{t("admDenied")}</h2><p>{errorText(t, deniedCode)}</p></div>
      ) : (
        <>
          <nav className="lb-tabs" aria-label={t("admTitle")}>
            {TABS.map(([path, key]) => <NavLink key={path} to={`/admin${path ? `/${path}` : ""}`} end={!path} className={({ isActive }) => `lb-tab${isActive ? " is-active" : ""}`}>{t(key)}</NavLink>)}
          </nav>
          <Routes>
            <Route index element={<OverviewTab {...props} />} />
            <Route path="users" element={<UsersTab {...props} />} />
            <Route path="users/:userId" element={<UserView {...props} />} />
            <Route path="providers" element={<ProvidersTab {...props} />} />
            <Route path="flags" element={<FlagsTab {...props} />} />
            <Route path="jobs" element={<JobsTab {...props} />} />
            <Route path="messages" element={<MessagesTab {...props} />} />
            <Route path="status" element={<StatusTab {...props} />} />
            <Route path="audit" element={<AuditTab {...props} />} />
          </Routes>
        </>
      )}
    </PageShell>
  );
}
