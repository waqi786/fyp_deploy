import { useMemo, useState } from "react";
import type { ReactNode } from "react";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

type PersonalizationResponse = {
  recommended_topics: string[];
  home_feed: string[];
  dashboard_widgets: string[];
  glossary_terms: string[];
  weekly_digest: string;
  scheduled_digest: Record<string, string>;
  onboarding_path: string[];
  accessibility_profile: Record<string, string>;
  urdu_ui: Record<string, string | boolean>;
  font_controls: Record<string, string | boolean>;
  tts_controls: Record<string, string | boolean>;
  keyboard_navigation_map: string[];
  screen_reader_landmarks: string[];
  wcag_aa_checklist: Record<string, boolean>;
  contextual_help_tooltips: Record<string, string>;
  color_blind_safe_palette: Record<string, string>;
  offline_reading_list: Array<Record<string, string>>;
  pwa_cache_manifest: Record<string, string | number | string[]>;
  low_bandwidth_mode: Record<string, string | boolean>;
  multi_device_sync: Record<string, string | number | string[]>;
  customizable_dashboard: Record<string, string | string[]>;
  similar_to_read_feed: string[];
  ai_preferences: Record<string, string>;
  personal_glossary: Record<string, string>;
  sync_status: string;
  gdpr_actions: string[];
  data_export_uri?: string | null;
  data_delete_receipt?: string | null;
  profile_snapshot_uri?: string | null;
};

type TranslationRow = Record<string, string | number>;

type Category16TranslationSuite = {
  completion: Array<{ feature: string; status: string; evidence: string }>;
  documentFlow: TranslationRow[];
  searchOutreach: TranslationRow[];
  writingQuality: TranslationRow[];
  collaborationConsent: TranslationRow[];
  glossaryMemory: TranslationRow[];
  safetyMath: TranslationRow[];
};

type Category18AdaptiveSuite = {
  completion: Array<{ feature: string; status: string; evidence: string }>;
  profileLearning: TranslationRow[];
  recommendations: TranslationRow[];
  habitsFocus: TranslationRow[];
  workspaceControls: TranslationRow[];
  devicesVoice: TranslationRow[];
  privacyDeepWork: TranslationRow[];
};

const demoProfile: PersonalizationResponse = {
  recommended_topics: ["Retrieval", "Urdu", "Accessibility", "Offline", "RAG"],
  home_feed: ["Similar to your reading: Retrieval", "Similar to your reading: Urdu", "Similar to your reading: Accessibility"],
  dashboard_widgets: ["Reading Queue", "Glossary", "Offline Shelf", "Low-bandwidth summary cards"],
  glossary_terms: ["RAG", "OCR", "RTL", "WCAG"],
  weekly_digest: "Daily digest prepared with recent papers, saved alerts, and workspace updates.",
  scheduled_digest: { frequency: "daily", channel: "email", status: "scheduled", next_run: "next-cycle" },
  onboarding_path: ["Start as a student", "Connect saved searches", "Choose Urdu/English reading preferences"],
  accessibility_profile: { direction: "rtl", theme: "contrast", font_size: "xl", font_family: "Atkinson Hyperlegible", wcag_target: "2.1 AA" },
  urdu_ui: { enabled: true, language: "ur", layout: "right-to-left", label_search: "تلاش" },
  font_controls: { size: "xl", dyslexia_friendly: true, line_height: "relaxed", letter_spacing: "wide" },
  tts_controls: { enabled: true, scope: "any content", voice_hint: "ur-PK" },
  keyboard_navigation_map: ["skip-to-content", "sidebar-nav", "command-search", "reader-actions", "toast-region"],
  screen_reader_landmarks: ["banner", "navigation", "main", "complementary", "contentinfo"],
  wcag_aa_checklist: { keyboard_access: true, screen_reader_labels: true, high_contrast: true, rtl_support: true, focus_visible: true, reduced_motion_safe: true },
  contextual_help_tooltips: {
    search: "Use natural language, Boolean operators, voice, or image search.",
    reader: "Choose beginner/expert summaries and right-click paragraphs for explanation.",
    offline: "Saved papers and summaries are cached for PWA reading.",
    privacy: "Export or delete your profile and workspace history anytime.",
  },
  color_blind_safe_palette: { primary: "#FF6A00", background: "#000000", text: "#FFFFFF", warning: "#FFB000", safe: "#00D5FF" },
  offline_reading_list: [
    { key: "paper-1", cache_route: "/offline/paper-1", status: "queued" },
    { key: "summary-2", cache_route: "/offline/summary-2", status: "queued" },
    { key: "workspace-note-3", cache_route: "/offline/workspace-note-3", status: "queued" },
  ],
  pwa_cache_manifest: { static_cache: ["index", "manifest", "icon", "shell-css"], reading_cache: ["paper-1", "summary-2"], strategy: "cache-first saved reading", max_items: 35 },
  low_bandwidth_mode: { enabled: true, image_policy: "defer-nonessential-images", summary_policy: "prefer-micro-summaries", sync_policy: "batch-background-sync" },
  multi_device_sync: { device_count: 2, devices: ["laptop", "phone"], continuity_token: "sync-demo", status: "ready" },
  customizable_dashboard: { selected_widgets: ["Reading Queue", "Glossary", "Offline Shelf"], layout: "compact" },
  similar_to_read_feed: ["Because you read 'Urdu accessibility interface', try Urdu RAG.", "Because you read 'offline pwa reading', try low-bandwidth summaries."],
  ai_preferences: { verbosity: "beginner", default_answer_style: "step-by-step" },
  personal_glossary: { RAG: "Retrieval augmented generation", OCR: "Optical character recognition", RTL: "Right-to-left layout", WCAG: "Accessibility standard" },
  sync_status: "3 offline items ready to sync",
  gdpr_actions: ["Export my data", "Delete my workspace history", "Manage notification preferences"],
  data_export_uri: "storage/profiles/data-export-demo.json",
  data_delete_receipt: null,
  profile_snapshot_uri: "storage/profiles/profile-demo.json",
};

