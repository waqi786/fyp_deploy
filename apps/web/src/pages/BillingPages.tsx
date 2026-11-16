/** Pricing, Plans & usage (credit windows, packs, history, invoices) and the sandbox checkout page. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { SearchCopyKey } from "./search/copy";
import { ConfirmButton, EmptyState, ErrorLine, Select, SkeletonRows, SparkGlyph, CheckGlyph, formatNumber } from "./library/ui";
import { billingApi, money, openInvoice, teamsApi, type BillingMe, type CheckoutSession, type Currency, type Interval, type Invoice, type Pack, type Plan, type TeamSummary } from "./platform/platformApi";
import { Meter, PageShell, Stat, errorText, formatDate, usePlatform } from "./platform/shared";

const PLAN_KEYS: Record<Plan["id"], SearchCopyKey> = { free: "billPlanFree", pro: "billPlanPro", team: "billPlanTeam", institution: "billPlanInstitution" };
const PLAN_BLURB: Record<Plan["id"], SearchCopyKey> = { free: "billPlanFreeBlurb", pro: "billPlanProBlurb", team: "billPlanTeamBlurb", institution: "billPlanInstitutionBlurb" };
const FEATURE_KEYS: Record<string, SearchCopyKey> = {
  search: "billFeatSearch", reader_basic: "billFeatReaderBasic", library: "billFeatLibrary", compare_3: "billFeatCompare3", citations: "billFeatCitations", one_language: "billFeatLanguage",
  everything_free: "billFeatEverythingFree", research_mode: "billFeatResearch", reader_full: "billFeatReaderFull", compare_unlimited: "billFeatCompareUnlimited", gaps_ai: "billFeatGaps", write_grounded: "billFeatWrite", exports_all: "billFeatExports", priority: "billFeatPriority",
  everything_pro: "billFeatEverythingPro", shared_projects: "billFeatShared", comments_mentions: "billFeatComments", supervisor_reviews: "billFeatSupervisor", pooled_credits: "billFeatPooled", team_admin: "billFeatAdmin", audit_log: "billFeatAudit",
  everything_team: "billFeatEverythingTeam", sso: "billFeatSso", invoicing: "billFeatInvoicing", data_residency: "billFeatResidency", dedicated_support: "billFeatSupport",
};
const STATUS_KEYS: Record<string, SearchCopyKey> = { active: "billStatusActive", trialing: "billStatusTrialing", past_due: "billStatusPastDue", canceled: "billStatusCanceled" };
const ACTION_KEYS: Record<string, SearchCopyKey> = { search: "billActionSearch", research: "billActionResearch", ask: "billActionAsk", summary: "billActionSummary", chat: "billActionChat", translate_pages: "billActionTranslate" };
const CURRENCY_KEY = "resora-billing-currency";

function storedCurrency(): Currency {
  try {
    const value = window.localStorage.getItem(CURRENCY_KEY);
    if (value === "usd" || value === "pkr") return value;
  } catch { /* per-viewer convenience only */ }
  return typeof navigator !== "undefined" && /(-PK|^ur)/i.test(navigator.language) ? "pkr" : "usd";
}

function useCurrency(): [Currency, (value: Currency) => void] {
  const [currency, setCurrency] = useState<Currency>(storedCurrency);
  return [currency, (value) => { setCurrency(value); try { window.localStorage.setItem(CURRENCY_KEY, value); } catch { /* ignore */ } }];
}

