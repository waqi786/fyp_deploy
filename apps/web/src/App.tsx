import { lazy, Suspense, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { PopoverProvider } from "./components/ui";
import { AutoTranslator } from "./i18n/StaticCatalogTranslator";
import { getResearchLanguage, researchLanguages } from "./i18n/languages";
import { hasSearchCatalog } from "./pages/search/copy";

const HomePage = lazy(() => import("./pages/HomePage").then((module) => ({ default: module.HomePage })));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })));
const SearchPage = lazy(() => import("./pages/SearchPage").then((module) => ({ default: module.SearchPage })));
const EntityProfilePage = lazy(() => import("./pages/EntityProfilePage").then((module) => ({ default: module.EntityProfilePage })));
const ReaderPage = lazy(() => import("./pages/ReaderPage").then((module) => ({ default: module.ReaderPage })));
const MultimodalPage = lazy(() => import("./pages/MultimodalPage").then((module) => ({ default: module.MultimodalPage })));
const ComparisonPage = lazy(() => import("./pages/ComparisonPage").then((module) => ({ default: module.ComparisonPage })));
const GapsPage = lazy(() => import("./pages/GapsPage").then((module) => ({ default: module.GapsPage })));
const WritePage = lazy(() => import("./pages/WritePage").then((module) => ({ default: module.WritePage })));
const ChatPage = lazy(() => import("./pages/ChatPage").then((module) => ({ default: module.ChatPage })));
const LibraryPage = lazy(() => import("./pages/LibraryPage").then((module) => ({ default: module.LibraryPage })));
const WritingLibraryPage = lazy(() => import("./pages/WritingLibraryPage").then((module) => ({ default: module.WritingLibraryPage })));
const CollaborationPage = lazy(() => import("./pages/CollaborationPage").then((module) => ({ default: module.CollaborationPage })));
const PersonalizationPage = lazy(() => import("./pages/PersonalizationPage").then((module) => ({ default: module.PersonalizationPage })));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })));
const SecurityMobilePage = lazy(() => import("./pages/SecurityMobilePage").then((module) => ({ default: module.SecurityMobilePage })));
const DeveloperAIPage = lazy(() => import("./pages/DeveloperAIPage").then((module) => ({ default: module.DeveloperAIPage })));
const FeatureAssurancePage = lazy(() => import("./pages/FeatureAssurancePage").then((module) => ({ default: module.FeatureAssurancePage })));
const ControlPage = lazy(() => import("./pages/ControlPage").then((module) => ({ default: module.ControlPage })));
const OpenSourceNoticesPage = lazy(() => import("./pages/OpenSourceNoticesPage").then((module) => ({ default: module.OpenSourceNoticesPage })));
const DevUiPage = lazy(() => import("./pages/DevUiPage").then((module) => ({ default: module.DevUiPage })));

type ThemeMode = "dark" | "light";
type DirectionMode = "ltr" | "rtl";
type LanguageCode = (typeof researchLanguages)[number]["code"];
type DensityMode = "compact" | "comfortable";
// One language for the whole app, and only languages whose interface is translated (no half-English screens).
const languageCodes: LanguageCode[] = researchLanguages.map((language) => language.code).filter((code) => hasSearchCatalog(code));
const densityModes: DensityMode[] = ["compact", "comfortable"];
const themeModes: ThemeMode[] = ["dark", "light"];

function resolveInitialTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "dark";
  }

  const savedTheme = window.localStorage.getItem("resora-theme");
  if (themeModes.includes(savedTheme as ThemeMode)) {
    return savedTheme as ThemeMode;
  }

  return "dark";
}

function resolveInitialLanguage(): LanguageCode {
  if (typeof window === "undefined") {
    return "en";
  }

  let savedLanguage: string | null = null;
  try {
    savedLanguage = window.localStorage.getItem("resora-language");
  } catch {
    savedLanguage = null;
  }
  // Both a pinned language ("settings") and the last auto-detected one are restored, so a reload never flips
  // an Urdu or Chinese user back to English.
  if (languageCodes.includes(savedLanguage as LanguageCode)) {
    return savedLanguage as LanguageCode;
  }

  // First visit: use the browser language when Resora supports it (exact match first, then the same base language).
  for (const preferred of window.navigator.languages || [window.navigator.language]) {
    const exact = languageCodes.find((code) => code.toLowerCase() === preferred.toLowerCase());
    if (exact) return exact;
    if (/^zh-(tw|hk|mo|hant)/i.test(preferred) && languageCodes.includes("zh-Hant" as LanguageCode)) return "zh-Hant" as LanguageCode;
    if (/^pt-pt/i.test(preferred) && languageCodes.includes("pt-PT" as LanguageCode)) return "pt-PT" as LanguageCode;
    const base = preferred.split("-")[0].toLowerCase();
    const sameBase = languageCodes.find((code) => code.split("-")[0].toLowerCase() === base);
    if (sameBase) return sameBase;
  }
  return "en";
}