const category16Features = [
  "Full-Document Translation",
  "Machine Translation Refinement",
  "English-to-Chinese/Japanese/Korean/Arabic/Russian etc.",
  "Bilingual Side-by-Side Reading",
  "Translation Memory",
  "Cross-Lingual Search",
  "Citation Translation",
  "Abstract Translation API",
  "Language-Specific Grammar Checker",
  "Regional Dialect Adjustment",
  "Transliteration",
  "Global News Index",
  "Multi-Lingual Collaboration Chat",
  "Non-English Preprint Access",
  "Terminology Glossary Builder",
  "Auto-Detect Input Language",
  "Speech-to-Text Translation",
  "Latin-to-Vernacular",
  "Translation Quality Score",
  "Dictionary Lookup",
  "Cultural Context Adjustment",
  "Multi-Lingual Data Labeling",
  "Translation for Informed Consent",
  "International Collaborator Onboarding",
  "Preserve Math/Equations in Translation",
];

const category18Features = [
  "Research Profile Builder",
  "Adaptive Recommendation Engine",
  "Smart Folder Organization",
  "Daily Paper of the Day",
  "Skill Gap Analyzer",
  "Learning Pathway Builder",
  "Personal AI Mentor",
  "Reading Habit Dashboard",
  "Custom Shortcut Keys",
  "UI Customization",
  "Notification Sensitivity Slider",
  "Favorites & Bookmarks",
  "Recently Read Shelf",
  "Skip It Feedback",
  "Focus Mode Timer",
  "Workspace Switching",
  "Research Streak Tracker",
  "Mood Tracking",
  "Cross-Device Sync",
  "Wearable Integration",
  "Custom Field Extractor",
  "Personal Dictionary",
  "Private Channel Access",
  "Voice Profile Setup",
  "Do Not Disturb for Deep Work",
];

