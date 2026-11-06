import { ReactNode, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { researchLanguages } from "../i18n/languages";
import "./SearchPage.css";
import { useSearchCopy, type SearchT } from "./search/copy";
import {
  fetchProfile,
  ProfileNotFound,
  type InstitutionProfile,
  type PersonLink,
  type ResearcherProfile,
  type WorkItem,
  type YearCount,
} from "./search/researchApi";

type Kind = "researcher" | "institution";
type Status = "loading" | "ready" | "notfound" | "error";

function formatNumber(value: number, locale: string) {
  try {
    return new Intl.NumberFormat(locale).format(value);
  } catch {
    return String(value);
  }
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

function displayYear(year?: number | null) {
  return year && year <= new Date().getFullYear() ? year : null;
}

/** Researcher and institution profile: who they are, what they publish, how it changed, who they work with. */
export function EntityProfilePage({ kind, interfaceLanguage = "en" }: { kind: Kind; interfaceLanguage?: string }) {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const t = useSearchCopy(interfaceLanguage);
  const language = interfaceLanguage;
  const direction = researchLanguages.find((item) => item.code === language)?.direction === "rtl" ? "rtl" : "ltr";
  const [status, setStatus] = useState<Status>("loading");
  const [profile, setProfile] = useState<ResearcherProfile | InstitutionProfile | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    setProfile(null);
    fetchProfile<ResearcherProfile | InstitutionProfile>(kind === "researcher" ? "researchers" : "institutions", id, language, controller.signal)
      .then((data) => {
        setProfile(data);
        setStatus("ready");
        document.title = `${data.name} · Resora`;
      })
      .catch((error: unknown) => {
        if ((error as Error)?.name === "AbortError") return;
        setStatus(error instanceof ProfileNotFound ? "notfound" : "error");
      });
    return () => controller.abort();
  }, [attempt, id, kind, language]);

  const goBack = () => (window.history.length > 1 ? navigate(-1) : navigate("/search"));
  const researcher = kind === "researcher" ? (profile as ResearcherProfile | null) : null;
  const institution = kind === "institution" ? (profile as InstitutionProfile | null) : null;

  return (
    <section className="rs-search rs-profile" dir={direction} lang={language} data-no-translate="">
      <div className="rs-col rs-profile-col">
        <button type="button" className="rs-text-button rs-profile-back" onClick={goBack}>
          <BackGlyph />{t("backToSearch")}
        </button>

        {status === "loading" ? <ProfileSkeleton label={t("searching")} /> : null}

        {status === "notfound" || status === "error" ? (
          <div className="rs-state" role="status">
            <h2>{status === "notfound" ? t("profileNotFound") : t("profileUnavailable")}</h2>
            <div className="rs-state-actions">
              {status === "error" ? (
                <button type="button" className="rs-button rs-button-primary" onClick={() => setAttempt((value) => value + 1)}>{t("retry")}</button>
              ) : (
                <Link className="rs-button rs-button-outline" to="/search">{t("searchTab")}</Link>
              )}
            </div>
          </div>
        ) : null}

        {status === "ready" && profile ? (
          <>
            <header className="rs-profile-head">
              <span className={`rs-profile-avatar${kind === "institution" ? " is-institution" : ""}`} aria-hidden="true">
                {kind === "institution" ? <BuildingGlyph /> : initials(profile.name)}
              </span>
              <div className="rs-profile-title">
                <p className="rs-profile-kind">{kind === "researcher" ? t("profileResearcher") : t("profileInstitution")}</p>
                <h1><bdi>{profile.name}</bdi></h1>
                <p className="rs-profile-sub">
                  <bdi>
                    {researcher
                      ? researcher.affiliations.join(" · ")
                      : [institution?.country, institution?.type ? capitalize(institution.type) : ""].filter(Boolean).join(" · ")}
                  </bdi>
                </p>
                <div className="rs-profile-links">
                  <Link className="rs-button rs-button-outline rs-button-small" to={`/search?q=${encodeURIComponent(profile.name)}`}>
                    {t("findInSearch")}
                  </Link>
                  {researcher?.orcid ? (
                    <a className="rs-text-button rs-text-button-small" href={`https://orcid.org/${researcher.orcid}`} target="_blank" rel="noopener noreferrer">
                      ORCID <ExternalGlyph />
                    </a>
                  ) : null}
                  {institution?.homepage ? (
                    <a className="rs-text-button rs-text-button-small" href={institution.homepage} target="_blank" rel="noopener noreferrer">
                      {t("website")} <ExternalGlyph />
                    </a>
                  ) : null}
                </div>
              </div>
            </header>

            <dl className="rs-profile-stats">
              <Stat label={t("statPublications")} value={formatNumber(profile.works_count, language)} />
              <Stat label={t("statCitations")} value={formatNumber(profile.cited_by_count, language)} />
              {researcher?.h_index ? <Stat label={t("statHIndex")} value={formatNumber(researcher.h_index, language)} /> : null}
            </dl>

            {profile.topics.length ? (
              <ProfileSection title={kind === "researcher" ? t("profileTopics") : t("profileAreas")}>
                <div className="rs-chip-row">
                  {profile.topics.map((topic) => (
                    <span key={topic.name} className="rs-tag" title={topic.translated_name ? topic.name : undefined}>
                      <bdi>{topic.translated_name || topic.name}</bdi>
                    </span>
                  ))}
                </div>
              </ProfileSection>
            ) : null}

            {profile.timeline.length >= 2 ? (
              <ProfileSection title={t("profileTimeline")}>
                <Timeline rows={profile.timeline} language={language} t={t} />
              </ProfileSection>
            ) : null}

            {profile.top_works.length ? (
              <ProfileSection title={t("profileMostCited")}>
                <WorkList works={profile.top_works} language={language} t={t} />
              </ProfileSection>
            ) : null}

            {researcher?.recent_works.length ? (
              <ProfileSection title={t("profileRecent")}>
                <WorkList works={researcher.recent_works} language={language} t={t} />
              </ProfileSection>
            ) : null}

            {researcher?.collaborators.length ? (
              <ProfileSection title={t("profileCollaborators")}>
                <PeopleList people={researcher.collaborators} detail={(person) => t("sharedPapers", { count: formatNumber(person.count, language) })} />
              </ProfileSection>
            ) : null}

            {institution?.top_researchers.length ? (
              <ProfileSection title={t("profileTopResearchers")}>
                <PeopleList people={institution.top_researchers} detail={(person) => `${formatNumber(person.count, language)} ${t("citations")}`} />
              </ProfileSection>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

export default EntityProfilePage;

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rs-profile-stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function ProfileSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rs-profile-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Timeline({ rows, language, t }: { rows: YearCount[]; language: string; t: SearchT }) {
  const max = Math.max(1, ...rows.map((row) => row.works));
  return (
    <figure className="rs-timeline">
      <div className="rs-timeline-bars" aria-hidden="true">
        {rows.map((row) => (
          <div key={row.year} className="rs-timeline-col" title={`${row.year}: ${formatNumber(row.works, language)}`}>
            <span className="rs-timeline-value">{row.works ? formatNumber(row.works, language) : ""}</span>
            <span className="rs-timeline-bar" style={{ height: `${Math.max(4, (row.works / max) * 100)}%` }} />
            <span className="rs-timeline-year">{String(row.year).slice(2)}</span>
          </div>
        ))}
      </div>
      <table className="rs-visually-hidden">
        <caption>{t("profileTimelineTable")}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.year}>
              <th scope="row">{row.year}</th>
              <td>{row.works}</td>
              <td>{row.citations}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function WorkList({ works, language, t }: { works: WorkItem[]; language: string; t: SearchT }) {
  return (
    <ul className="rs-work-list">
      {works.map((work) => {
        const title = work.translated_title || work.title;
        const meta = [work.venue, displayYear(work.year)].filter(Boolean).join(" · ");
        return (
          <li key={`${work.title}-${work.year}`} className="rs-work">
            <div className="rs-work-main">
              <p className="rs-work-title" dir="auto" title={work.translated_title ? work.title : undefined}>{title}</p>
              {meta ? <p className="rs-card-meta"><bdi>{meta}</bdi></p> : null}
            </div>
            <div className="rs-work-side">
              {work.citation_count ? (
                <span className="rs-card-citations"><strong>{formatNumber(work.citation_count, language)}</strong> {t("citations")}</span>
              ) : null}
              {work.url ? (
                <a className="rs-button rs-button-outline rs-button-small" href={work.url} target="_blank" rel="noopener noreferrer">
                  {work.is_open_access ? t("readPaper") : t("openLink")}
                </a>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function PeopleList({ people, detail }: { people: PersonLink[]; detail: (person: PersonLink) => string }) {
  return (
    <div className="rs-people">
      {people.map((person) =>
        person.id ? (
          <Link key={person.id} className="rs-entity" to={`/researchers/${encodeURIComponent(person.id)}`}>
            <span className="rs-entity-avatar" aria-hidden="true">{initials(person.name)}</span>
            <span className="rs-entity-text">
              <bdi className="rs-entity-name">{person.name}</bdi>
              <span className="rs-entity-sub">{detail(person)}</span>
            </span>
          </Link>
        ) : null,
      )}
    </div>
  );
}

function ProfileSkeleton({ label }: { label: string }) {
  return (
    <div className="rs-profile-skeleton" role="status" aria-label={label}>
      <div className="rs-skeleton-row" style={{ justifyContent: "flex-start" }}>
        <i className="rs-sk" style={{ width: 72, height: 72, borderRadius: "50%" }} />
        <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
          <i className="rs-sk rs-sk-meta" />
          <i className="rs-sk rs-sk-title" />
        </span>
      </div>
      <div className="rs-skeleton-row">
        <i className="rs-sk" style={{ flex: 1, height: 72 }} />
        <i className="rs-sk" style={{ flex: 1, height: 72 }} />
        <i className="rs-sk" style={{ flex: 1, height: 72 }} />
      </div>
      <i className="rs-sk rs-sk-line" />
      <i className="rs-sk rs-sk-line rs-sk-short" />
    </div>
  );
}

function Icon({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}
function BackGlyph() { return <span className="rs-flip-rtl"><Icon><path d="M15 6l-6 6 6 6" /></Icon></span>; }
function ExternalGlyph() { return <Icon size={13}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Icon>; }
function BuildingGlyph() { return <Icon size={28}><path d="M4 21V5l8-3 8 3v16" /><path d="M9 21v-4h6v4M8 8h.01M12 8h.01M16 8h.01M8 12h.01M12 12h.01M16 12h.01" /></Icon>; }