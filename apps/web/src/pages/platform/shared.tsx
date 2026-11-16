/** Building blocks shared by Plans & usage, Teams and Insights (same look as Library / Gaps). */
import { useCallback, useRef, useState, type ReactNode } from "react";
import { useSearchCopy, type SearchCopyKey, type SearchT } from "../search/copy";
import { LibraryError } from "../library/libraryApi";
import { directionOf, formatNumber } from "../library/ui";
import type { Window } from "./platformApi";
import "../SearchPage.css";
import "../LibraryPage.css";
import "../GapsWritePage.css";
import "./PlatformPages.css";

const ERRORS: Record<string, SearchCopyKey> = {
  network: "libErrorNetwork",
  sign_in_required: "libErrorSignIn",
  limit_reached: "gapErrorCredits",
  forbidden: "pfErrorForbidden",
  not_found: "pfErrorNotFound",
  invite_invalid: "teamInviteInvalid",
  invite_expired: "teamInviteExpired",
  invite_used: "teamInviteUsed",
  owner_cannot_leave: "teamOwnerCannotLeave",
  team_required: "billTeamRequired",
  already_on_plan: "billAlreadyOnPlan",
  plan_not_purchasable: "billContactSales",
  busy: "insBusy",
  catalog_unavailable: "insUnavailable",
  sandbox_disabled: "billSandboxDisabled",
  session_expired: "billSessionExpired",
  session_completed: "billSessionDone",
  session_canceled: "billSessionCanceled",
  reviewer_not_supervisor: "teamReviewerNotSupervisor",
  member_limit: "teamMemberLimit",
  team_limit: "teamTeamLimit",
};

export function errorText(t: SearchT, caught: unknown) {
  const code = caught instanceof LibraryError ? caught.code : "";
  return t(ERRORS[code] || "libErrorGeneric");
}

export function usePlatform(language: string) {
  const t = useSearchCopy(language);
  const [toastText, setToastText] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const toast = useCallback((message: string) => {
    setToastText(message);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToastText(""), 3600);
  }, []);
  return { t, toast, toastText };
}

export function PageShell({ language, title, subtitle, actions, toastText, children, className = "" }: { language: string; title: string; subtitle?: ReactNode; actions?: ReactNode; toastText: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rs-search lb-library gw-page pf-page ${className}`} dir={directionOf(language)} lang={language} data-no-translate="">
      <div className="lb-shell">
        <header className="lb-head">
          <div className="lb-head-text">
            <h1>{title}</h1>
            {subtitle ? <p className="lb-head-sub">{subtitle}</p> : null}
          </div>
          {actions ? <div className="lb-head-actions">{actions}</div> : null}
        </header>
        <main className="lb-main">{children}</main>
      </div>
      <div className="lb-toast-region" aria-live="polite">{toastText ? <div className="lb-toast" role="status">{toastText}</div> : null}</div>
    </section>
  );
}

export function formatDateTime(iso: string | null | undefined, language: string) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat(language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
  } catch {
    return iso.slice(0, 16).replace("T", " ");
  }
}

export function formatDate(iso: string | null | undefined, language: string) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(new Date(iso));
  } catch {
    return iso.slice(0, 10);
  }
}

const WINDOW_KEYS: Record<Window["scope"], SearchCopyKey> = { session: "billWindowSession", week: "billWindowWeek", month: "billWindowMonth" };

/** One credit window: used / limit, a bar coloured by how close it is, and when it resets. */
export function Meter({ t, language, window }: { t: SearchT; language: string; window: Window }) {
  const percent = Math.round(window.percent * 100);
  const level = percent >= 90 ? "is-high" : percent >= 70 ? "is-mid" : "";
  return (
    <div className={`pf-meter ${level}`}>
      <div className="pf-meter-head">
        <b>{t(WINDOW_KEYS[window.scope])}</b>
        <span>{t("billUsedOf", { used: formatNumber(window.used, language), limit: formatNumber(window.limit, language) })}</span>
      </div>
      <div className="pf-meter-track" role="progressbar" aria-label={t(WINDOW_KEYS[window.scope])} aria-valuemin={0} aria-valuemax={window.limit} aria-valuenow={window.used}>
        <span style={{ inlineSize: `${Math.min(100, percent)}%` }} />
      </div>
      <p className="gw-small">{t("billResetsAt", { time: formatDateTime(window.resets_at, language) })}</p>
    </div>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="pf-stat">
      <span className="pf-stat-label">{label}</span>
      <span className="pf-stat-value">{value}</span>
      {note ? <span className="gw-small">{note}</span> : null}
    </div>
  );
}