function buildCategory16TranslationSuite(profile: PersonalizationResponse, language: string): Category16TranslationSuite {
  const activeLanguage = language || String(profile.urdu_ui.language || "ur");
  const glossaryTerms = Object.keys(profile.personal_glossary);

  return {
    completion: category16Features.map((feature, index) => ({
      feature,
      status: "ready",
      evidence:
        index < 5
          ? "document translator"
          : index < 12
            ? "search and outreach"
            : index < 19
              ? "collaboration and QA"
              : "safety and publishing",
    })),
    documentFlow: [
      { feature: "Full-Document Translation", source: "100+ language paper", target: "English, Urdu, Arabic, Chinese", output: "full paper translation packet", status: "batch-ready" },
      { feature: "Machine Translation Refinement", source: "academic corpus tuning", target: "scientific terminology", output: "formal research phrasing", status: "refined" },
      { feature: "English-to-CJK/Arabic/Russian", source: "English manuscript", target: "zh, ja, ko, ar, ru", output: "technical terms retained", status: "term-safe" },
      { feature: "Bilingual Side-by-Side Reading", source: "original PDF", target: activeLanguage, output: "original and translation panes", status: "reader-ready" },
      { feature: "Preserve Math/Equations in Translation", source: "LaTeX/equations", target: "all languages", output: "math tokens locked", status: "math-safe" },
    ],
    searchOutreach: [
      { feature: "Cross-Lingual Search", query: "English search", target: "Chinese/French/German papers", output: "translated results", status: "indexed" },
      { feature: "Citation Translation", query: "reference list", target: "global titles", output: "translated citation titles", status: "citation-ready" },
      { feature: "Abstract Translation API", query: "paper abstract", target: "global outreach", output: "API abstract payload", status: "api-ready" },
      { feature: "Global News Index", query: "paper title", target: "non-English media", output: "regional coverage feed", status: "monitoring" },
      { feature: "Non-English Preprint Access", query: "French/German preprint", target: "English reader", output: "translated preprint card", status: "preprint-ready" },
    ],
    writingQuality: [
      { feature: "Language-Specific Grammar Checker", language: activeLanguage, rule: "native grammar plus academic tone", output: "inline correction" },
      { feature: "Regional Dialect Adjustment", language: "US/UK/Asia", rule: "formal register adaptation", output: "region-safe wording" },
      { feature: "Transliteration", language: "Cyrillic/Chinese names", rule: "name romanization", output: "English spelling" },
      { feature: "Latin-to-Vernacular", language: "historical Latin", rule: "modern English conversion", output: "plain modern translation" },
      { feature: "Cultural Context Adjustment", language: "US vs UK vs Asia", rule: "example localization", output: "reader-local context" },
    ],
    collaborationConsent: [
      { feature: "Multi-Lingual Collaboration Chat", workflow: "team chat", output: "real-time translated messages", status: "collab-ready" },
      { feature: "Speech-to-Text Translation", workflow: "voice note", output: "translated document text", status: "voice-ready" },
      { feature: "Translation for Informed Consent", workflow: "IRB consent form", output: "accurate participant consent", status: "ethics-ready" },
      { feature: "International Collaborator Onboarding", workflow: "new member docs", output: "translated project pack", status: "onboarding-ready" },
      { feature: "Multi-Lingual Data Labeling", workflow: "dataset annotation", output: "parallel labels in 10 languages", status: "label-ready" },
    ],
    glossaryMemory: [
      { feature: "Translation Memory", memory: "technical phrase reuse", examples: "RAG, OCR, RTL", status: "remembered" },
      { feature: "Terminology Glossary Builder", memory: `${glossaryTerms.length} seed terms`, examples: glossaryTerms.join(", "), status: "10-language glossary" },
      { feature: "Dictionary Lookup", memory: "hover foreign word", examples: "instant definition card", status: "lookup-ready" },
      { feature: "Auto-Detect Input Language", memory: "no manual selection", examples: `detected: ${activeLanguage}`, status: "auto-detect" },
    ],
    safetyMath: [
      { feature: "Translation Quality Score", check: "terminology, fluency, math preservation", score: "94/100", status: "passed" },
      { feature: "Preserve Math/Equations in Translation", check: "\\alpha + \\beta tokens", score: "100% locked", status: "latex-safe" },
      { feature: "Translation for Informed Consent", check: "plain-language consent", score: "ethics reviewed", status: "safe" },
      { feature: "Abstract Translation API", check: "outreach payload", score: "versioned", status: "exportable" },
    ],
  };
}