function Toggle<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void; label: string }) {
  return (
    <div className="lb-segmented" role="group" aria-label={label}>
      {options.map((option) => <button key={option.value} type="button" className={value === option.value ? "is-active" : ""} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}
    </div>
  );
}

// =====================================================================================================================
// Pricing

export function PricingPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [data, setData] = useState<{ plans: Plan[]; packs: Pack[]; sandbox: boolean } | null>(null);
  const [me, setMe] = useState<BillingMe | null>(null);
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [error, setError] = useState("");
  const [currency, setCurrency] = useCurrency();
  const [interval, setInterval] = useState<Interval>("year");
  const [seats, setSeats] = useState(3);
  const [teamId, setTeamId] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    billingApi.plans().then(setData).catch((caught) => setError(errorText(t, caught)));
    billingApi.me().then(setMe).catch(() => undefined);
    teamsApi.list().then((result) => { const owned = result.teams.filter((team) => team.role === "owner"); setTeams(owned); setTeamId((current) => current || owned[0]?.id || ""); }).catch(() => undefined);
    if (params.get("checkout") === "canceled") toast(t("billCheckoutCanceled"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function choose(plan: Plan) {
    if (!plan.checkout) return;
    setBusy(plan.id);
    try {
      const session = await billingApi.checkout({ kind: "subscription", plan: plan.id, interval, currency, seats: plan.per_seat ? seats : 1, team_id: plan.per_seat ? teamId : undefined });
      if (session.url.startsWith("/")) navigate(session.url);
      else window.location.assign(session.url);
    } catch (caught) {
      toast(errorText(t, caught));
    } finally {
      setBusy("");
    }
  }

  async function buyPack(pack: Pack) {
    setBusy(pack.id);
    try {
      const session = await billingApi.checkout({ kind: "topup", pack: pack.id, currency });
      if (session.url.startsWith("/")) navigate(session.url);
      else window.location.assign(session.url);
    } catch (caught) {
      toast(errorText(t, caught));
    } finally {
      setBusy("");
    }
  }

  return (
    <PageShell language={interfaceLanguage} title={t("billPricingTitle")} subtitle={t("billPricingSubtitle")} toastText={toastText}
      actions={<>
        <Toggle label={t("billInterval")} value={interval} onChange={setInterval} options={[{ value: "month", label: t("billMonthly") }, { value: "year", label: t("billYearly") }]} />
        <Toggle label={t("billCurrency")} value={currency} onChange={setCurrency} options={[{ value: "usd", label: "USD" }, { value: "pkr", label: "PKR" }]} />
      </>}>
      {error ? <ErrorLine message={error} t={t} /> : !data ? <SkeletonRows rows={4} /> : (
        <>
          {data.sandbox ? <p className="gw-disclaimer" role="note">{t("billSandboxNote")}</p> : null}
          <div className="pf-plans">
            {data.plans.map((plan) => {
              const current = me?.plan === plan.id;
              const unit = plan.prices[currency][interval];
              const total = unit * (plan.per_seat ? seats : 1);
              const yearlySaving = plan.prices[currency].month * 12 - plan.prices[currency].year;
              return (
                <article key={plan.id} className={`pf-plan${plan.id === "pro" ? " is-featured" : ""}${current ? " is-current" : ""}`} aria-labelledby={`plan-${plan.id}`}>
                  <header>
                    <h2 id={`plan-${plan.id}`}>{t(PLAN_KEYS[plan.id])}</h2>
                    {plan.id === "pro" ? <span className="lb-badge">{t("billMostPopular")}</span> : null}
                    {current ? <span className="lb-badge pf-badge-current">{t("billCurrentPlan")}</span> : null}
                  </header>
                  <p className="gw-small">{t(PLAN_BLURB[plan.id])}</p>
                  <div className="pf-price">
                    {plan.id === "institution" ? <b>{t("billCustomPrice")}</b> : unit === 0 ? <b>{t("billFreePrice")}</b> : (
                      <>
                        <b>{money(unit, currency, interfaceLanguage)}</b>
                        <span>{plan.per_seat ? t(interval === "year" ? "billPerSeatYear" : "billPerSeatMonth") : t(interval === "year" ? "billPerYear" : "billPerMonth")}</span>
                      </>
                    )}
                  </div>
                  {interval === "year" && yearlySaving > 0 ? <p className="pf-saving">{t("billYearlySaving", { amount: money(yearlySaving, currency, interfaceLanguage) })}</p> : null}
                  {plan.trial_days ? <p className="gw-small">{t("billTrialDays", { days: plan.trial_days })}</p> : null}
                  <dl className="pf-limits">
                    <div><dt>{t("billWindowSession")}</dt><dd>{formatNumber(plan.limits.session, interfaceLanguage)}</dd></div>
                    <div><dt>{t("billWindowWeek")}</dt><dd>{formatNumber(plan.limits.week, interfaceLanguage)}</dd></div>
                    <div><dt>{t("billWindowMonth")}</dt><dd>{formatNumber(plan.limits.month, interfaceLanguage)}</dd></div>
                  </dl>
                  <ul className="pf-features">{plan.features.map((feature) => <li key={feature}><CheckGlyph />{t(FEATURE_KEYS[feature] || "billFeatSearch")}</li>)}</ul>
                  {plan.per_seat && plan.checkout ? (
                    <div className="pf-seats">
                      <label className="lb-field"><span>{t("billSeats")}</span>
                        <input type="number" min={plan.min_seats} max={plan.max_seats} value={seats} onChange={(event) => setSeats(Math.max(plan.min_seats, Math.min(plan.max_seats, Number(event.target.value) || plan.min_seats)))} />
                      </label>
                      {teams.length ? <Select label={t("billForTeam")} value={teamId} onChange={setTeamId} options={teams.map((team) => ({ value: team.id, label: team.name }))} /> : <Link className="lb-text-button" to="/teams">{t("billCreateTeamFirst")}</Link>}
                      <p className="gw-small">{t("billTotal", { amount: money(total, currency, interfaceLanguage) })}</p>
                    </div>
                  ) : null}
                  <div className="pf-plan-action">
                    {plan.id === "institution" ? <a className="lb-button lb-button-quiet" href="mailto:sales@resora.app">{t("billContactSales")}</a>
                      : plan.id === "free" ? <span className="gw-small">{current ? t("billCurrentPlan") : t("billIncluded")}</span>
                      : <button type="button" className={`lb-button ${plan.id === "pro" ? "lb-button-primary" : "lb-button-quiet"}`} disabled={busy === plan.id || current || (plan.per_seat && !teamId)} onClick={() => void choose(plan)}>{current ? t("billCurrentPlan") : busy === plan.id ? t("billOpening") : plan.trial_days ? t("billStartTrial") : t("billChoosePlan")}</button>}
                  </div>
                </article>
              );
            })}
          </div>

          <section className="gw-panel pf-packs" aria-labelledby="packs-title">
            <div className="lb-section-head"><h2 id="packs-title">{t("billPacksTitle")}</h2></div>
            <p className="lb-section-note">{t("billPacksNote")}</p>
            <div className="pf-pack-row">
              {data.packs.map((pack) => (
                <div key={pack.id} className="pf-pack">
                  <b>{t("billCredits", { count: formatNumber(pack.credits, interfaceLanguage) })}</b>
                  <span>{money(pack.prices[currency], currency, interfaceLanguage)}</span>
                  <button type="button" className="lb-button lb-button-quiet" disabled={busy === pack.id} onClick={() => void buyPack(pack)}>{t("billBuy")}</button>
                </div>
              ))}
            </div>
          </section>
          <p className="lb-section-note pf-fineprint">{t("billFinePrint")}</p>
        </>
      )}
    </PageShell>
  );
}

// =====================================================================================================================
// Plans & usage

export function UsagePage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const [params, setParams] = useSearchParams();
  const [me, setMe] = useState<BillingMe | null>(null);
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [usage, list] = await Promise.all([billingApi.me(), billingApi.invoices()]);
      setMe(usage);
      setInvoices(list.invoices);
    } catch (caught) {
      setError(errorText(t, caught));
    }
  }, [t]);

  useEffect(() => {
    void load();
    if (params.get("checkout") === "success") {
      toast(t("billCheckoutSuccess"));
      params.delete("checkout");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function act(action: () => Promise<unknown>, message: SearchCopyKey) {
    try {
      await action();
      toast(t(message));
      await load();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  const sub = me?.subscription;
  const byAction = useMemo(() => {
    const totals = new Map<string, number>();
    for (const row of me?.history || []) totals.set(row.action, (totals.get(row.action) || 0) + row.credits);
    return [...totals.entries()].sort((a, b) => b[1] - a[1]);
  }, [me]);
  const byDay = useMemo(() => {
    const totals = new Map<string, number>();
    for (const row of me?.history || []) totals.set(row.day, (totals.get(row.day) || 0) + row.credits);
    return [...totals.entries()].sort();
  }, [me]);

  return (
    <PageShell language={interfaceLanguage} title={t("billUsageTitle")} subtitle={t("billUsageSubtitle")} toastText={toastText}
      actions={<Link className="lb-button lb-button-primary" to="/pricing"><SparkGlyph />{t("billSeePlans")}</Link>}>
      {error ? <ErrorLine message={error} onRetry={() => void load()} t={t} /> : !me ? <SkeletonRows rows={5} /> : (
        <>
          <section className="gw-panel pf-current" aria-labelledby="current-plan">
            <div className="pf-current-head">
              <div>
                <p className="lb-menu-label">{t("billYourPlan")}</p>
                <h2 id="current-plan">{t(PLAN_KEYS[me.plan] || "billPlanFree")}{me.usage.pooled ? <span className="lb-badge">{t("billPooled", { seats: me.seats })}</span> : null}</h2>
                {sub ? (
                  <p className="gw-small">
                    {t(STATUS_KEYS[sub.status] || "billStatusActive")} · {sub.status === "trialing" ? t("billTrialEnds", { date: formatDate(sub.trial_end || sub.current_period_end, interfaceLanguage) }) : sub.cancel_at_period_end ? t("billEndsOn", { date: formatDate(sub.current_period_end, interfaceLanguage) }) : t("billRenewsOn", { date: formatDate(sub.current_period_end, interfaceLanguage) })}
                  </p>
                ) : <p className="gw-small">{t("billFreeForever")}</p>}
                {sub?.pending_plan ? <p className="pf-notice">{t("billScheduledChange", { plan: t(PLAN_KEYS[sub.pending_plan as Plan["id"]] || "billPlanFree"), date: formatDate(sub.current_period_end, interfaceLanguage) })}</p> : null}
                {sub?.status === "past_due" ? <p className="pf-notice is-warn">{t("billPastDueNote")}</p> : null}
              </div>
              {sub && !sub.team_id ? (
                <div className="lb-head-actions">
                  {sub.cancel_at_period_end ? <button type="button" className="lb-button lb-button-primary" onClick={() => void act(billingApi.resume, "billResumed")}>{t("billResume")}</button>
                    : <ConfirmButton label={t("billCancel")} confirmLabel={t("billConfirmCancel")} onConfirm={() => void act(billingApi.cancel, "billCanceledNote")} />}
                  {sub.interval === "month" && sub.plan !== "free" ? <button type="button" className="lb-button lb-button-quiet" onClick={() => void act(() => billingApi.change(sub.plan, "year", sub.seats), "billSwitchedYearly")}>{t("billSwitchYearly")}</button> : null}
                </div>
              ) : null}
            </div>
          </section>

          <section className="gw-panel" aria-labelledby="windows-title">
            <div className="lb-section-head"><h2 id="windows-title">{t("billCreditsTitle")}</h2></div>
            <p className="lb-section-note">{t("billCreditsNote")}</p>
            <div className="pf-meters">{me.usage.windows.map((window) => <Meter key={window.scope} t={t} language={interfaceLanguage} window={window} />)}</div>
            <div className="pf-stats">
              <Stat label={t("billPackBalance")} value={formatNumber(me.topup_balance, interfaceLanguage)} note={<Link to="/pricing" className="lb-text-button">{t("billBuyMore")}</Link>} />
            </div>
          </section>

          <section className="gw-panel" aria-labelledby="history-title">
            <div className="lb-section-head"><h2 id="history-title">{t("billHistoryTitle")}</h2></div>
            {!byDay.length ? <EmptyState title={t("billNoUsage")} body={t("billNoUsageBody")} /> : (
              <>
                <div className="gw-chart" role="img" aria-label={t("billHistoryTitle")}>
                  {(() => { const max = Math.max(1, ...byDay.map(([, value]) => value)); return byDay.map(([day, value]) => (
                    <div key={day} className="gw-bar" title={`${day}: ${value}`}>
                      <span className="gw-bar-fill" style={{ blockSize: `${Math.max(2, (value / max) * 100)}%` }} />
                      <span className="gw-bar-value">{formatNumber(value, interfaceLanguage)}</span>
                      <span className="gw-bar-label">{day.slice(5)}</span>
                    </div>
                  )); })()}
                </div>
                <div className="gw-table-wrap"><table className="gw-table">
                  <thead><tr><th>{t("billAction")}</th><th className="num">{t("billCreditsUsed")}</th><th className="num">{t("billCostEach")}</th></tr></thead>
                  <tbody>{byAction.map(([action, value]) => <tr key={action}><th scope="row">{t(ACTION_KEYS[action] || "billActionOther")}</th><td className="num">{formatNumber(value, interfaceLanguage)}</td><td className="num">{formatNumber(me.costs[action] ?? 0, interfaceLanguage)}</td></tr>)}</tbody>
                </table></div>
              </>
            )}
          </section>

          <section className="gw-panel" aria-labelledby="invoices-title">
            <div className="lb-section-head"><h2 id="invoices-title">{t("billInvoicesTitle")}</h2></div>
            {!invoices?.length ? <EmptyState title={t("billNoInvoices")} /> : (
              <div className="gw-table-wrap"><table className="gw-table">
                <thead><tr><th>{t("billInvoiceNumber")}</th><th>{t("billInvoiceDate")}</th><th>{t("billInvoiceFor")}</th><th className="num">{t("billAmount")}</th><th>{t("billInvoiceStatus")}</th><th /></tr></thead>
                <tbody>{invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <th scope="row"><bdi>{invoice.number}</bdi></th>
                    <td>{formatDate(invoice.created_at, interfaceLanguage)}</td>
                    <td><bdi>{invoice.description}</bdi></td>
                    <td className="num">{money(invoice.amount, invoice.currency, interfaceLanguage)}</td>
                    <td>{t(invoice.status === "paid" ? "billPaid" : invoice.status === "refunded" ? "billRefunded" : "billOpen")}</td>
                    <td><button type="button" className="lb-text-button" onClick={() => void openInvoice(invoice.id).catch(() => toast(t("libErrorGeneric")))}>{t("billView")}</button></td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}
    </PageShell>
  );
}

// =====================================================================================================================
// Sandbox checkout (real providers redirect to their own hosted page instead)

export function CheckoutPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState<CheckoutSession | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    billingApi.session(sessionId).then(setSession).catch((caught) => setError(errorText(t, caught)));
  }, [sessionId, t]);

  async function decide(decision: "complete" | "cancel") {
    setBusy(true);
    try {
      const result = await billingApi.sandbox(sessionId, decision);
      setSession(result);
      if (result.status === "completed") navigate("/usage?checkout=success");
      else navigate("/pricing?checkout=canceled");
    } catch (caught) {
      toast(errorText(t, caught));
    } finally {
      setBusy(false);
    }
  }

  const what = session ? (session.kind === "topup" ? t("billCheckoutPack", { pack: (session.pack || "").replace("credits_", "") }) : `${t(PLAN_KEYS[(session.plan || "free") as Plan["id"]])} · ${t(session.interval === "year" ? "billYearly" : "billMonthly")}${session.seats > 1 ? ` · ${t("billSeatsCount", { count: session.seats })}` : ""}`) : "";
  return (
    <PageShell language={interfaceLanguage} title={t("billCheckoutTitle")} subtitle={t("billCheckoutSubtitle")} toastText={toastText}>
      {error ? <ErrorLine message={error} t={t} /> : !session ? <SkeletonRows rows={3} /> : (
        <section className="gw-panel pf-checkout" aria-labelledby="checkout-what">
          <p className="gw-disclaimer" role="note">{t("billSandboxPay")}</p>
          <h2 id="checkout-what"><bdi>{what}</bdi></h2>
          <p className="pf-checkout-amount">{money(session.amount, session.currency, interfaceLanguage)}</p>
          {session.status !== "open" ? <p className="pf-notice">{t(session.status === "completed" ? "billSessionDone" : session.status === "expired" ? "billSessionExpired" : "billSessionCanceled")}</p> : (
            <div className="lb-head-actions">
              <button type="button" className="lb-button lb-button-primary" disabled={busy} onClick={() => void decide("complete")}>{t("billPayNow")}</button>
              <button type="button" className="lb-button lb-button-quiet" disabled={busy} onClick={() => void decide("cancel")}>{t("libCancel")}</button>
            </div>
          )}
        </section>
      )}
    </PageShell>
  );
}

