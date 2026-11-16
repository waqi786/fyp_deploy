/**
 * Public-site runtime: per-page SEO tags (title, description, Open Graph, canonical, hreflang), cookieless page
 * views (no cookies, no ids; Do Not Track / Global Privacy Control respected) and the cookie notice.
 */
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { libraryApiBase } from "../library/libraryApi";
import { useSearchCopy } from "../search/copy";

const SITE_URL = (import.meta.env.VITE_PUBLIC_SITE_URL as string | undefined)?.replace(/\/$/, "") || (typeof window !== "undefined" ? window.location.origin : "");
const SEO_LANGUAGES = ["en", "ur"];

function setMeta(selector: string, attribute: "name" | "property", key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(selector);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, key);
    document.head.appendChild(element);
  }
  element.setAttribute("content", content);
}

function setLink(rel: string, href: string, hreflang?: string) {
  const selector = hreflang ? `link[rel="${rel}"][hreflang="${hreflang}"]` : `link[rel="${rel}"]:not([hreflang])`;
  let element = document.head.querySelector<HTMLLinkElement>(selector);
  if (!element) {
    element = document.createElement("link");
    element.rel = rel;
    if (hreflang) element.hreflang = hreflang;
    document.head.appendChild(element);
  }
  element.href = href;
}

/** Title, description, Open Graph / Twitter tags, canonical URL and hreflang alternates for a public page. */
export function useSeo(title: string, description: string, path: string) {
  useEffect(() => {
    const fullTitle = title.includes("Resora") ? title : `${title} · Resora`;
    document.title = fullTitle;
    setMeta('meta[name="description"]', "name", "description", description);
    setMeta('meta[property="og:title"]', "property", "og:title", fullTitle);
    setMeta('meta[property="og:description"]', "property", "og:description", description);
    setMeta('meta[property="og:type"]', "property", "og:type", "website");
    setMeta('meta[property="og:url"]', "property", "og:url", `${SITE_URL}${path}`);
    setMeta('meta[property="og:image"]', "property", "og:image", `${SITE_URL}/brand-dark.png`);
    setMeta('meta[name="twitter:card"]', "name", "twitter:card", "summary_large_image");
    setLink("canonical", `${SITE_URL}${path}`);
    for (const language of SEO_LANGUAGES) setLink("alternate", `${SITE_URL}${path}?lang=${language}`, language);
    setLink("alternate", `${SITE_URL}${path}`, "x-default");
  }, [description, path, title]);
}

/** One anonymous page view per route change (skipped with Do Not Track / Global Privacy Control). */
export function PageviewTracker({ language }: { language: string }) {
  const location = useLocation();
  useEffect(() => {
    const nav = navigator as Navigator & { globalPrivacyControl?: boolean; doNotTrack?: string };
    if (nav.doNotTrack === "1" || nav.globalPrivacyControl) return;
    const timer = window.setTimeout(() => {
      const body = JSON.stringify({ path: location.pathname, referrer: document.referrer && !document.referrer.startsWith(window.location.origin) ? document.referrer : "", language });
      try {
        void fetch(`${libraryApiBase}/site/pageview`, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => undefined);
      } catch {
        /* analytics must never break the page */
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [language, location.pathname]);
  return null;
}

const NOTICE_KEY = "resora-cookie-notice";

/** Resora sets no tracking cookies, so the notice informs and links to the policy; it is shown once. */
export function CookieNotice({ language }: { language: string }) {
  const t = useSearchCopy(language);
  const [open, setOpen] = useState(() => {
    try {
      return !window.localStorage.getItem(NOTICE_KEY);
    } catch {
      return false;
    }
  });
  useEffect(() => {
    const reopen = () => setOpen(true);
    window.addEventListener("resora:cookie-notice", reopen);
    return () => window.removeEventListener("resora:cookie-notice", reopen);
  }, []);
  if (!open) return null;
  const dismiss = () => {
    try {
      window.localStorage.setItem(NOTICE_KEY, new Date().toISOString());
    } catch {
      /* ignore */
    }
    setOpen(false);
  };
  return (
    <div className="site-cookie" role="dialog" aria-label={t("siteCookieTitle")} lang={language} dir={language === "ur" ? "rtl" : "ltr"} data-no-translate="">
      <p><b>{t("siteCookieTitle")}</b> {t("siteCookieBody")} <Link to="/legal/cookies">{t("siteCookieLink")}</Link></p>
      <button type="button" onClick={dismiss}>{t("siteCookieOk")}</button>
    </div>
  );
}