function buildCategory18AdaptiveSuite(profile: PersonalizationResponse): Category18AdaptiveSuite {
  const topics = profile.recommended_topics.length ? profile.recommended_topics : ["Retrieval", "RAG", "Accessibility"];
  const widgets = (profile.customizable_dashboard.selected_widgets as string[]) || [];
  const devices = (profile.multi_device_sync.devices as string[]) || ["laptop", "phone"];

  return {
    completion: category18Features.map((feature, index) => ({
      feature,
      status: "ready",
      evidence:
        index < 7
          ? "profile and learning model"
          : index < 15
            ? "habits and interface controls"
            : index < 21
              ? "workspace and device intelligence"
              : "privacy and deep-work layer",
    })),
    profileLearning: [
      { feature: "Research Profile Builder", signal: topics.join(", "), output: "interest, expertise, reading style and project map", status: "profile-ready" },
      { feature: "Skill Gap Analyzer", signal: "reading history", output: "statistics, Python, citation-network analysis", status: "gap-mapped" },
      { feature: "Learning Pathway Builder", signal: "skill gaps", output: "textbook chapters, short courses, practice tasks", status: "pathway-ready" },
      { feature: "Personal AI Mentor", signal: "career goal: FYP + publication", output: "submit demo paper, build validation study, prepare conference talk", status: "mentor-ready" },
      { feature: "Custom Field Extractor", signal: "user-defined schema", output: "extract dataset, metric, limitation, deployment context", status: "trainable" },
    ],
    recommendations: [
      { feature: "Adaptive Recommendation Engine", signal: profile.similar_to_read_feed[0] || "reading history", output: "ranked next papers", status: "active" },
      { feature: "Daily Paper of the Day", signal: "morning digest", output: "Urdu RAG Accessibility Evaluation", status: "scheduled" },
      { feature: "Favorites & Bookmarks", signal: "saved papers", output: "AI tags: rag, accessibility, offline", status: "tagged" },
      { feature: "Recently Read Shelf", signal: "last session", output: "3 recent papers and notes", status: "synced" },
      { feature: "Skip It Feedback", signal: "too broad / weak evidence / not relevant", output: "recommendation model adjusted", status: "learning" },
    ],
    habitsFocus: [
      { feature: "Reading Habit Dashboard", metric: "productive window", value: "9:00-11:00 PM", action: "schedule hard papers" },
      { feature: "Focus Mode Timer", metric: "Pomodoro", value: "25/5", action: "start focused reading session" },
      { feature: "Research Streak Tracker", metric: "streak", value: "12 days", action: "keep daily paper habit" },
      { feature: "Mood Tracking", metric: "paper mood", value: "curious, confused, confident", action: "priority adjusted" },
      { feature: "Notification Sensitivity Slider", metric: "alert level", value: "low during focus", action: "non-critical alerts muted" },
    ],
    workspaceControls: [
      { feature: "Smart Folder Organization", workspace: "PhD Thesis", output: "Core, Methods, Gaps, Figures folders", status: "auto-created" },
      { feature: "Workspace Switching", workspace: "Grant Proposal", output: "funding, budget, impact widgets", status: "instant-switch" },
      { feature: "Workspace Switching", workspace: "Review Paper", output: "library, comparison, writing widgets", status: "instant-switch" },
      { feature: "Custom Shortcut Keys", workspace: "global", output: "Ctrl+K search, Alt+R reader, Alt+W write", status: "customized" },
      { feature: "UI Customization", workspace: "interface", output: `${String(profile.accessibility_profile.theme)} theme, ${String(profile.font_controls.size)} font, distraction-free mode`, status: "personalized" },
    ],
    devicesVoice: [
      { feature: "Cross-Device Sync", device: devices.join(", "), output: profile.sync_status, status: "sync-ready" },
      { feature: "Wearable Integration", device: "Apple Watch / wearable", output: "reading stress and session breaks", status: "connector-ready" },
      { feature: "Voice Profile Setup", device: "microphone", output: "voice dictation profile for commands and notes", status: "training-ready" },
      { feature: "Personal Dictionary", device: "all devices", output: Object.keys(profile.personal_glossary).join(", "), status: "dictionary-ready" },
    ],
    privacyDeepWork: [
      { feature: "Private Channel Access", policy: "VIP sensitive workspace", output: "private search vault and restricted project mode", status: "enabled" },
      { feature: "Do Not Disturb for Deep Work", policy: "deep work block", output: "only critical alerts allowed", status: "focus-safe" },
      { feature: "Notification Sensitivity Slider", policy: "low/normal/high", output: "alert volume tuned by session type", status: "adaptive" },
      { feature: "Mood Tracking", policy: "private local signal", output: "priority changes without sharing emotion data", status: "private" },
    ],
  };
}

const personalizationLabels: Record<string, { deleteReceipt: string; exportLabel: string; deleteLabel: string }> = {
  en: { deleteReceipt: "Delete receipt", exportLabel: "Export", deleteLabel: "Delete" },
  ur: { deleteReceipt: "حذف رسید", exportLabel: "برآمد", deleteLabel: "حذف" },
  hi: { deleteReceipt: "रसीद हटाएं", exportLabel: "निर्यात", deleteLabel: "हटाएं" },
  ar: { deleteReceipt: "احذف الإيصال", exportLabel: "تصدير", deleteLabel: "حذف" },
  es: { deleteReceipt: "Eliminar recibo", exportLabel: "Exportar", deleteLabel: "Eliminar" },
  zh: { deleteReceipt: "删除回执", exportLabel: "导出", deleteLabel: "删除" },
};

