/**
 * Public website (Part 18): Landing (/welcome), Features, About, Help center (searchable FAQ), Contact, Status,
 * Changelog, Legal documents, newsletter confirmation and the referral page (/invite).
 * Same theme and building blocks as the app; every label comes from the catalog (English + Urdu).
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { comparisonHeaders } from "./compare/compareApi";
import { LibraryError, libraryApiBase } from "./library/libraryApi";
import { directionOf, formatNumber } from "./library/ui";
import { billingApi, money, type Plan } from "./platform/platformApi";
import { errorText, formatDateTime, usePlatform } from "./platform/shared";
import { useSearchCopy, type SearchCopyKey, type SearchT } from "./search/copy";
import { LEGAL_DOCS, LEGAL_REVIEW_NOTE, legalDoc } from "./site/legalDocs";
import { useSeo } from "./site/siteRuntime";
import "./site/SitePages.css";

async function siteCall<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${libraryApiBase}/site${path}`, { method: body === undefined ? "GET" : "POST", headers: { ...comparisonHeaders(), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new LibraryError("network");
  }
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
    throw new LibraryError(detail?.detail?.code || (response.status === 429 ? "rate_limited" : "unavailable"), response.status);
  }
  return (await response.json()) as T;
}

type StatusPayload = { overall: string; components: Record<string, string>; incidents: Array<{ id: string; title: string; component: string; severity: string; status: string; message: string; created_at: string; updated_at: string; resolved_at: string | null }>; checked_at: string };
type Referral = { code: string; invited: number; rewarded: number; credits_earned: number; credits_per_referral: number; max_rewards: number; redeemed_code: string | null };

const SITE_ERRORS: Record<string, SearchCopyKey> = {
  invalid_email: "siteErrorEmail", consent_required: "siteErrorConsent", message_too_short: "siteErrorShort", rate_limited: "siteErrorRate",
  token_invalid: "siteErrorToken", referral_invalid: "refErrorInvalid", referral_self: "refErrorSelf", referral_used: "refErrorUsed", referral_circular: "refErrorCircular",
};
function siteError(t: SearchT, caught: unknown) {
  const code = caught instanceof LibraryError ? caught.code : "";
  return SITE_ERRORS[code] ? t(SITE_ERRORS[code]) : errorText(t, caught);
}

const FEATURES: Array<{ key: string; title: SearchCopyKey; body: SearchCopyKey; to: string }> = [
  { key: "search", title: "siteFeatSearchTitle", body: "siteFeatSearchBody", to: "/search" },
  { key: "reader", title: "siteFeatReaderTitle", body: "siteFeatReaderBody", to: "/reader" },
  { key: "listen", title: "siteFeatListenTitle", body: "siteFeatListenBody", to: "/reader" },
  { key: "compare", title: "siteFeatCompareTitle", body: "siteFeatCompareBody", to: "/comparison" },
  { key: "gaps", title: "siteFeatGapsTitle", body: "siteFeatGapsBody", to: "/gaps" },
  { key: "write", title: "siteFeatWriteTitle", body: "siteFeatWriteBody", to: "/writing" },
  { key: "library", title: "siteFeatLibraryTitle", body: "siteFeatLibraryBody", to: "/library" },
  { key: "teams", title: "siteFeatTeamsTitle", body: "siteFeatTeamsBody", to: "/teams" },
  { key: "insights", title: "siteFeatInsightsTitle", body: "siteFeatInsightsBody", to: "/insights" },
];
const FAQ: Array<[SearchCopyKey, SearchCopyKey, string]> = [
  ["siteFaqFreeQ", "siteFaqFreeA", "billing"], ["siteFaqCreditsQ", "siteFaqCreditsA", "billing"], ["siteFaqSourcesQ", "siteFaqSourcesA", "search"],
  ["siteFaqLanguagesQ", "siteFaqLanguagesA", "languages"], ["siteFaqPrivacyQ", "siteFaqPrivacyA", "privacy"], ["siteFaqListenQ", "siteFaqListenA", "listen"],
  ["siteFaqTeamsQ", "siteFaqTeamsA", "teams"], ["siteFaqCancelQ", "siteFaqCancelA", "billing"], ["siteFaqAccuracyQ", "siteFaqAccuracyA", "ai"],
  ["siteFaqUploadQ", "siteFaqUploadA", "reader"], ["siteFaqStudentQ", "siteFaqStudentA", "billing"], ["siteFaqDeleteQ", "siteFaqDeleteA", "privacy"],
];
const CHANGELOG: Array<{ date: string; title: SearchCopyKey; body: SearchCopyKey }> = [
  { date: "2026-11-15", title: "siteLogListenTitle", body: "siteLogListenBody" },
  { date: "2026-11-15", title: "siteLogAdminTitle", body: "siteLogAdminBody" },
  { date: "2026-11-14", title: "siteLogPlansTitle", body: "siteLogPlansBody" },
  { date: "2026-11-14", title: "siteLogCatalogTitle", body: "siteLogCatalogBody" },
  { date: "2026-11-01", title: "siteLogWriteTitle", body: "siteLogWriteBody" },
  { date: "2026-10-20", title: "siteLogCompareTitle", body: "siteLogCompareBody" },
];
const STATUS_KEYS: Record<string, SearchCopyKey> = { operational: "siteStatusOperational", degraded: "siteStatusDegraded", partial_outage: "siteStatusPartial", major_outage: "siteStatusMajor", maintenance: "siteStatusMaintenance" };

function SiteShell({ language, children, className = "" }: { language: string; children: ReactNode; className?: string }) {
  const t = useSearchCopy(language);
  return (
    <section className={`rs-search lb-library gw-page pf-page site-page ${className}`} dir={directionOf(language)} lang={language} data-no-translate="">
      <div className="lb-shell">{children}</div>
      <footer className="site-footer">
        <nav aria-label={t("siteFooterProduct")}>
          <b>{t("siteFooterProduct")}</b>
          <Link to="/features">{t("siteNavFeatures")}</Link><Link to="/pricing">{t("navPricing")}</Link><Link to="/changelog">{t("siteNavChangelog")}</Link><Link to="/status">{t("siteNavStatus")}</Link>
        </nav>
        <nav aria-label={t("siteFooterCompany")}>
          <b>{t("siteFooterCompany")}</b>
          <Link to="/about">{t("siteNavAbout")}</Link><Link to="/help">{t("siteNavHelp")}</Link><Link to="/contact">{t("siteNavContact")}</Link><Link to="/invite">{t("refNav")}</Link>
        </nav>
        <nav aria-label={t("siteFooterLegal")}>
          <b>{t("siteFooterLegal")}</b>
          {LEGAL_DOCS.map((doc) => <Link key={doc.slug} to={`/legal/${doc.slug}`}>{t(`siteLegal_${doc.slug.replace("-", "_")}` as SearchCopyKey)}</Link>)}
          <Link to="/open-source">{t("siteOpenSource")}</Link>
          <button type="button" className="site-link-button" onClick={() => window.dispatchEvent(new Event("resora:cookie-notice"))}>{t("siteCookieSettings")}</button>
        </nav>
        <p className="site-copy">{t("siteCopyright", { year: new Date().getFullYear() })}</p>
      </footer>
    </section>
  );
}

function SiteHead({ title, subtitle, eyebrow }: { title: string; subtitle?: string; eyebrow?: string }) {
  return (
    <header className="site-head">
      {eyebrow ? <span className="site-eyebrow">{eyebrow}</span> : null}
      <h1>{title}</h1>
      {subtitle ? <p>{subtitle}</p> : null}
    </header>
  );
}

function FeatureIcon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    search: "M10.5 4a6.5 6.5 0 1 0 4.1 11.5l4.7 4.7 1.4-1.4-4.7-4.7A6.5 6.5 0 0 0 10.5 4z",
    reader: "M4 5h7a3 3 0 0 1 3 3v11a2 2 0 0 0-2-2H4zM20 5h-4a3 3 0 0 0-2 1",
    listen: "M4 15v-3a8 8 0 0 1 16 0v3M3 14h4v6H3zM17 14h4v6h-4z",
    compare: "M4 5h7v14H4zM13 5h7v14h-7z",
    gaps: "M4 19 9 9l4 6 3-4 4 8z",
    write: "M5 19l1-4 10-10 3 3-10 10zM14 6l3 3",
    library: "M5 4h3v16H5zM10 4h3v16h-3zM15 5l3-1 3 15-3 1z",
    teams: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20a6 6 0 0 1 12 0M12 20a6 6 0 0 1 10 0",
    insights: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round"><path d={paths[name] || paths.search} /></svg>;
}

function NewsletterForm({ t, language, source }: { t: SearchT; language: string; source: string }) {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<"idle" | "busy" | "pending" | "error">("idle");
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState("busy");
    try {
      await siteCall("/newsletter", { email, consent, language, source });
      setState("pending");
    } catch (caught) {
      setError(siteError(t, caught));
      setState("error");
    }
  }
  if (state === "pending") return <p className="site-success" role="status">{t("siteNewsletterPending")}</p>;
  return (
    <form className="site-newsletter" onSubmit={submit}>
      <label className="lb-field"><span>{t("siteEmail")}</span><input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder={t("siteEmailPlaceholder")} autoComplete="email" /></label>
      <label className="site-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>{t("siteNewsletterConsent")}</span></label>
      <button type="submit" className="lb-button lb-button-primary" disabled={state === "busy"}>{t("siteSubscribe")}</button>
      {state === "error" ? <p className="site-error" role="alert">{error}</p> : null}
    </form>
  );
}

export function LandingPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [open, setOpen] = useState<number | null>(0);
  useSeo(t("siteLandingTitle"), t("siteLandingSubtitle"), "/welcome");
  useEffect(() => {
    billingApi.plans().then((data) => setPlans(Array.isArray(data?.plans) ? data.plans : [])).catch(() => setPlans([]));
  }, []);
  const pro = plans.find((plan) => plan.id === "pro");
  const currency = language === "ur" ? "pkr" : "usd";
  return (
    <SiteShell language={language} className="site-landing">
      <section className="site-hero" aria-labelledby="site-hero-title">
        <span className="site-eyebrow">{t("siteHeroEyebrow")}</span>
        <h1 id="site-hero-title">{t("siteLandingTitle")}</h1>
        <p className="site-lead">{t("siteLandingSubtitle")}</p>
        <form className="site-hero-search" role="search" onSubmit={(event) => { event.preventDefault(); navigate(query.trim() ? `/search?q=${encodeURIComponent(query.trim())}` : "/search"); }}>
          <label className="rs-visually-hidden" htmlFor="site-q">{t("siteHeroSearch")}</label>
          <input id="site-q" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("siteHeroSearch")} dir="auto" />
          <button type="submit" className="lb-button lb-button-primary">{t("siteStartFree")}</button>
        </form>
        <ul className="site-proof">
          <li>{t("siteProofSources")}</li><li>{t("siteProofCited")}</li><li>{t("siteProofLanguages")}</li>
        </ul>
      </section>

      <section className="site-section" aria-labelledby="site-features">
        <h2 id="site-features">{t("siteFeaturesTitle")}</h2>
        <div className="site-grid">
          {FEATURES.map((feature) => (
            <Link key={feature.key} to={feature.to} className="site-card">
              <span className="site-card-icon"><FeatureIcon name={feature.key} /></span>
              <b>{t(feature.title)}</b>
              <span>{t(feature.body)}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="site-section site-split" aria-labelledby="site-how">
        <div>
          <h2 id="site-how">{t("siteHowTitle")}</h2>
          <ol className="site-steps">
            <li><b>{t("siteHowFind")}</b><span>{t("siteHowFindBody")}</span></li>
            <li><b>{t("siteHowUnderstand")}</b><span>{t("siteHowUnderstandBody")}</span></li>
            <li><b>{t("siteHowWrite")}</b><span>{t("siteHowWriteBody")}</span></li>
          </ol>
        </div>
        <div className="site-panel">
          <h3>{t("siteLanguagesTitle")}</h3>
          <p>{t("siteLanguagesBody")}</p>
          <p className="site-langs" aria-label={t("siteLanguagesTitle")}><span lang="en">English</span><span lang="ur">اردو</span><span lang="zh">中文</span><span lang="es">Español</span><span lang="ar">العربية</span><span lang="hi">हिन्दी</span></p>
        </div>
      </section>

      <section className="site-section site-pricing-teaser" aria-labelledby="site-pricing">
        <h2 id="site-pricing">{t("sitePricingTitle")}</h2>
        <p>{pro ? t("sitePricingBody", { price: money(pro.prices[currency].month, currency, language) }) : t("sitePricingBodyNoPrice")}</p>
        <div className="pf-actions"><Link className="lb-button lb-button-primary" to="/pricing">{t("siteSeePlans")}</Link><Link className="lb-button" to="/search">{t("siteStartFree")}</Link></div>
      </section>

      <section className="site-section" aria-labelledby="site-faq">
        <h2 id="site-faq">{t("siteFaqTitle")}</h2>
        <div className="site-faq">
          {FAQ.slice(0, 6).map(([question, answer], index) => (
            <div key={question} className="site-faq-item">
              <button type="button" aria-expanded={open === index} aria-controls={`faq-${index}`} onClick={() => setOpen(open === index ? null : index)}>{t(question)}</button>
              {open === index ? <p id={`faq-${index}`}>{t(answer)}</p> : null}
            </div>
          ))}
        </div>
        <Link to="/help" className="lb-link">{t("siteMoreQuestions")}</Link>
      </section>

      <section className="site-section site-cta" aria-labelledby="site-cta">
        <h2 id="site-cta">{t("siteCtaTitle")}</h2>
        <p>{t("siteCtaBody")}</p>
        <Link className="lb-button lb-button-primary" to="/search">{t("siteStartFree")}</Link>
        <h3>{t("siteNewsletterTitle")}</h3>
        <NewsletterForm t={t} language={language} source="landing" />
      </section>
    </SiteShell>
  );
}

export function FeaturesPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  useSeo(t("siteNavFeatures"), t("siteFeaturesSubtitle"), "/features");
  return (
    <SiteShell language={language}>
      <SiteHead title={t("siteNavFeatures")} subtitle={t("siteFeaturesSubtitle")} />
      <div className="site-feature-list">
        {FEATURES.map((feature) => (
          <article key={feature.key} className="site-feature">
            <span className="site-card-icon"><FeatureIcon name={feature.key} /></span>
            <div><h2>{t(feature.title)}</h2><p>{t(feature.body)}</p><Link to={feature.to} className="lb-link">{t("siteTryIt")}</Link></div>
          </article>
        ))}
      </div>
    </SiteShell>
  );
}

export function AboutPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  useSeo(t("siteNavAbout"), t("siteAboutLead"), "/about");
  return (
    <SiteShell language={language}>
      <SiteHead title={t("siteNavAbout")} subtitle={t("siteAboutLead")} />
      <div className="site-prose">
        <h2>{t("siteAboutMissionTitle")}</h2><p>{t("siteAboutMission")}</p>
        <h2>{t("siteAboutPrinciplesTitle")}</h2>
        <ul><li>{t("siteAboutPrincipleCited")}</li><li>{t("siteAboutPrinciplePrivate")}</li><li>{t("siteAboutPrincipleLanguage")}</li><li>{t("siteAboutPrincipleHonest")}</li></ul>
        <h2>{t("siteAboutDataTitle")}</h2><p>{t("siteAboutData")}</p>
      </div>
    </SiteShell>
  );
}

export function HelpPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  useSeo(t("siteNavHelp"), t("siteHelpSubtitle"), "/help");
  const items = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(language);
    return FAQ.filter(([question, answer]) => !needle || `${t(question)} ${t(answer)}`.toLocaleLowerCase(language).includes(needle));
  }, [language, query, t]);
  return (
    <SiteShell language={language}>
      <SiteHead title={t("siteNavHelp")} subtitle={t("siteHelpSubtitle")} />
      <form className="site-help-search" role="search" onSubmit={(event) => event.preventDefault()}>
        <label className="rs-visually-hidden" htmlFor="help-q">{t("siteHelpSearch")}</label>
        <input id="help-q" className="lb-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("siteHelpSearch")} dir="auto" />
      </form>
      <div className="site-faq" aria-live="polite">
        {items.length ? items.map(([question, answer]) => (
          <div key={question} className="site-faq-item">
            <button type="button" aria-expanded={open === question} onClick={() => setOpen(open === question ? null : question)}>{t(question)}</button>
            {open === question || query.trim() ? <p>{t(answer)}</p> : null}
          </div>
        )) : <p className="pf-empty">{t("siteHelpNoResults")} <Link to="/contact">{t("siteNavContact")}</Link></p>}
      </div>
      <section className="site-panel">
        <h2>{t("siteHelpStillTitle")}</h2>
        <p>{t("siteHelpStillBody")}</p>
        <div className="pf-actions"><Link to="/contact" className="lb-button lb-button-primary">{t("siteNavContact")}</Link><Link to="/status" className="lb-button">{t("siteNavStatus")}</Link></div>
      </section>
    </SiteShell>
  );
}

const TOPICS: Array<[string, SearchCopyKey]> = [["general", "siteTopicGeneral"], ["support", "siteTopicSupport"], ["billing", "siteTopicBilling"], ["sales", "siteTopicSales"], ["privacy", "siteTopicPrivacy"], ["bug", "siteTopicBug"], ["press", "siteTopicPress"]];

export function ContactPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  const [form, setForm] = useState({ name: "", email: "", topic: "general", message: "", website: "" });
  const [state, setState] = useState<"idle" | "busy" | "sent" | "error">("idle");
  const [error, setError] = useState("");
  useSeo(t("siteNavContact"), t("siteContactSubtitle"), "/contact");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState("busy");
    try {
      await siteCall("/contact", { ...form, language });
      setState("sent");
    } catch (caught) {
      setError(siteError(t, caught));
      setState("error");
    }
  }
  return (
    <SiteShell language={language}>
      <SiteHead title={t("siteNavContact")} subtitle={t("siteContactSubtitle")} />
      {state === "sent" ? <p className="site-success" role="status">{t("siteContactSent")}</p> : (
        <form className="site-form" onSubmit={submit}>
          <label className="lb-field"><span>{t("siteName")}</span><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} autoComplete="name" maxLength={120} /></label>
          <label className="lb-field"><span>{t("siteEmail")}</span><input type="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} autoComplete="email" placeholder={t("siteEmailPlaceholder")} /></label>
          <fieldset className="pf-choice"><legend>{t("siteTopic")}</legend>
            {TOPICS.map(([value, key]) => <button key={value} type="button" role="radio" aria-checked={form.topic === value} className={form.topic === value ? "is-active" : ""} onClick={() => setForm({ ...form, topic: value })}>{t(key)}</button>)}
          </fieldset>
          <label className="lb-field"><span>{t("siteMessage")}</span><textarea required minLength={10} rows={6} value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} dir="auto" /></label>
          <label className="site-honeypot" aria-hidden="true">Website<input tabIndex={-1} autoComplete="off" value={form.website} onChange={(event) => setForm({ ...form, website: event.target.value })} /></label>
          <p className="gw-small">{t("siteContactPrivacy")} <Link to="/legal/privacy">{t("siteLegal_privacy")}</Link></p>
          <button type="submit" className="lb-button lb-button-primary" disabled={state === "busy"}>{t("siteSend")}</button>
          {state === "error" ? <p className="site-error" role="alert">{error}</p> : null}
        </form>
      )}
    </SiteShell>
  );
}

export function StatusPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  const [data, setData] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<unknown>(null);
  useSeo(t("siteNavStatus"), t("siteStatusSubtitle"), "/status");
  useEffect(() => {
    let cancelled = false;
    const load = () => siteCall<StatusPayload>("/status").then((value) => { if (!cancelled) { setData(value); setError(null); } }).catch((caught) => { if (!cancelled) setError(caught); });
    load();
    const timer = window.setInterval(load, 60_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);
  return (
    <SiteShell language={language}>
      <SiteHead title={t("siteNavStatus")} subtitle={t("siteStatusSubtitle")} />
      {error && !data ? <p className="pf-empty" role="alert">{t("siteStatusUnreachable")}</p> : !data ? <div className="pf-skel" /> : (
        <>
          <div className={`site-status-banner is-${data.overall}`} role="status">{data.overall === "operational" ? t("siteStatusAllGood") : t(STATUS_KEYS[data.overall] || "siteStatusDegraded")}</div>
          <ul className="site-components">
            {Object.entries(data.components).map(([component, state]) => (
              <li key={component}><span>{t(`siteComponent_${component}` as SearchCopyKey)}</span><span className={`site-dot is-${state}`}>{t(STATUS_KEYS[state] || "siteStatusDegraded")}</span></li>
            ))}
          </ul>
          <p className="gw-small">{t("siteStatusChecked", { time: formatDateTime(data.checked_at, language) })}</p>
          <h2>{t("siteIncidents")}</h2>
          {data.incidents.length ? (
            <ul className="pf-messages">
              {data.incidents.map((incident) => (
                <li key={incident.id} className={incident.status === "resolved" ? "is-closed" : ""}>
                  <div className="pf-message-head"><b><bdi>{incident.title}</bdi></b><span className="gw-small">{t(`siteComponent_${incident.component}` as SearchCopyKey)} · {t(`siteIncident_${incident.status}` as SearchCopyKey)} · {formatDateTime(incident.updated_at, language)}</span></div>
                  {incident.message ? <p dir="auto">{incident.message}</p> : null}
                </li>
              ))}
            </ul>
          ) : <p className="pf-empty">{t("siteNoIncidents")}</p>}
        </>
      )}
    </SiteShell>
  );
}

export function ChangelogPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  useSeo(t("siteNavChangelog"), t("siteChangelogSubtitle"), "/changelog");
  return (
    <SiteShell language={language}>
      <SiteHead title={t("siteNavChangelog")} subtitle={t("siteChangelogSubtitle")} />
      <ol className="site-changelog">
        {CHANGELOG.map((entry) => (
          <li key={entry.title}><time dateTime={entry.date}>{new Intl.DateTimeFormat(language, { dateStyle: "long" }).format(new Date(`${entry.date}T12:00:00Z`))}</time><h2>{t(entry.title)}</h2><p>{t(entry.body)}</p></li>
        ))}
      </ol>
    </SiteShell>
  );
}

export function LegalPage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const t = useSearchCopy(language);
  const { doc: slug } = useParams();
  const doc = legalDoc(slug);
  useSeo(doc ? doc.docTitle : t("pfErrorNotFound"), doc?.summary || "", `/legal/${slug || ""}`);
  return (
    <SiteShell language={language}>
      <nav className="site-legal-nav" aria-label={t("siteFooterLegal")}>
        {LEGAL_DOCS.map((item) => <Link key={item.slug} to={`/legal/${item.slug}`} aria-current={item.slug === slug ? "page" : undefined}>{t(`siteLegal_${item.slug.replace("-", "_")}` as SearchCopyKey)}</Link>)}
      </nav>
      {!doc ? <p className="pf-empty">{t("pfErrorNotFound")}</p> : (
        <>
          {language !== "en" ? <p className="site-panel site-legal-note">{t("siteLegalEnglishNote")}</p> : null}
          <article className="site-prose site-legal" lang="en" dir="ltr">
            <h1>{doc.docTitle}</h1>
            <p className="gw-small"><time dateTime={doc.updated}>{doc.updated}</time> · {LEGAL_REVIEW_NOTE}</p>
            <p><em>{doc.summary}</em></p>
            {doc.sections.map((section) => (
              <section key={section.heading}><h2>{section.heading}</h2>{section.body.map((paragraph) => <p key={paragraph.slice(0, 40)}>{paragraph}</p>)}</section>
            ))}
          </article>
        </>
      )}
    </SiteShell>
  );
}

export function NewsletterConfirmPage({ interfaceLanguage: language, action }: { interfaceLanguage: string; action: "confirm" | "unsubscribe" }) {
  const t = useSearchCopy(language);
  const [params] = useSearchParams();
  const [state, setState] = useState<"busy" | "done" | "error">("busy");
  useEffect(() => {
    const token = params.get("token") || "";
    siteCall(`/newsletter/${action}`, { token }).then(() => setState("done")).catch(() => setState("error"));
  }, [action, params]);
  return (
    <SiteShell language={language}>
      <SiteHead title={action === "confirm" ? t("siteNewsletterConfirmTitle") : t("siteNewsletterUnsubTitle")} />
      {state === "busy" ? <div className="pf-skel" /> : state === "done" ? <p className="site-success" role="status">{action === "confirm" ? t("siteNewsletterConfirmed") : t("siteNewsletterRemoved")}</p> : <p className="site-error" role="alert">{t("siteErrorToken")}</p>}
    </SiteShell>
  );
}

export function InvitePage({ interfaceLanguage: language }: { interfaceLanguage: string }) {
  const { t, toast, toastText } = usePlatform(language);
  const [params] = useSearchParams();
  const [data, setData] = useState<Referral | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [code, setCode] = useState(params.get("code") || "");
  useSeo(t("refTitle"), t("refSubtitle"), "/invite");
  const load = () => siteCall<Referral>("/referral").then(setData).catch(setError);
  useEffect(() => { void load(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const link = data ? `${window.location.origin}/invite?code=${data.code}` : "";
  async function redeem(event: React.FormEvent) {
    event.preventDefault();
    try {
      const result = await siteCall<{ credits: number }>("/referral/redeem", { code });
      toast(t("refRedeemed", { credits: formatNumber(result.credits, language) }));
      void load();
    } catch (caught) {
      toast(siteError(t, caught));
    }
  }
  return (
    <SiteShell language={language}>
      <SiteHead title={t("refTitle")} subtitle={t("refSubtitle")} />
      {error && !data ? <p className="pf-empty" role="alert">{errorText(t, error)}</p> : !data ? <div className="pf-skel" /> : (
        <div className="pf-grid-2">
          <section className="gw-panel" aria-labelledby="ref-share">
            <h2 id="ref-share">{t("refYourLink")}</h2>
            <p className="gw-small">{t("refHow", { credits: formatNumber(data.credits_per_referral, language) })}</p>
            <div className="pf-inline-form">
              <label className="rs-visually-hidden" htmlFor="ref-link">{t("refYourLink")}</label>
              <input id="ref-link" className="lb-input" readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
              <button type="button" className="lb-button lb-button-primary" onClick={() => void navigator.clipboard?.writeText(link).then(() => toast(t("refCopied")), () => undefined)}>{t("refCopy")}</button>
            </div>
            <p className="gw-small">{t("refCode", { code: data.code })}</p>
            <p>{t("refStats", { invited: formatNumber(data.invited, language), credits: formatNumber(data.credits_earned, language) })}</p>
          </section>
          <section className="gw-panel" aria-labelledby="ref-redeem">
            <h2 id="ref-redeem">{t("refHaveCode")}</h2>
            {data.redeemed_code ? <p className="site-success">{t("refAlreadyRedeemed", { code: data.redeemed_code })}</p> : (
              <form className="pf-inline-form" onSubmit={redeem}>
                <label className="rs-visually-hidden" htmlFor="ref-code">{t("refEnterCode")}</label>
                <input id="ref-code" className="lb-input" value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} placeholder={t("refEnterCode")} minLength={4} maxLength={20} required />
                <button type="submit" className="lb-button">{t("refRedeem")}</button>
              </form>
            )}
          </section>
        </div>
      )}
      <div className="lb-toast-region" aria-live="polite">{toastText ? <div className="lb-toast" role="status">{toastText}</div> : null}</div>
    </SiteShell>
  );
}
