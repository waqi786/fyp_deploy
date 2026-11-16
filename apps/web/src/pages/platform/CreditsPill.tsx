/** Top-bar credits pill: remaining credits in the current 5-hour window, linking to Plans & usage. */
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useSearchCopy } from "../search/copy";
import { billingApi, type Window } from "./platformApi";

export function CreditsPill({ language = "en" }: { language?: string }) {
  const t = useSearchCopy(language);
  const location = useLocation();
  const [session, setSession] = useState<Window | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => billingApi.me().then((me) => { if (alive) setSession(me.usage.windows.find((window) => window.scope === "session") || null); }).catch(() => { if (alive) setSession(null); });
    void load();
    const timer = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [location.pathname]);

  if (!session) return null;
  const low = session.limit > 0 && session.remaining / session.limit < 0.15;
  return (
    <NavLink to="/usage" className={`resora-credits-pill${low ? " is-low" : ""}`} title={t("billCreditsLeftTitle", { remaining: session.remaining, limit: session.limit })} aria-label={t("billCreditsLeftTitle", { remaining: session.remaining, limit: session.limit })} data-no-translate="" lang={language}>
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" /></svg>
      <span>{new Intl.NumberFormat(language).format(session.remaining)}</span>
    </NavLink>
  );
}