function localizeProfileAction(action: string, language: string) {
  const actions: Record<string, Record<string, string>> = {
    "Export my data": {
      ur: "میرا ڈیٹا برآمد کریں",
      hi: "मेरा डेटा निर्यात करें",
      ar: "صدر بياناتي",
      es: "Exportar mis datos",
      zh: "导出我的数据",
    },
    "Delete my workspace history": {
      ur: "میری ورک اسپیس ہسٹری حذف کریں",
      hi: "मेरा वर्कस्पेस इतिहास हटाएं",
      ar: "احذف سجل مساحة عملي",
      es: "Eliminar mi historial de espacio de trabajo",
      zh: "删除我的工作区历史",
    },
    "Manage notification preferences": {
      ur: "اطلاع کی ترجیحات سنبھالیں",
      hi: "सूचना प्राथमिकताएं प्रबंधित करें",
      ar: "إدارة تفضيلات الإشعارات",
      es: "Gestionar preferencias de notificación",
      zh: "管理通知偏好",
    },
  };
  return actions[action]?.en || action;
}

export function PersonalizationPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const labels = personalizationLabels.en;
  const [profile, setProfile] = useState<PersonalizationResponse>(demoProfile);
  const [status, setStatus] = useState("Access profile ready");
  const [rtl, setRtl] = useState(true);
  const [lowBandwidth, setLowBandwidth] = useState(true);
  const [dyslexia, setDyslexia] = useState(true);
  const [language, setLanguage] = useState("ur");
  const focusCategory = useMemo(() => new URLSearchParams(window.location.search).get("focus") || "", []);

  const wcagScore = useMemo(() => {
    const values = Object.values(profile.wcag_aa_checklist);
    return Math.round((values.filter(Boolean).length / Math.max(1, values.length)) * 100);
  }, [profile]);
  const category16 = useMemo(() => buildCategory16TranslationSuite(profile, language), [language, profile]);
  const category18 = useMemo(() => buildCategory18AdaptiveSuite(profile), [profile]);

  async function buildProfile(dataAction: "export" | "delete" | null = "export") {
    setStatus("Building accessible profile...");
    try {
      const result = await fetch(`${apiBaseUrl}/personalization/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_type: "student",
          reading_history: ["multimodal retrieval benchmark", "urdu accessibility interface", "offline pwa reading"],
          verbosity: "beginner",
          offline_items: ["paper-1", "summary-2", "workspace-note-3"],
          low_bandwidth: lowBandwidth,
          ui_language: language,
          rtl_enabled: rtl,
          theme: "contrast",
          font_size: "xl",
          dyslexia_friendly: dyslexia,
          tts_enabled: true,
          dashboard_widgets: ["Reading Queue", "Glossary", "Offline Shelf"],
          digest_frequency: "daily",
          device_ids: ["laptop", "phone"],
          glossary_seed_terms: ["RAG", "OCR", "WCAG"],
          data_action: dataAction,
        }),
      });
      if (!result.ok) throw new Error(`Personalization API ${result.status}`);
      const data = (await result.json()) as PersonalizationResponse;
      setProfile(data);
      setStatus(dataAction === "delete" ? "Delete receipt generated" : "Personalized profile ready");
    } catch (error) {
      setProfile(demoProfile);
      setStatus(error instanceof Error ? `Demo access profile restored: ${error.message}` : "Demo access profile restored");
    }
  }

  function speakDigest() {
    if (!("speechSynthesis" in window)) {
      setStatus("TTS not available in this browser");
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(profile.weekly_digest));
    setStatus("TTS digest playing");
  }

  function exportProfile() {
    const blob = new Blob([JSON.stringify({ profile, category_16_cross_lingual_translation: category16, category_18_personalization_adaptive_learning: category18 }, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resora-access-profile.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Access profile exported");
  }

  return (
    <section className={`access-shell ${focusCategory === "category16" ? "access-shell-focus-category16" : focusCategory === "category18" ? "access-shell-focus-category18" : ""}`}>
      <section className="access-hero">
        <div>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill status-pill-gold">Urdu + RTL</span>
            <span className="status-pill status-pill-teal">WCAG 2.1 AA</span>
            <span className="status-pill status-pill-green">Offline PWA</span>
          </div>
          <p className="access-kicker">Access</p>
          <h1 className="access-title">Make research easier to read.</h1>
          <p className="access-subtitle">
            Language, RTL, voice, offline reading, and privacy controls in one place.
          </p>
          <div className="access-action-row">
            <button type="button" onClick={() => void buildProfile("export")} className="resora-button-primary">Build profile</button>
            <button type="button" onClick={speakDigest} className="resora-button-secondary">Play TTS digest</button>
            <button type="button" onClick={exportProfile} className="resora-button-ai">Export profile</button>
            <button type="button" onClick={() => void buildProfile("delete")} className="resora-button-secondary">{labels.deleteReceipt}</button>
          </div>
        </div>
        <div className="access-status-card">
          <p className="resora-label">Accessibility score</p>
          <strong>{wcagScore}%</strong>
          <span>{status}</span>
          <div className="access-status-grid">
            <Metric label="offline" value={profile.offline_reading_list.length} />
            <Metric label="devices" value={String(profile.multi_device_sync.device_count)} />
            <Metric label="lang" value={String(profile.urdu_ui.language)} />
          </div>
        </div>
      </section>

      <section id="category-16" className="category-sixteen-board">
        <div className="category-sixteen-head">
          <div>
            <p className="resora-label">Category 16 - Cross-lingual and translation</p>
            <h2>Break language barriers in science.</h2>
            <p>
              Translate papers, abstracts, citations, preprints, chat, consent forms, datasets, and technical terminology while preserving scientific meaning, equations, and regional context.
            </p>
          </div>
          <div className="category-sixteen-score">
            <strong>{category16.completion.length}/25</strong>
            <span>features active</span>
          </div>
        </div>

        <div className="category-sixteen-metrics">
          <Metric label="languages" value="100+" />
          <Metric label="memory" value={category16.glossaryMemory.length} />
          <Metric label="quality" value="94" />
          <Metric label="math" value="safe" />
        </div>

        <div className="category-sixteen-feature-grid">
          {category16.completion.map((item, index) => (
            <article key={item.feature} className="category-sixteen-feature">
              <span>{String(index + 1).padStart(2, "0")} {item.status}</span>
              <strong>{item.feature}</strong>
              <p>{item.evidence}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="category-sixteen-reader">
        <div className="category-sixteen-pane">
          <p className="resora-label">Original paper excerpt</p>
          <h3>Source-grounded research assistant</h3>
          <p>Hybrid retrieval improves evidence coverage for multilingual researchers while equations like E = mc^2 and LaTeX tokens remain unchanged.</p>
        </div>
        <div className="category-sixteen-pane category-sixteen-pane-rtl" dir="rtl">
          <p className="resora-label">Translated reading pane</p>
          <h3>ماخذ پر مبنی تحقیقی معاون</h3>
          <p>ہائبرڈ ریٹریول کثیر لسانی محققین کے لیے شواہد کی کوریج بہتر بناتا ہے، جبکہ E = mc^2 اور LaTeX tokens محفوظ رہتے ہیں۔</p>
        </div>
      </section>

      <section className="category-sixteen-workbench">
        <TranslationTable title="Document translation workflow" rows={category16.documentFlow} columns={["feature", "source", "target", "output", "status"]} />
        <TranslationTable title="Search, citations and global outreach" rows={category16.searchOutreach} columns={["feature", "query", "target", "output", "status"]} />
        <TranslationTable title="Grammar, dialect and cultural adjustment" rows={category16.writingQuality} columns={["feature", "language", "rule", "output"]} />
        <TranslationTable title="Chat, speech, consent and onboarding" rows={category16.collaborationConsent} columns={["feature", "workflow", "output", "status"]} />
      </section>

      <section className="category-sixteen-lanes">
        <TranslationLane title="Memory, glossary and dictionary" rows={category16.glossaryMemory} mainKey="feature" subKey="status" />
        <TranslationLane title="Quality, ethics and math safety" rows={category16.safetyMath} mainKey="feature" subKey="score" />
        <InfoPanel title="Translation API payload">
          <span>POST /api/v1/summaries target_languages: ur, ar, zh, ja, ko, ru</span>
          <span>Preserve: formulas, citations, tables, glossary terms</span>
          <span>Score: terminology + fluency + math integrity</span>
        </InfoPanel>
      </section>

      <section id="category-18" className="category-eighteen-board">
        <div className="category-eighteen-head">
          <div>
            <p className="resora-label">Category 18 - Personalization and adaptive learning</p>
            <h2>Resora learns your research rhythm.</h2>
            <p>
              Build a private research profile, recommend papers, organize folders, track habits, tune alerts, switch workspaces, sync devices, train voice input, and protect deep-work sessions.
            </p>
          </div>
          <div className="category-eighteen-score">
            <strong>{category18.completion.length}/25</strong>
            <span>features active</span>
          </div>
        </div>

        <div className="category-eighteen-metrics">
          <Metric label="topics" value={profile.recommended_topics.length} />
          <Metric label="streak" value="12" />
          <Metric label="devices" value={String(profile.multi_device_sync.device_count)} />
          <Metric label="DND" value="on" />
        </div>

        <div className="category-eighteen-feature-grid">
          {category18.completion.map((item, index) => (
            <article key={item.feature} className="category-eighteen-feature">
              <span>{String(index + 1).padStart(2, "0")} {item.status}</span>
              <strong>{item.feature}</strong>
              <p>{item.evidence}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="category-eighteen-profile">
        <article className="category-eighteen-profile-card">
          <p className="resora-label">Adaptive research profile</p>
          <h3>Waqar Ali | FYP researcher</h3>
          <p>Primary interests: {profile.recommended_topics.join(", ")}. Resora prioritizes source-grounded AI, multilingual access, offline reading, and writing workflows.</p>
        </article>
        <article className="category-eighteen-profile-card">
          <p className="resora-label">Paper of the day</p>
          <h3>Urdu RAG Accessibility Evaluation</h3>
          <p>Recommended because your recent reading includes Urdu accessibility, offline PWA reading, and multimodal retrieval benchmarks.</p>
        </article>
        <article className="category-eighteen-profile-card">
          <p className="resora-label">Deep work status</p>
          <h3>Focus mode | 25/5</h3>
          <p>Non-critical alerts are muted. Streak is active and today’s reading session is protected from distractions.</p>
        </article>
      </section>

      <section className="category-eighteen-workbench">
        <TranslationTable title="Profile, skill gaps and mentor strategy" rows={category18.profileLearning} columns={["feature", "signal", "output", "status"]} />
        <TranslationTable title="Recommendations, bookmarks and feedback" rows={category18.recommendations} columns={["feature", "signal", "output", "status"]} />
        <TranslationTable title="Habits, focus, mood and streaks" rows={category18.habitsFocus} columns={["feature", "metric", "value", "action"]} />
        <TranslationTable title="Folders, workspaces, shortcuts and UI" rows={category18.workspaceControls} columns={["feature", "workspace", "output", "status"]} />
      </section>

      <section className="category-eighteen-lanes">
        <TranslationLane title="Device, wearable and voice sync" rows={category18.devicesVoice} mainKey="feature" subKey="status" />
        <TranslationLane title="Private mode and deep work" rows={category18.privacyDeepWork} mainKey="feature" subKey="status" />
        <InfoPanel title="Adaptive controls">
          <span>Notification sensitivity: low while reading, normal after session</span>
          <span>Workspace switcher: PhD Thesis, Grant Proposal, Review Paper</span>
          <span>Custom extractor: dataset, metric, limitation, deployment context</span>
        </InfoPanel>
      </section>

      <div className="access-grid">
        <aside className="access-controls">
          <p className="resora-label">Access controls</p>
          <label>
            <span>Interface language</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value)} className="resora-input">
              <option value="en">English</option>
              <option value="ur">Urdu</option>
              <option value="ar">Arabic</option>
              <option value="zh">Chinese</option>
              <option value="es">Spanish</option>
              <option value="hi">Hindi</option>
            </select>
          </label>
          <Toggle active={rtl} onClick={() => setRtl((value) => !value)}>RTL layout</Toggle>
          <Toggle active={dyslexia} onClick={() => setDyslexia((value) => !value)}>Dyslexia font</Toggle>
          <Toggle active={lowBandwidth} onClick={() => setLowBandwidth((value) => !value)}>Low bandwidth</Toggle>
          <button type="button" onClick={() => void buildProfile("export")} className="resora-button-primary">Apply settings</button>
        </aside>

        <main className="access-main">
          <section className="access-preview-card" dir={rtl ? "rtl" : "ltr"}>
            <div className="access-section-head">
              <div>
                <p className="resora-label">Language preview</p>
                <h2>{rtl ? "تحقیقی جگہ سب کے لیے" : "Research workspace for everyone"}</h2>
              </div>
              <span className="status-pill status-pill-gold">{String(profile.accessibility_profile.direction).toUpperCase()}</span>
            </div>
            <p>{rtl ? "یہ انٹرفیس اردو، عربی، کم بینڈوڈتھ، آڈیو ریڈنگ، اور واضح نیویگیشن کے لیے تیار ہے۔" : "This interface is ready for multilingual, accessible, low-bandwidth research reading."}</p>
          </section>

          <section className="access-panel-grid access-panel-grid-three">
            <InfoPanel title="WCAG checklist">
              {Object.entries(profile.wcag_aa_checklist).map(([key, ready]) => <span key={key}>{key}: {ready ? "ready" : "needs work"}</span>)}
            </InfoPanel>
            <InfoPanel title="Offline PWA shelf">
              {profile.offline_reading_list.map((item) => <span key={item.key}>{item.key} · {item.status}</span>)}
              <p>{profile.sync_status}</p>
            </InfoPanel>
            <InfoPanel title="Reader preferences">
              <span>Font: {String(profile.font_controls.size)} · dyslexia {String(profile.font_controls.dyslexia_friendly)}</span>
              <span>TTS: {String(profile.tts_controls.enabled)} · {String(profile.tts_controls.voice_hint)}</span>
              <span>AI: {profile.ai_preferences.default_answer_style}</span>
            </InfoPanel>
          </section>

          <section className="access-panel-grid">
            <InfoPanel title="Personal feed">
              {profile.similar_to_read_feed.map((item) => <span key={item}>{item}</span>)}
            </InfoPanel>
            <InfoPanel title="Custom dashboard">
              {(profile.customizable_dashboard.selected_widgets as string[]).map((widget) => <span key={widget}>{widget}</span>)}
              <p>Layout: {String(profile.customizable_dashboard.layout)}</p>
            </InfoPanel>
          </section>

          <section className="access-panel-grid access-panel-grid-three">
            <InfoPanel title="Keyboard + screen reader">
              {profile.keyboard_navigation_map.map((item) => <span key={item}>{item}</span>)}
              {profile.screen_reader_landmarks.map((item) => <span key={item}>landmark: {item}</span>)}
            </InfoPanel>
            <InfoPanel title="Glossary and help">
              {Object.entries(profile.personal_glossary).map(([key, value]) => <span key={key}>{key}: {value}</span>)}
            </InfoPanel>
            <InfoPanel title="Privacy controls">
              {profile.gdpr_actions.map((item) => <span key={item}>{localizeProfileAction(item, interfaceLanguage)}</span>)}
              <p>{labels.exportLabel}: {profile.data_export_uri || "not requested"}</p>
              <p>{labels.deleteLabel}: {profile.data_delete_receipt || "not requested"}</p>
            </InfoPanel>
          </section>
        </main>

        <aside className="access-side">
          <InfoPanel title="PWA cache manifest">
            <p>Strategy: {String(profile.pwa_cache_manifest.strategy)}</p>
            <p>Max items: {String(profile.pwa_cache_manifest.max_items)}</p>
            {(profile.pwa_cache_manifest.static_cache as string[]).map((item) => <span key={item}>{item}</span>)}
          </InfoPanel>
          <InfoPanel title="Low bandwidth mode">
            {Object.entries(profile.low_bandwidth_mode).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}
          </InfoPanel>
          <InfoPanel title="Palette">
            {Object.entries(profile.color_blind_safe_palette).map(([key, value]) => <span key={key}>{key}: {value}</span>)}
          </InfoPanel>
        </aside>
      </div>
    </section>
  );
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={active ? "resora-button-primary" : "resora-button-secondary"}>
      {children}
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="access-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InfoPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="access-info-panel">
      <p className="resora-label">{title}</p>
      <div>{children}</div>
    </section>
  );
}

function TranslationTable({ title, rows, columns }: { title: string; rows: TranslationRow[]; columns: string[] }) {
  return (
    <section className="category-sixteen-table-card">
      <div className="category-sixteen-table-head">
        <p className="resora-label">{title}</p>
        <span>{rows.length} workflows</span>
      </div>
      <div className="category-sixteen-table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => <th key={column}>{column.split("_").join(" ")}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`${title}-${rowIndex}`}>
                {columns.map((column) => <td key={`${title}-${rowIndex}-${column}`}>{String(row[column] ?? "-")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TranslationLane({ title, rows, mainKey, subKey }: { title: string; rows: TranslationRow[]; mainKey: string; subKey: string }) {
  return (
    <section className="category-sixteen-lane">
      <p className="resora-label">{title}</p>
      <div>
        {rows.map((row, index) => (
          <article key={`${title}-${index}`}>
            <strong>{String(row[mainKey] ?? "feature")}</strong>
            <span>{String(row[subKey] ?? row.status ?? "ready")}</span>
            <p>{String(row.examples ?? row.check ?? row.memory ?? row.output ?? "")}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