function directionForLanguage(language: LanguageCode): DirectionMode {
  return getResearchLanguage(language)?.direction || "ltr";
}

function resolveInitialDensity(): DensityMode {
  if (typeof window === "undefined") {
    return "compact";
  }

  const savedDensity = window.localStorage.getItem("resora-density");
  if (densityModes.includes(savedDensity as DensityMode)) {
    return savedDensity as DensityMode;
  }

  return "compact";
}

/** Old /summaries links (Home, bookmarks) open the Reader with the same query. */
function LegacyReaderRedirect() {
  const location = useLocation();
  return <Navigate to={`/reader${location.search}`} replace />;
}

function ScrollToTop() {
  const location = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [location.pathname, location.search]);

  return null;
}

export function App() {
  const [theme, setTheme] = useState<ThemeMode>(resolveInitialTheme);
  const [language, setLanguage] = useState<LanguageCode>(resolveInitialLanguage);
  const [density, setDensity] = useState<DensityMode>(resolveInitialDensity);
  const direction = directionForLanguage(language);

  function handleLanguageChange(nextLanguage: LanguageCode, source: "settings" | "auto" = "settings") {
    if (!languageCodes.includes(nextLanguage)) return;
    try {
      window.localStorage.setItem("resora-language-source", source);
    } catch {
      /* storage unavailable — the choice still applies for this session */
    }
    setLanguage(nextLanguage);
  }

  useEffect(() => {
    document.body.dataset.theme = theme;
    document.body.dataset.language = language;
    document.body.dataset.density = density;
    document.documentElement.dir = direction;
    document.documentElement.lang = language;
    window.localStorage.setItem("resora-language", language);
    window.localStorage.setItem("resora-density", density);
    window.localStorage.setItem("resora-theme", theme);
  }, [theme, language, density, direction]);

  return (
    <BrowserRouter>
      <ScrollToTop />
      <AutoTranslator language={language}>
        <PopoverProvider>
        <AppShell
          theme={theme}
          onThemeChange={setTheme}
          language={language}
          onLanguageChange={handleLanguageChange}
          density={density}
          onDensityChange={setDensity}
          direction={direction}
        >
          <Suspense fallback={<div className="flex min-h-[50vh] items-center justify-center text-sm text-muted" role="status">Loading Resora</div>}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/dashboard" element={<Navigate to="/control" replace />} />
            <Route path="/workspace" element={<Navigate to="/control" replace />} />
            <Route path="/search" element={<SearchPage interfaceLanguage={language} onLanguageChange={handleLanguageChange} />} />
            <Route path="/reader" element={<ReaderPage interfaceLanguage={language} />} />
            <Route path="/reader/:docId" element={<ReaderPage interfaceLanguage={language} />} />
            <Route path="/summaries" element={<LegacyReaderRedirect />} />
            <Route path="/researchers/:id" element={<EntityProfilePage kind="researcher" interfaceLanguage={language} />} />
            <Route path="/institutions/:id" element={<EntityProfilePage kind="institution" interfaceLanguage={language} />} />
            <Route path="/multimodal" element={<MultimodalPage />} />
            <Route path="/comparison" element={<ComparisonPage interfaceLanguage={language} />} />
            <Route path="/gaps/*" element={<GapsPage interfaceLanguage={language} />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/writing/*" element={<WritePage interfaceLanguage={language} />} />
            <Route path="/library/*" element={<LibraryPage interfaceLanguage={language} />} />
            <Route path="/collaboration" element={<CollaborationPage />} />
            <Route path="/personalization" element={<PersonalizationPage interfaceLanguage={language} />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/security-mobile" element={<SecurityMobilePage />} />
            <Route path="/developer-ai" element={<DeveloperAIPage />} />
            <Route path="/assurance" element={<FeatureAssurancePage />} />
            <Route path="/control" element={<ControlPage />} />
            <Route path="/open-source" element={<OpenSourceNoticesPage />} />
            {import.meta.env.DEV ? <Route path="/dev/ui" element={<DevUiPage />} /> : null}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
          </Suspense>
        </AppShell>
        </PopoverProvider>
      </AutoTranslator>
    </BrowserRouter>
  );
}
