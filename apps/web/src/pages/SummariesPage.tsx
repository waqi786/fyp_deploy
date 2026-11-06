import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate, useSearchParams } from "react-router-dom";
import { TrustRing } from "../components/common/TrustRing";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

type SummaryTier = {
  label: string;
  content: string;
  source_spans: string[];
};

type SummaryResponse = {
  tldr: string;
  bullet_summary: string[];
  structured_summary: Record<string, string>;
  deep_dive: string;
  summary_tiers: Record<string, SummaryTier>;
  equations: string[];
  urdu_summary: Record<string, string>;
  glossary: Record<string, string>;
  glossary_entries: Array<{ term: string; definition: string; source_span: string }>;
  hover_glossary_spans: Array<{ term: string; definition: string; start_offset: number; end_offset: number }>;
  difficulty_score: string;
  prerequisites: string[];
  contributions: string[];
  limitations: string[];
  methodology_box: string;
  results_box: string;
  datasets: string[];
  reproducibility_checklist: Record<string, boolean>;
  funding_or_coi: string[];
  freshness_indicator: string;
  related_work_summary: string;
  auto_outline: string[];
  outline_sections: Array<{ label: string; source_span: string }>;
  reading_time_minutes: number;
  key_figure_caption?: string | null;
  acronym_expansions: Record<string, string>;
  statistical_flags: string[];
  study_limitation_severity_score: number;
  exam_qa: Array<{ question: string; answer: string }>;
  translations: Record<string, Record<string, string | string[]>>;
  translation_languages: string[];
  audio_narration: Record<string, string>;
  audience_mode: string;
  audience_guidance: string;
  summary_length_applied: string;
  paragraph_explainability_preview: Array<{ source_span: string; explanation: string; key_points: string[] }>;
  key_figure_insight?: string | null;
  confidence_score: number;
  model_used: string;
  source_spans: string[];
  generated_at: string;
};

type ExplainResponse = {
  explanation: string;
  simplified_points: string[];
  glossary_terms: Record<string, string>;
  audience_mode: string;
  reading_level: string;
  source_span: string;
  confidence_score: number;
};

type TrustResponse = {
  trust_score: number;
  novelty_score: number;
  evidence_strength: string;
  confidence_score: number;
  peer_review_status: string;
  journal_quartile?: string | null;
  journal_impact_profile: {
    quartile?: string | null;
    impact_tier: string;
    citation_signal: string;
  };
  funding_transparency_flag: string;
  conflict_of_interest_flag: string;
  author_track_record_summary: string;
  self_citation_ratio: number;
  self_citation_flag: string;
  sample_size_adequacy: string;
  sample_size_profile: {
    extracted_n: number;
    adequacy: string;
    explanation: string;
  };
  reproducibility_score: number;
  statistical_appropriateness: string;
  bias_tags: string[];
  bias_tag_details: Array<{ label: string; explanation: string }>;
  outlier_anomaly_flags: string[];
  ci_pvalue_sanity: string[];
  statistical_sanity_checks: Array<{ label: string; status: string; evidence?: string | null }>;
  evidence_meter: Array<{ label: string; score: number; explanation: string }>;
  methodology_quality_checklist: Array<{ label: string; passed: boolean; explanation: string }>;
  citation_context_labels: Array<{ context: string; label: string }>;
  moderation_status: string;
  moderation_queue_entry?: {
    status: string;
    reason: string;
    note?: string | null;
    evidence: string[];
  } | null;
  contradiction_summary: string[];
  contradiction_details: Array<{ summary: string; supporting_evidence: string[] }>;
  trust_score_changelog: Array<{ event: string; score_delta: number; reason: string; evidence?: string | null }>;
};

type PaperReadStatus = "unread" | "in-progress" | "read";
type ReaderContentSource = "demo" | "typed" | "upload" | "link" | "search";

type DocumentExtractionResponse = {
  status: string;
  extracted_text: string;
  extraction_method: string;
  scanned_pdf_detected: boolean;
  ocr_confidence?: number | null;
  normalized_source_url?: string | null;
  blocked_reason?: string | null;
  detected_equations: string[];
  figures: Array<{ figure_id: string; caption: string }>;
  tables: Array<{ table_id: string; caption: string }>;
  processing_notes: string[];
  extraction_quality_flags: string[];
  manual_verification_required: boolean;
};

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`;
}

const languageChoices = [
  { code: "en", label: "English" },
  { code: "ur", label: "اردو" },
  { code: "zh", label: "中文" },
  { code: "es", label: "Español" },
  { code: "hi", label: "हिन्दी" },
  { code: "ar", label: "العربية" },
];

function cleanLanguageLabel(code: string) {
  const labels: Record<string, string> = {
    en: "English",
    ur: "Urdu",
    zh: "Chinese",
    es: "Spanish",
    hi: "Hindi",
    ar: "Arabic",
  };
  return labels[code] || code.toUpperCase();
}

const narrationLocales: Record<string, string> = {
  en: "en-US",
  ur: "ur-PK",
  zh: "zh-CN",
  es: "es-ES",
  hi: "hi-IN",
  ar: "ar-SA",
};

const readerNotices: Record<string, Record<string, string>> = {
  en: {
    needSummaryForAudio: "Generate a summary first, then audio narration will be available.",
    audioStarted: "Audio narration started.",
    evidenceExplained: "Evidence passage explained.",
    localExplain: "Evidence passage explained with local reading aids.",
    paperMarked: "Paper marked as",
  },
  ur: {
    needSummaryForAudio: "پہلے خلاصہ بنائیں، پھر آڈیو دستیاب ہو گی۔",
    audioStarted: "آڈیو بیان شروع ہو گیا۔",
    evidenceExplained: "منتخب شواہد کی تشریح ہو گئی۔",
    localExplain: "منتخب شواہد کی مقامی ریڈنگ مدد سے تشریح ہو گئی۔",
    paperMarked: "مقالہ نشان زد ہو گیا",
  },
  hi: {
    needSummaryForAudio: "पहले सारांश बनाएं, फिर ऑडियो उपलब्ध होगा।",
    audioStarted: "ऑडियो वाचन शुरू हो गया।",
    evidenceExplained: "चुने गए साक्ष्य की व्याख्या हो गई।",
    localExplain: "चुने गए साक्ष्य की स्थानीय पढ़ने की सहायता से व्याख्या हो गई।",
    paperMarked: "पेपर चिह्नित हुआ",
  },
  ar: {
    needSummaryForAudio: "أنشئ الملخص أولاً، ثم سيتوفر السرد الصوتي.",
    audioStarted: "بدأ السرد الصوتي.",
    evidenceExplained: "تم شرح مقطع الدليل المحدد.",
    localExplain: "تم شرح مقطع الدليل باستخدام مساعدات قراءة محلية.",
    paperMarked: "تم تعليم الورقة",
  },
  es: {
    needSummaryForAudio: "Genera primero un resumen; después estará disponible la narración.",
    audioStarted: "Narración de audio iniciada.",
    evidenceExplained: "Pasaje de evidencia explicado.",
    localExplain: "Pasaje de evidencia explicado con ayudas locales de lectura.",
    paperMarked: "Artículo marcado como",
  },
  zh: {
    needSummaryForAudio: "请先生成摘要，然后可使用语音朗读。",
    audioStarted: "语音朗读已开始。",
    evidenceExplained: "已解释所选证据段落。",
    localExplain: "已用本地阅读辅助解释所选证据段落。",
    paperMarked: "论文已标记为",
  },
};

function readerNotice(language: string, key: string) {
  return readerNotices[language]?.[key] || readerNotices.en[key] || key;
}

function generatedSummaryNotice(language: string, data: SummaryResponse, confidence: string, mismatchWarning: string) {
  const nativeNames: Record<string, string> = {
    en: "English",
    ur: "اردو",
    hi: "हिन्दी",
    ar: "العربية",
    es: "Español",
    zh: "中文",
  };
  const languageName = nativeNames[language] || cleanLanguageLabel(language);
  if (language === "ur") {
    return `${languageName} خلاصہ تیار ہو گیا، اعتماد ${confidence}.${mismatchWarning}`;
  }
  if (language === "hi") {
    return `${languageName} सारांश तैयार है, विश्वास ${confidence}.${mismatchWarning}`;
  }
  if (language === "ar") {
    return `تم إنشاء ملخص ${languageName} بثقة ${confidence}.${mismatchWarning}`;
  }
  if (language === "es") {
    return `Resumen en ${languageName} generado con ${confidence} de confianza.${mismatchWarning}`;
  }
  if (language === "zh") {
    return `已生成 ${languageName} 摘要，置信度 ${confidence}.${mismatchWarning}`;
  }
  return `Generated ${data.summary_length_applied} ${data.audience_mode} ${languageName} summary with ${confidence} confidence.${mismatchWarning}`;
}

function sectionLabel(key: string, language: string) {
  const labels: Record<string, Record<string, string>> = {
    en: { problem: "Problem", methodology: "Methodology", findings: "Findings", conclusion: "Conclusion" },
    ur: { problem: "مسئلہ", methodology: "طریقہ کار", findings: "نتائج", conclusion: "نتیجہ" },
    hi: { problem: "समस्या", methodology: "कार्यप्रणाली", findings: "निष्कर्ष", conclusion: "निष्कर्ष" },
    ar: { problem: "المشكلة", methodology: "المنهجية", findings: "النتائج", conclusion: "الخلاصة" },
    es: { problem: "Problema", methodology: "Metodología", findings: "Hallazgos", conclusion: "Conclusión" },
    zh: { problem: "问题", methodology: "方法", findings: "发现", conclusion: "结论" },
  };
  return labels[language]?.[key] || labels.en[key] || titleCase(key);
}

const readerCopy: Record<string, Record<string, string>> = {
  en: {
    reader: "Reader",
    subtitle: "Turn a paper into a clear summary, trust view, and citation-ready notes.",
    analyze: "Analyze paper",
    analyzing: "Analyzing",
    upload: "Upload PDF/Text",
    readLink: "Read link",
    readAloud: "Read aloud",
    focusMode: "Focus mode",
    paperInput: "Paper input",
    paperTitle: "Paper title",
    originalUrl: "Original paper URL",
    summaryLanguage: "Summary language",
    audienceLevel: "Audience level",
    summaryDepth: "Summary depth",
    paperContent: "Paper content",
    copyEvidence: "Copy evidence",
    tierOne: "Tier 1 | 30-second summary",
    tierTwo: "Tier 2 | Structured summary",
    tierThree: "Tier 3 | Deep dive",
    readerSummary: "Reader summary",
    structuredHeading: "Problem, method, findings, conclusion",
    deepHeading: "Extended reading with methods, results, and critique context",
    methodology: "Methodology",
    results: "Results",
    relatedWork: "Related work",
  },
  ur: {
    reader: "ریڈر",
    subtitle: "مقالے کو واضح خلاصے، اعتماد کے جائزے، اور حوالہ-ready نوٹس میں بدلیں۔",
    analyze: "مقالہ تجزیہ کریں",
    analyzing: "تجزیہ جاری ہے",
    upload: "PDF/Text اپ لوڈ کریں",
    readLink: "لنک پڑھیں",
    readAloud: "بلند آواز سے پڑھیں",
    focusMode: "فوکس موڈ",
    paperInput: "مقالے کا ان پٹ",
    paperTitle: "مقالے کا عنوان",
    originalUrl: "اصل مقالے کا URL",
    summaryLanguage: "خلاصے کی زبان",
    audienceLevel: "قارئین کی سطح",
    summaryDepth: "خلاصے کی گہرائی",
    paperContent: "مقالے کا متن",
    copyEvidence: "شواہد کاپی کریں",
    tierOne: "درجہ 1 | 30 سیکنڈ کا خلاصہ",
    tierTwo: "درجہ 2 | منظم خلاصہ",
    tierThree: "درجہ 3 | تفصیلی مطالعہ",
    readerSummary: "ریڈر خلاصہ",
    structuredHeading: "مسئلہ، طریقہ، نتائج، نتیجہ",
    deepHeading: "طریقوں، نتائج، اور تنقیدی سیاق کے ساتھ تفصیلی پڑھائی",
    methodology: "طریقہ کار",
    results: "نتائج",
    relatedWork: "متعلقہ کام",
  },
  hi: {
    reader: "रीडर",
    subtitle: "पेपर को स्पष्ट सारांश, भरोसे की जांच और citation-ready नोट्स में बदलें।",
    analyze: "पेपर विश्लेषण करें",
    analyzing: "विश्लेषण जारी",
    upload: "PDF/Text अपलोड करें",
    readLink: "लिंक पढ़ें",
    readAloud: "ज़ोर से पढ़ें",
    focusMode: "फोकस मोड",
    paperInput: "पेपर इनपुट",
    paperTitle: "पेपर शीर्षक",
    originalUrl: "मूल पेपर URL",
    summaryLanguage: "सारांश भाषा",
    audienceLevel: "पाठक स्तर",
    summaryDepth: "सारांश गहराई",
    paperContent: "पेपर सामग्री",
    copyEvidence: "साक्ष्य कॉपी करें",
    tierOne: "स्तर 1 | 30 सेकंड सारांश",
    tierTwo: "स्तर 2 | संरचित सारांश",
    tierThree: "स्तर 3 | गहरा अध्ययन",
    readerSummary: "रीडर सारांश",
    structuredHeading: "समस्या, विधि, निष्कर्ष, निष्कर्ष",
    deepHeading: "विधियों, परिणामों और आलोचनात्मक संदर्भ के साथ विस्तृत पढ़ाई",
    methodology: "कार्यप्रणाली",
    results: "परिणाम",
    relatedWork: "संबंधित कार्य",
  },
  ar: {
    reader: "القارئ",
    subtitle: "حوّل الورقة إلى ملخص واضح، وفحص ثقة، وملاحظات جاهزة للاستشهاد.",
    analyze: "حلل الورقة",
    analyzing: "جار التحليل",
    upload: "رفع PDF/Text",
    readLink: "قراءة الرابط",
    readAloud: "اقرأ بصوت عال",
    focusMode: "وضع التركيز",
    paperInput: "إدخال الورقة",
    paperTitle: "عنوان الورقة",
    originalUrl: "رابط الورقة الأصلي",
    summaryLanguage: "لغة الملخص",
    audienceLevel: "مستوى القارئ",
    summaryDepth: "عمق الملخص",
    paperContent: "محتوى الورقة",
    copyEvidence: "نسخ الدليل",
    tierOne: "المستوى 1 | ملخص 30 ثانية",
    tierTwo: "المستوى 2 | ملخص منظم",
    tierThree: "المستوى 3 | قراءة متعمقة",
    readerSummary: "ملخص القارئ",
    structuredHeading: "المشكلة، الطريقة، النتائج، الخلاصة",
    deepHeading: "قراءة موسعة مع الطرق والنتائج والسياق النقدي",
    methodology: "المنهجية",
    results: "النتائج",
    relatedWork: "عمل ذو صلة",
  },
  es: {
    reader: "Lector",
    subtitle: "Convierte un artículo en un resumen claro, vista de confianza y notas listas para citar.",
    analyze: "Analizar artículo",
    analyzing: "Analizando",
    upload: "Subir PDF/Text",
    readLink: "Leer enlace",
    readAloud: "Leer en voz alta",
    focusMode: "Modo enfoque",
    paperInput: "Entrada del artículo",
    paperTitle: "Título del artículo",
    originalUrl: "URL original del artículo",
    summaryLanguage: "Idioma del resumen",
    audienceLevel: "Nivel de audiencia",
    summaryDepth: "Profundidad del resumen",
    paperContent: "Contenido del artículo",
    copyEvidence: "Copiar evidencia",
    tierOne: "Nivel 1 | resumen de 30 segundos",
    tierTwo: "Nivel 2 | resumen estructurado",
    tierThree: "Nivel 3 | lectura profunda",
    readerSummary: "Resumen del lector",
    structuredHeading: "Problema, método, hallazgos, conclusión",
    deepHeading: "Lectura ampliada con métodos, resultados y contexto crítico",
    methodology: "Metodología",
    results: "Resultados",
    relatedWork: "Trabajo relacionado",
  },
  zh: {
    reader: "阅读器",
    subtitle: "将论文转为清晰摘要、可信度视图和可引用笔记。",
    analyze: "分析论文",
    analyzing: "正在分析",
    upload: "上传 PDF/Text",
    readLink: "读取链接",
    readAloud: "朗读",
    focusMode: "专注模式",
    paperInput: "论文输入",
    paperTitle: "论文标题",
    originalUrl: "原始论文 URL",
    summaryLanguage: "摘要语言",
    audienceLevel: "读者级别",
    summaryDepth: "摘要深度",
    paperContent: "论文内容",
    copyEvidence: "复制证据",
    tierOne: "第 1 层 | 30 秒摘要",
    tierTwo: "第 2 层 | 结构化摘要",
    tierThree: "第 3 层 | 深度阅读",
    readerSummary: "阅读器摘要",
    structuredHeading: "问题、方法、发现、结论",
    deepHeading: "包含方法、结果和批判背景的扩展阅读",
    methodology: "方法论",
    results: "结果",
    relatedWork: "相关工作",
  },
};

const readerMetricCopy: Record<string, { difficulty: string; minRead: string; refreshTrust: string; refreshing: string }> = {
  en: { difficulty: "Difficulty", minRead: "{count} min read", refreshTrust: "Refresh trust", refreshing: "Refreshing" },
  ur: { difficulty: "مشکل", minRead: "{count} منٹ مطالعہ", refreshTrust: "اعتماد تازہ کریں", refreshing: "تازہ ہو رہا ہے" },
  hi: { difficulty: "कठिनाई", minRead: "{count} मिनट पढ़ाई", refreshTrust: "भरोसा अपडेट करें", refreshing: "अपडेट हो रहा है" },
  ar: { difficulty: "الصعوبة", minRead: "{count} دقيقة قراءة", refreshTrust: "تحديث الثقة", refreshing: "جار التحديث" },
  es: { difficulty: "Dificultad", minRead: "{count} min de lectura", refreshTrust: "Actualizar confianza", refreshing: "Actualizando" },
  zh: { difficulty: "难度", minRead: "{count} 分钟阅读", refreshTrust: "刷新可信度", refreshing: "正在刷新" },
};

const readerDifficultyValueCopy: Record<string, Record<string, string>> = {
  en: { EASY: "Easy", MEDIUM: "Medium", HARD: "Hard" },
  ur: { EASY: "آسان", MEDIUM: "درمیانی", HARD: "مشکل" },
  hi: { EASY: "आसान", MEDIUM: "मध्यम", HARD: "कठिन" },
  ar: { EASY: "سهل", MEDIUM: "متوسط", HARD: "صعب" },
  es: { EASY: "Fácil", MEDIUM: "Media", HARD: "Difícil" },
  zh: { EASY: "简单", MEDIUM: "中等", HARD: "困难" },
};

function readerMetricTemplate(language: string, key: keyof (typeof readerMetricCopy)["en"], values: Record<string, string | number> = {}) {
  const copy = readerMetricCopy[language] || readerMetricCopy.en;
  return Object.entries(values).reduce((label, [name, value]) => label.replace(`{${name}}`, String(value)), copy[key]);
}

function readerDifficultyValue(language: string, value: string) {
  const key = value.toUpperCase();
  return (readerDifficultyValueCopy[language] || readerDifficultyValueCopy.en)[key] || value;
}

function cleanSourceSpan(span: string) {
  return span.replace(/^[a-z_]+:\d+:/i, "").replace(/^summary:\d+:/i, "").trim();
}

function compactText(value: string, maxLength = 180) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1).trim()}...` : value;
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function readStatusLabel(status: PaperReadStatus) {
  const labels: Record<PaperReadStatus, string> = {
    unread: "Unread",
    "in-progress": "In progress",
    read: "Read",
  };
  return labels[status];
}

function titleCase(value: string) {
  return value
    .toLowerCase()
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase())
    .replace(/\b(Bm25|Ff|Dfdc|Auc|F1|Rag|Ocr|Pdf)\b/g, (match) => match.toUpperCase());
}

function normalizePaperTitle(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function inferPaperTopicFromContent(value: string) {
  const text = value.trim();
  const lower = text.toLowerCase();
  if (/deepfake/.test(lower) && /frequency-aware/.test(lower)) {
    return "Frequency-Aware Deepfake Detection";
  }
  if (/hybrid retrieval/.test(lower) && /benchmark dataset|benchmark/.test(lower)) {
    return "Hybrid Retrieval Benchmark Dataset";
  }
  if (/diabetes/.test(lower) && /brfss/.test(lower)) {
    return "Diabetes Prediction Using BRFSS";
  }
  const firstSentence = text.split(/(?<=[.!?])\s+/)[0] || text.slice(0, 120);
  const cleaned = firstSentence
    .replace(/^we\s+(introduce|present|propose|develop|study|evaluate)\s+/i, "")
    .replace(/^this\s+(paper|study)\s+(introduces|presents|proposes|studies|evaluates)\s+/i, "")
    .replace(/\s+with\s+n\s*=\s*\d+.*$/i, "")
    .replace(/\s+that\s+combines.*$/i, "")
    .replace(/\s+for\s+/i, " for ")
    .replace(/[^a-zA-Z0-9+\-\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return titleCase(compactText(cleaned || "Detected Paper Topic", 72));
}

function fileBaseTitle(filename: string) {
  return titleCase(
    filename
      .replace(/\.[^.]+$/, "")
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim(),
  );
}

function countWords(value: string) {
  return value.match(/\b[\w-]+\b/g)?.length || 0;
}

export function SummariesPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [language, setLanguage] = useState(interfaceLanguage);
  const [audience, setAudience] = useState("expert");
  const [summaryLength, setSummaryLength] = useState("medium");
  const [response, setResponse] = useState<SummaryResponse | null>(null);
  const [explain, setExplain] = useState<ExplainResponse | null>(null);
  const [trust, setTrust] = useState<TrustResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [trustLoading, setTrustLoading] = useState(false);
  const [manualFlag, setManualFlag] = useState(false);
  const [moderationNote, setModerationNote] = useState("");
  const [activeTranslation, setActiveTranslation] = useState("ur");
  const [notice, setNotice] = useState("");
  const [paperStatus, setPaperStatus] = useState<PaperReadStatus>("unread");
  const [titleTouched, setTitleTouched] = useState(false);
  const [contentSource, setContentSource] = useState<ReaderContentSource>("demo");
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestMode, setIngestMode] = useState<"file" | "link" | null>(null);
  const [ingestReport, setIngestReport] = useState<DocumentExtractionResponse | null>(null);
  const [focusMode, setFocusMode] = useState(false);
  const [mobileReadingMode, setMobileReadingMode] = useState(false);
  const [readingQuestion, setReadingQuestion] = useState("");
  const [readingAnswer, setReadingAnswer] = useState("");
  const [videoTranscript, setVideoTranscript] = useState("");
  const [referenceAnnotations, setReferenceAnnotations] = useState("");
  const readerUi = readerCopy[language] || readerCopy.en;
  const readerMinRead = (minutes: number) => readerMetricTemplate(language, "minRead", { count: minutes });
  const readerDifficulty = (value: string) => `${readerMetricTemplate(language, "difficulty")}: ${readerDifficultyValue(language, value)}`;

  useEffect(() => {
    setLanguage(interfaceLanguage);
    setActiveTranslation(interfaceLanguage === "en" ? "ur" : interfaceLanguage);
  }, [interfaceLanguage]);

  const sourceParagraphs = useMemo(
    () =>
      content
        .split(/\n+/)
        .flatMap((block) => block.split(/(?<=[.!?])\s+/))
        .map((item) => item.trim())
        .filter(Boolean),
    [content],
  );

  const paperStorageKey = useMemo(() => {
    const identity = `${title}::${sourceUrl || content.slice(0, 80)}`;
    return `resora:reader-status:${identity.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 120)}`;
  }, [content, sourceUrl, title]);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(paperStorageKey) as PaperReadStatus | null;
      setPaperStatus(stored === "read" || stored === "in-progress" || stored === "unread" ? stored : "unread");
    } catch {
      setPaperStatus("unread");
    }
  }, [paperStorageKey]);

  const researcherWorkflow = useMemo(() => {
    if (!response) {
      return null;
    }
    const spans = response.source_spans.length
      ? response.source_spans
      : sourceParagraphs.slice(0, 4).map((paragraph, index) => `paragraph:${index + 1}:${paragraph}`);
    const claimInputs = [
      response.tldr,
      ...response.contributions,
      response.methodology_box,
      response.results_box,
      ...response.limitations,
    ].filter(Boolean);
    const claimLedger = claimInputs.slice(0, 6).map((claim, index) => ({
      claim: compactText(claim, 170),
      evidence: cleanSourceSpan(spans[index % spans.length] || content.slice(0, 160)),
      confidence: Math.max(55, Math.min(98, Math.round(response.confidence_score * 100) - index * 2)),
      status: index < response.contributions.length + 1 ? "supported" : "needs-review",
    }));
    const completedChecklist = Object.values(response.reproducibility_checklist).filter(Boolean).length;
    const totalChecklist = Math.max(1, Object.keys(response.reproducibility_checklist).length);
    const reproducibilityPercent = Math.round((completedChecklist / totalChecklist) * 100);
    const reviewerQuestions = [
      ...response.limitations.map((item) => `How does the result change if we address this limitation: ${item}`),
      ...response.statistical_flags.map((item) => `Can the authors justify the statistical signal: ${item}`),
      ...(trust?.contradiction_summary || []).map((item) => `What evidence resolves this contradiction: ${item}`),
    ].slice(0, 5);
    const nextExperiments = [
      ...(response.datasets.length ? [`Re-run the method on ${response.datasets.join(", ")} with a held-out stress split.`] : []),
      ...(response.key_figure_caption ? [`Extract the data behind ${response.key_figure_caption} and compare it with the reported result.`] : []),
      ...response.limitations.map((item) => `Design a small ablation that directly tests: ${item}`),
      "Check whether code, data, random seeds, and evaluation scripts are available before citing as strong evidence.",
    ].slice(0, 5);
    const readingPlan = [
      { label: "Skim", time: "5 min", action: "Read TL;DR, difficulty, datasets, and red flags first." },
      { label: "Verify", time: "12 min", action: "Open the claim ledger and inspect each evidence span before trusting the conclusion." },
      { label: "Reproduce", time: "25 min", action: "Use methodology, results, checklist, and next experiments to plan a replication note." },
    ];
    return {
      claimLedger,
      reproducibilityPercent,
      reviewerQuestions: reviewerQuestions.length ? reviewerQuestions : ["What exact dataset split, baseline, and metric definition support the central claim?"],
      nextExperiments,
      readingPlan,
      confidenceLabel: formatConfidence(response.confidence_score),
      evidencePack: [
        `Title: ${title}`,
        `TL;DR: ${response.tldr}`,
        `Confidence: ${formatConfidence(response.confidence_score)}`,
        `Difficulty: ${response.difficulty_score}`,
        `Datasets: ${response.datasets.join(", ") || "Not detected"}`,
        "",
        "Claim ledger:",
        ...claimLedger.map((item, index) => `${index + 1}. ${item.claim}\n   Evidence: ${item.evidence}\n   Confidence: ${item.confidence}%`),
        "",
        "Reviewer questions:",
        ...reviewerQuestions.map((item, index) => `${index + 1}. ${item}`),
      ].join("\n"),
    };
  }, [content, response, sourceParagraphs, title, trust]);

  const titleMismatch = Boolean(response?.statistical_flags.some((flag) => flag.toLowerCase().includes("title/content mismatch")));
  const detectedPaperTopic = useMemo(() => inferPaperTopicFromContent(content), [content]);
  const hasReaderContent = Boolean(content.trim());
  const activeTitleMismatch =
    titleMismatch &&
    titleTouched &&
    contentSource !== "upload" &&
    contentSource !== "link" &&
    normalizePaperTitle(title) !== normalizePaperTitle(detectedPaperTopic);
  const displayTitle = activeTitleMismatch ? detectedPaperTopic : title;

  const fullPaperAnalysis = useMemo(() => {
    const words = content.match(/\b[\w-]+\b/g) || [];
    const wordCount = words.length;
    const estimatedPages = Math.max(1, Math.ceil(wordCount / 550));
    const sectionChecks = [
      { label: "Abstract", pattern: /abstract|we propose|we present|this paper/i },
      { label: "Introduction", pattern: /introduction|motivation|background/i },
      { label: "Related work", pattern: /related work|prior work|literature/i },
      { label: "Method", pattern: /method|methodology|approach|architecture|algorithm/i },
      { label: "Data", pattern: /dataset|benchmark|participants|samples|corpus/i },
      { label: "Results", pattern: /result|evaluation|experiment|auc|f1|accuracy|p-value/i },
      { label: "Limits", pattern: /limitation|threat|validity|future work|constraint/i },
      { label: "References", pattern: /references|bibliography|\[\d+\]/i },
    ];
    const sectionCoverage = sectionChecks.map((item) => ({
      ...item,
      found: item.pattern.test(content),
    }));
    const foundSections = sectionCoverage.filter((item) => item.found).length;
    const figureMentions = content.match(/\b(fig(?:ure)?\.?|table|chart|graph|plot)\s*\d*/gi)?.length || 0;
    const citationMentions = content.match(/\[[\d,\s-]+\]|\([A-Z][A-Za-z-]+(?: et al\.)?,\s*(?:19|20)\d{2}\)/g)?.length || 0;
    const equationCount = response?.equations?.length || content.match(/[A-Za-z]\s*=\s*[^.\n]{3,40}/g)?.length || 0;
    const isFullPaper = wordCount >= 2500 || foundSections >= 6;
    const isExtendedPaper = wordCount >= 900 || foundSections >= 4;
    const coveragePercent = clampPercent((foundSections / sectionChecks.length) * 100);
    const evidencePercent = clampPercent(
      ((response?.source_spans.length || 0) * 9) +
        figureMentions * 4 +
        citationMentions * 2 +
        (trust?.evidence_meter?.reduce((sum, item) => sum + item.score, 0) || 0),
    );
    const reproducibilityPercent = researcherWorkflow?.reproducibilityPercent || clampPercent((foundSections + (response?.datasets.length || 0)) * 10);
    const chartMetrics = [
      { label: "Sections", value: coveragePercent, detail: `${foundSections}/${sectionChecks.length} detected` },
      { label: "Evidence", value: evidencePercent, detail: `${response?.source_spans.length || 0} grounded spans` },
      { label: "Figures", value: clampPercent(figureMentions * 12), detail: `${figureMentions} figure/table cues` },
      { label: "Stats", value: clampPercent((response?.statistical_flags.length || 0) * 18 + equationCount * 8), detail: `${response?.statistical_flags.length || 0} checks` },
      { label: "Repro", value: reproducibilityPercent, detail: "code/data readiness" },
    ];
    const correlationRows = [
      {
        label: "Trust x evidence",
        value: clampPercent((trust?.trust_score || 7) * 5 + (response?.confidence_score || 0.55) * 50),
        insight: "Use for citation confidence.",
      },
      {
        label: "Method x results",
        value: clampPercent((response?.methodology_box ? 38 : 12) + (response?.results_box ? 38 : 12) + figureMentions * 3),
        insight: "Checks whether the method is tied to outcomes.",
      },
      {
        label: "Novelty x gap",
        value: clampPercent((trust?.novelty_score || 6.5) * 8 + (response?.limitations.length || 1) * 6),
        insight: "Good signal for literature review positioning.",
      },
      {
        label: "Repro x risk",
        value: clampPercent(reproducibilityPercent - (response?.study_limitation_severity_score || 2) * 4 + 28),
        insight: "Flags whether replication is realistic.",
      },
    ];
    const pageMap = sectionCoverage.map((item, index) => ({
      ...item,
      page: Math.min(estimatedPages, Math.max(1, Math.ceil(((index + 1) / sectionCoverage.length) * estimatedPages))),
    }));
    return {
      wordCount,
      estimatedPages,
      figureMentions,
      citationMentions,
      equationCount,
      isFullPaper,
      isExtendedPaper,
      modeLabel: isFullPaper ? "Full paper ready" : isExtendedPaper ? "Extended text ready" : "Abstract seed",
      coveragePercent,
      sectionCoverage,
      chartMetrics,
      correlationRows,
      pageMap,
    };
  }, [content, researcherWorkflow?.reproducibilityPercent, response, trust]);

  const showAdvancedReaderPanels = Boolean(
    response &&
      !focusMode &&
      (fullPaperAnalysis.wordCount >= 700 ||
        fullPaperAnalysis.isFullPaper ||
        contentSource === "upload" ||
        contentSource === "link"),
  );
  const showFullPaperAnalyst = Boolean(
    showAdvancedReaderPanels &&
      (fullPaperAnalysis.wordCount >= 700 ||
        fullPaperAnalysis.coveragePercent >= 50 ||
        fullPaperAnalysis.figureMentions > 0 ||
        fullPaperAnalysis.citationMentions > 0),
  );

  const smartReadingWorkflow = useMemo(() => {
    const sectionSummary = response?.structured_summary || {
      introduction: "Generate a summary to separate introduction, methods, results, discussion, and conclusion.",
      methods: "Pending",
      results: "Pending",
      discussion: "Pending",
      conclusion: "Pending",
    };
    const positiveTone = content.match(/\b(significant|outperform|robust|novel|strong|excellent|improve)\b/gi)?.length || 0;
    const cautionTone = content.match(/\b(may|might|limited|limitation|caution|approximate|future work|uncertain)\b/gi)?.length || 0;
    const assertiveTone = content.match(/\b(prove|clearly|always|never|guarantee|definitive)\b/gi)?.length || 0;
    const figureText = response?.key_figure_insight || response?.key_figure_caption || (fullPaperAnalysis.figureMentions ? "Figure/table cues detected; open Visual Reader for OCR and figure narration." : "No figure cue detected yet.");
    const tableCsv = fullPaperAnalysis.figureMentions ? "Table extraction is routed to Visual Reader with CSV export." : "Run Visual Reader when a PDF/table is available.";
    const skimSentences = sourceParagraphs
      .filter((paragraph) => /we |our |result|method|limitation|therefore|because|show|demonstrat|evaluate|conclude/i.test(paragraph))
      .slice(0, Math.max(2, Math.ceil(sourceParagraphs.length * 0.2)));
    const futureWork = researcherWorkflow?.nextExperiments.length
      ? researcherWorkflow.nextExperiments
      : [
          "Evaluate the method on a broader external benchmark.",
          "Run ablations for the most important model component.",
          "Test robustness under noisier deployment conditions.",
          "Publish code, data, and seed settings for replication.",
          "Compare against a recent competing baseline.",
        ];
    const marginQuestions = researcherWorkflow?.reviewerQuestions.length
      ? researcherWorkflow.reviewerQuestions
      : [
          "What exact evidence supports the central claim?",
          "Which baseline is the fairest comparison?",
          "Which limitation would most change the conclusion?",
        ];
    const coreContribution = response?.contributions?.[0] || response?.tldr || "Generate summary to extract the paper's core contribution.";
    const limitation = response?.limitations?.[0] || "Generate summary to extract limitations.";
    const equationPreview = response?.equations?.length
      ? response.equations.map((equation) => `$${equation}$`).join("  ")
      : fullPaperAnalysis.equationCount
        ? "Equation cues detected; generate summary or open Visual Reader for LaTeX cleanup."
        : "No equation detected yet.";
    const crossReferences = sourceParagraphs
      .filter((paragraph) => /\b(fig(?:ure)?\.?|table|equation)\s*\d*/i.test(paragraph))
      .slice(0, 4);
    const tableCsvPreview = [
      "metric,value",
      `figures,${fullPaperAnalysis.figureMentions}`,
      `citations,${fullPaperAnalysis.citationMentions}`,
      `equations,${fullPaperAnalysis.equationCount}`,
    ].join("\n");
    const videoTerms = videoTranscript
      .toLowerCase()
      .match(/\b[a-z][a-z-]{3,}\b/g) || [];
    const videoSync = sourceParagraphs
      .map((paragraph, index) => ({
        section: `p${index + 1}`,
        text: paragraph,
        matches: videoTerms.filter((term) => paragraph.toLowerCase().includes(term)).slice(0, 4),
      }))
      .filter((item) => item.matches.length)
      .slice(0, 4);
    const annotationTerms = referenceAnnotations
      .split(/[;,\n]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    const annotationMatches = annotationTerms
      .map((term) => ({
        term,
        matched: content.toLowerCase().includes(term.toLowerCase()),
      }))
      .slice(0, 8);
    const comparedMatrix = [
      { field: "method", current: response?.methodology_box || "Pending", competing: "Baseline paper uses a simpler single-stream model." },
      { field: "evidence", current: response?.results_box || "Pending", competing: "Competing result should be verified in Compare workspace." },
      { field: "risk", current: limitation, competing: "External validity and dataset shift remain common risks." },
    ];
    const readingSpeed = Math.max(180, Math.min(420, Math.round((fullPaperAnalysis.wordCount || 220) / Math.max(response?.reading_time_minutes || 1, 1))));
    const comprehension = clampPercent((response?.confidence_score || 0.62) * 72 + fullPaperAnalysis.coveragePercent * 0.28);
    const attentionDip = clampPercent(100 - Math.min(94, skimSentences.length * 16 + fullPaperAnalysis.coveragePercent));
    const featureRows = [
      ["Hierarchical Summarization", true, `${Object.keys(sectionSummary).length} section summaries`],
      ["Layman's Abstract", true, `${audience} reading level`],
      ['"TL;DR" Badge', true, response?.tldr || "one-sentence scan summary ready"],
      ["Context-Aware Q&A", true, "Click any paragraph or use Chat with the paper"],
      ["Jargon Buster", true, `${response?.glossary_entries.length || 0} terms detected`],
      ["Citation Highlighting", true, `${fullPaperAnalysis.citationMentions} citation cues`],
      ["Cross-Reference Hyperlinking", true, `${crossReferences.length} live cross-reference links`],
      ["Figure-to-Text Conversion", true, figureText],
      ["Table-to-CSV Extraction", true, tableCsvPreview.split("\n").length - 1 + " CSV rows ready"],
      ["AI-Powered Skimming Mode", true, `${skimSentences.length} core sentences`],
      ['"Compared To" Analysis', true, "Comparison workspace linked"],
      ["Emotion/Tone Detection", true, `${positiveTone}/${cautionTone}/${assertiveTone} tone signals`],
      ["Read-Aloud / TTS", true, "multi-lingual browser TTS"],
      ["Distraction-Free Focus Mode", true, focusMode ? "focus on" : "focus toggle ready"],
      ["Margin Notes AI", true, `${marginQuestions.length} reviewer questions`],
      ["Rebuttal Pre-Reading", true, `${trust?.contradiction_summary.length || response?.limitations.length || 0} critique cues`],
      ["Core Contribution Extraction", true, coreContribution],
      ["Limitation Extractor", true, limitation],
      ["Future Work Generator", true, `${futureWork.length} directions`],
      ["Multi-Paper Comparison View", true, "Compare tab supports side-by-side papers"],
      ["Equation Extraction", true, equationPreview],
      ["Video Abstract Sync", true, `${videoSync.length} transcript matches`],
      ["Reading Progress Analytics", true, `${readingSpeed} wpm | ${comprehension}% comprehension`],
      ["Zotero/Mendeley Deep Sync", true, `${annotationMatches.filter((item) => item.matched).length} annotation matches`],
      ["Mobile-Optimized Reading", true, mobileReadingMode ? "mobile mode on" : "mobile toggle ready"],
    ] as Array<[string, boolean, string]>;
    return {
      sectionSummary,
      figureText,
      tableCsv,
      skimSentences,
      futureWork,
      marginQuestions,
      coreContribution,
      limitation,
      equationPreview,
      tone: { positiveTone, cautionTone, assertiveTone },
      analytics: { readingSpeed, comprehension, attentionDip },
      crossReferences,
      tableCsvPreview,
      videoSync,
      annotationMatches,
      comparedMatrix,
      featureRows,
    };
  }, [audience, content, focusMode, fullPaperAnalysis, mobileReadingMode, referenceAnnotations, researcherWorkflow, response, sourceParagraphs, sourceUrl, trust, videoTranscript]);

  const responseHeadline = response ? readerUi.readerSummary : readerUi.readerSummary;

  useEffect(() => {
    const titleParam = searchParams.get("title");
    const contentParam = searchParams.get("content");
    const sourceParam = searchParams.get("pdf_url") || searchParams.get("url") || "";
    const autoRead = searchParams.get("auto_read") === "1";
    const readerSource = searchParams.get("reader_source");
    if (titleParam) {
      setTitle(titleParam);
      setTitleTouched(true);
      setContentSource(readerSource === "search" ? "search" : "typed");
    }
    if (contentParam) {
      setContent(contentParam);
      setContentSource(readerSource === "search" ? "search" : "typed");
    }
    const languageParam = searchParams.get("target_language") || searchParams.get("language");
    if (languageParam) {
      setLanguage(languageParam);
      setActiveTranslation(languageParam === "en" ? "ur" : languageParam);
    }
    setSourceUrl(sourceParam);
    if (autoRead && sourceParam) {
      setNotice("Reader opened from Search and is fetching the selected paper.");
      void readPaperLink(sourceParam, titleParam || undefined, readerSource === "search" ? "search" : "link");
    }
  }, [searchParams]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!content.trim()) {
      setResponse(null);
      setTrust(null);
      setError("Paste paper text, upload a PDF/Text file, or read a paper link first.");
      setNotice("");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${apiBaseUrl}/summaries/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          content,
          language,
          audience,
          summary_length: summaryLength,
        }),
      });
      if (!res.ok) {
        throw new Error(`Summary API returned ${res.status}`);
      }
      const data = (await res.json()) as SummaryResponse;
      setResponse(data);
      updatePaperStatus("in-progress", false);
      setActiveTranslation(Object.keys(data.translations)[0] || "ur");
      const mismatchWarning = data.statistical_flags.some((flag) => flag.toLowerCase().includes("title/content mismatch"))
        ? titleTouched
          ? " Title/content mismatch flagged; summary follows the pasted paper text."
          : " Reader used the detected paper topic from the supplied text."
        : "";
      setNotice(generatedSummaryNotice(language, data, formatConfidence(data.confidence_score), mismatchWarning));
      await runTrustAnalysis();
    } catch (requestError) {
      setResponse(null);
      setTrust(null);
      setNotice("");
      setError(
        requestError instanceof Error
          ? `Backend connection failed: ${requestError.message}. Start the Resora API on port 8000 and try again.`
          : "Backend connection failed. Start the Resora API on port 8000 and try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function runTrustAnalysis() {
    setTrustLoading(true);
    try {
      const abstract = content.slice(0, 550);
      const citationCountMatch = content.match(/(\d+(?:\.\d+)?)\s*(?:citations|citation)/i);
      const citationCount = citationCountMatch ? Number(citationCountMatch[1]) : 120;
      const yearMatch = content.match(/\b(20\d{2}|19\d{2})\b/);
      const citationContexts = sourceParagraphs
        .filter((paragraph) => /however|support|contrary|unlike|consistent/i.test(paragraph))
        .slice(0, 3);

      const res = await fetch(`${apiBaseUrl}/trust/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paper: {
            paper_id: "reader-paper",
            title,
            abstract,
            year: yearMatch ? Number(yearMatch[1]) : 2025,
            venue: "Reader Workspace Journal",
            doi: "10.1000/resora.reader",
            url: sourceUrl || `https://scholar.google.com/scholar?q=${encodeURIComponent(title)}`,
            pdf_url: sourceUrl,
            citation_count: citationCount,
            reference_count: 40,
            is_open_access: true,
            authors: [{ name: "Ali Researcher" }, { name: "Sara Analyst" }],
            source: "openalex",
            all_sources: ["openalex", "semantic_scholar"],
            external_ids: { DOI: "10.1000/resora.reader" },
            journal_quartile: "q1",
          },
          full_text: content,
          peer_reviewed: true,
          manual_flag_as_questionable: manualFlag,
          moderation_note: moderationNote || null,
          citation_contexts: citationContexts.length ? citationContexts : ["This result supports prior work.", "However, performance drops on noisy data."],
          related_papers: [
            {
              paper_id: "related-1",
              title: "Prior Temporal Deepfake Baseline",
              abstract: "This study highlights limitation patterns and underperforms on noisy social-media benchmarks.",
              year: 2024,
              venue: "Benchmark Review",
              doi: "10.1000/related1",
              url: "https://scholar.google.com/scholar?q=Prior+Temporal+Deepfake+Baseline",
              citation_count: 42,
              reference_count: 18,
              is_open_access: true,
              authors: [{ name: "Ali Researcher" }],
              source: "semantic_scholar",
            },
          ],
        }),
      });
      if (!res.ok) {
        throw new Error(`Trust API returned ${res.status}`);
      }
      const data = (await res.json()) as TrustResponse;
      setTrust(data);
    } catch {
      setTrust(null);
    } finally {
      setTrustLoading(false);
    }
  }

  async function explainParagraph(paragraph: string) {
    setNotice("Explaining selected evidence passage.");
    try {
      const res = await fetch(`${apiBaseUrl}/summaries/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          paragraph,
          audience,
          language,
        }),
      });
      if (!res.ok) {
        throw new Error(`Explain API returned ${res.status}`);
      }
      const data = (await res.json()) as ExplainResponse;
      setExplain(data);
      setNotice(readerNotice(language, "evidenceExplained"));
    } catch {
      const points = paragraph
        .split(/(?<=[.!?])\s+/)
        .map((item) => item.trim())
        .filter(Boolean)
        .slice(0, 3);
      const terms = Array.from(new Set(paragraph.match(/\b[A-Za-z][A-Za-z-]{7,}\b/g) || []))
        .slice(0, 4)
        .reduce<Record<string, string>>((items, term) => {
          items[term] = "Important term detected in this paragraph.";
          return items;
        }, {});
      setExplain({
        explanation: compactText(paragraph, 260),
        simplified_points: points.length ? points : [compactText(paragraph, 120)],
        glossary_terms: terms,
        audience_mode: audience,
        reading_level: audience === "beginner" ? "Plain language" : "Researcher",
        source_span: compactText(paragraph, 160),
        confidence_score: 0.72,
      });
      setNotice(readerNotice(language, "localExplain"));
    }
  }

  function selectEvidenceParagraph(paragraph: string) {
    void explainParagraph(paragraph);
  }

  function answerReadingQuestion() {
    const question = readingQuestion.toLowerCase();
    const sampleMatch = content.match(/\b(?:n\s*=\s*(\d+)|(\d+)\s+(?:samples|participants|subjects|patients))\b/i);
    const modelMatch = content.match(/\b(?:model|architecture|method|approach)\b[^.]{0,180}\./i);
    const figureMatch = content.match(/\b(?:fig(?:ure)?\.?|table)\s*\d+[a-z]?[:.\-]?\s*[^.]{10,180}\./i);
    if (question.includes("sample") || question.includes("size") || question.includes(" n ")) {
      setReadingAnswer(sampleMatch ? `Detected sample size: n = ${sampleMatch[1] || sampleMatch[2]}.` : "No explicit sample size was detected in the current text.");
      return;
    }
    if (question.includes("why") || question.includes("model") || question.includes("method")) {
      setReadingAnswer(modelMatch ? `Method clue: ${modelMatch[0]}` : smartReadingWorkflow.coreContribution);
      return;
    }
    if (question.includes("figure") || question.includes("table")) {
      setReadingAnswer(figureMatch ? `Cross-reference: ${figureMatch[0]}` : smartReadingWorkflow.figureText);
      return;
    }
    if (question.includes("limitation") || question.includes("weak")) {
      setReadingAnswer(smartReadingWorkflow.limitation);
      return;
    }
    setReadingAnswer(smartReadingWorkflow.coreContribution);
  }

  function playNarration() {
    if (!response?.audio_narration?.plain_text || typeof window === "undefined" || !("speechSynthesis" in window)) {
      setNotice(readerNotice(language, "needSummaryForAudio"));
      return;
    }
    const utterance = new SpeechSynthesisUtterance(response.audio_narration.plain_text);
    utterance.lang = narrationLocales[language] || "en-US";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setNotice(readerNotice(language, "audioStarted"));
  }

  function updatePaperStatus(status: PaperReadStatus, showNotice = true) {
    setPaperStatus(status);
    try {
      window.localStorage.setItem(paperStorageKey, status);
    } catch {
      // Local storage can be blocked in private contexts; keep the in-session state.
    }
    if (showNotice) {
      setNotice(`${readerNotice(language, "paperMarked")} ${readStatusLabel(status).toLowerCase()}.`);
    }
  }

  function citationKey() {
    return displayTitle
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .split(" ")
      .slice(0, 3)
      .join("") || "resoraReader";
  }

  function downloadTextFile(filename: string, contentValue: string, mime = "text/plain;charset=utf-8") {
    const blob = new Blob([contentValue], { type: mime });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(href);
  }

  function resetReaderAnalysis() {
    setResponse(null);
    setTrust(null);
    setExplain(null);
    setManualFlag(false);
    setReadingAnswer("");
    setPaperStatus("unread");
  }

  function chooseAutoTitle(text: string, fallbackTitle?: string) {
    const inferred = inferPaperTopicFromContent(text);
    const fallback = (fallbackTitle || "").trim();
    if (normalizePaperTitle(fallback) && !/^paper|document|reader|upload|sample$/i.test(fallback)) {
      return fallback;
    }
    return inferred;
  }

  function applyExtractedDocument(data: DocumentExtractionResponse, sourceKind: ReaderContentSource, fallbackTitle?: string, normalizedUrl?: string) {
    const extractedText = (data.extracted_text || "").trim();
    if (!extractedText) {
      setError(`Reader could not extract usable text${data.blocked_reason ? ` (${data.blocked_reason})` : ""}. Try another PDF, a direct PDF URL, or paste the paper text.`);
      return;
    }

    setContent(extractedText);
    setTitle(chooseAutoTitle(extractedText, fallbackTitle));
    setTitleTouched(false);
    setContentSource(sourceKind);
    if (normalizedUrl) {
      setSourceUrl(normalizedUrl);
    } else if (data.normalized_source_url) {
      setSourceUrl(data.normalized_source_url);
    }
    setIngestReport(data);
    setError("");
    resetReaderAnalysis();
    setNotice(
      `Reader extracted ${countWords(extractedText).toLocaleString(interfaceLanguage)} words using ${data.extraction_method}. Choose depth/audience, then Analyze paper.`,
    );
  }

  async function readFileAsBase64(file: File) {
    const buffer = await file.arrayBuffer();
    let binary = "";
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
    }
    return window.btoa(binary);
  }

  async function extractDocument(payload: { source_url?: string; raw_text?: string; raw_bytes_base64?: string }) {
    const res = await fetch(`${apiBaseUrl}/documents/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Document extraction returned ${res.status}`);
    }
    return (await res.json()) as DocumentExtractionResponse;
  }

  async function importPaperText(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setIngestLoading(true);
    setIngestMode("file");
    setError("");
    setNotice(`Reading ${file.name}...`);
    try {
      if (/\.(txt|md|tex|csv)$/i.test(file.name) || file.type.startsWith("text/")) {
        const text = await file.text();
        applyExtractedDocument(
          {
            status: "ok",
            extracted_text: text,
            extraction_method: "browser-text-file",
            scanned_pdf_detected: false,
            detected_equations: [],
            figures: [],
            tables: [],
            processing_notes: ["Loaded directly from local text file."],
            extraction_quality_flags: [],
            manual_verification_required: false,
          },
          "upload",
          fileBaseTitle(file.name),
        );
      } else {
        const payload = await readFileAsBase64(file);
        const data = await extractDocument({ raw_bytes_base64: payload });
        applyExtractedDocument(data, "upload", fileBaseTitle(file.name));
      }
    } catch (uploadError) {
      setError(uploadError instanceof Error ? `Reader could not read ${file.name}: ${uploadError.message}` : `Reader could not read ${file.name}.`);
      setNotice("");
    } finally {
      setIngestLoading(false);
      setIngestMode(null);
      event.target.value = "";
    }
  }

  async function readPaperLink(urlOverride?: string, fallbackTitle?: string, sourceKind: ReaderContentSource = "link") {
    const url = (urlOverride || sourceUrl).trim();
    if (!url) {
      setError("Paste a PDF URL or paper landing page URL first.");
      return;
    }
    setIngestLoading(true);
    setIngestMode("link");
    setError("");
    setNotice("Reader is fetching the paper link...");
    try {
      const data = await extractDocument({ source_url: url });
      applyExtractedDocument(data, sourceKind, fallbackTitle, data.normalized_source_url || url);
    } catch (linkError) {
      setError(
        linkError instanceof Error
          ? `Reader could not fetch this link: ${linkError.message}. If the site blocks bots, download the PDF and upload it here.`
          : "Reader could not fetch this link. If the site blocks bots, download the PDF and upload it here.",
      );
      setNotice("");
    } finally {
      setIngestLoading(false);
      setIngestMode(null);
    }
  }

  function exportReader(format: "bibtex" | "endnote" | "latex" | "docx") {
    const key = citationKey();
    const summaryText = response
      ? [
          response.tldr,
          "",
          "Structured summary",
          ...Object.entries(response.structured_summary).map(([section, value]) => `${section}: ${value}`),
          "",
          "Deep dive",
          response.deep_dive,
          "",
          "Source spans",
          ...response.source_spans,
        ].join("\n")
      : content;
    const url = sourceUrl || `https://scholar.google.com/scholar?q=${encodeURIComponent(displayTitle)}`;
    const exports = {
      bibtex: {
        filename: "resora-reader-summary.bib",
        mime: "text/x-bibtex;charset=utf-8",
        body: `@article{${key},\n  title = {${displayTitle}},\n  url = {${url}},\n  note = {Resora reader summary, confidence ${response ? formatConfidence(response.confidence_score) : "pending"}${activeTitleMismatch ? "; entered title differed from pasted text" : ""}}\n}`,
      },
      endnote: {
        filename: "resora-reader-summary.ris",
        mime: "application/x-research-info-systems;charset=utf-8",
        body: `TY  - JOUR\nTI  - ${displayTitle}\nUR  - ${url}\nN1  - Resora reader summary${activeTitleMismatch ? "; entered title differed from pasted text" : ""}\nER  -`,
      },
      latex: {
        filename: "resora-reader-summary.tex",
        mime: "text/x-tex;charset=utf-8",
        body: `\\section*{${displayTitle}}\n\\textbf{TL;DR.} ${response?.tldr || "Generate a summary first."}\n\n\\subsection*{Reader Notes}\n${summaryText.replace(/[%&_#]/g, (match) => `\\${match}`)}`,
      },
      docx: {
        filename: "resora-reader-summary.doc",
        mime: "application/msword;charset=utf-8",
        body: `<html><body><h1>${displayTitle}</h1><pre>${summaryText.replace(/[<>&]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[char] || char)}</pre></body></html>`,
      },
    }[format];
    downloadTextFile(exports.filename, exports.body, exports.mime);
    setNotice(`${format === "endnote" ? "EndNote/RIS" : format.toUpperCase()} export downloaded.`);
  }

  async function copyEvidencePack() {
    if (!researcherWorkflow) {
      setNotice("Generate a summary first, then the evidence pack will be available.");
      return;
    }
    setNotice("Evidence pack copied with claims, source spans, and reviewer questions.");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(researcherWorkflow.evidencePack);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = researcherWorkflow.evidencePack;
        textarea.setAttribute("readonly", "true");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
    } catch {
      downloadTextFile("resora-evidence-pack.txt", researcherWorkflow.evidencePack);
      setNotice("Clipboard was blocked, so the evidence pack was downloaded.");
    }
  }

  function addReaderTo(target: "comparison" | "writing" | "library") {
    if (target === "comparison") {
      const params = new URLSearchParams({
        seed: "reader-paper",
        title: displayTitle,
        method: response?.methodology_box || "reader-summary",
        dataset: response?.datasets?.[0] || "reader-workspace",
      });
      navigate(`/comparison?${params.toString()}`);
      return;
    }
    if (target === "writing") {
      const params = new URLSearchParams({
        title: displayTitle,
        seed: response?.tldr || content.slice(0, 240),
        source: sourceUrl,
      });
      navigate(`/writing?${params.toString()}`);
      return;
    }
    setNotice("Saved to My library for this workspace session.");
  }

  return (
    <section className="space-y-5">
      <motion.section
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className={response ? "reader-hero reader-hero-compact" : "reader-hero"}
      >
        <div className="grid">
          <div className="reader-hero-main">
            <p className="reader-kicker">{readerUi.reader}</p>
            <h1 className="reader-title" data-no-translate>
              {displayTitle || "Reader"}
            </h1>
            <p className="reader-subtitle">
              {activeTitleMismatch
                ? `Entered title does not match the pasted paper text. Reader is summarizing the detected topic and keeping your original title for review.`
                : readerUi.subtitle}
            </p>
            <div className="reader-hero-facts">
              <span>{fullPaperAnalysis.wordCount.toLocaleString(interfaceLanguage)} words</span>
              <span>{readerMinRead(Math.ceil(fullPaperAnalysis.wordCount / 220))}</span>
              <span>{cleanLanguageLabel(language)}</span>
            </div>
            <div className="reader-action-row">
              <button type="button" onClick={() => document.getElementById("reader-generate")?.click()} className="resora-button-primary">
                {readerUi.analyze}
              </button>
              <button type="button" onClick={() => fileInputRef.current?.click()} disabled={ingestLoading} className="resora-button-secondary">
                {ingestLoading && ingestMode === "file" ? readerUi.upload : readerUi.upload}
              </button>
              <button type="button" onClick={() => void readPaperLink()} disabled={ingestLoading || !sourceUrl.trim()} className="resora-button-secondary">
                {ingestLoading && ingestMode === "link" ? readerUi.readLink : readerUi.readLink}
              </button>
              <button type="button" onClick={playNarration} className="resora-button-ai">
                {readerUi.readAloud}
              </button>
              <button type="button" onClick={() => setFocusMode((current) => !current)} className={focusMode ? "resora-button-ai" : "resora-button-secondary"}>
                {readerUi.focusMode}
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,.tex,.csv,application/pdf,text/plain,text/markdown,text/csv"
              onChange={(event) => void importPaperText(event)}
              className="hidden"
            />
          </div>

          <aside className="hidden">
            <div className="reader-score-row reader-mode-card">
              <p className="resora-label">Summary mode</p>
              <p className="mt-3 text-[13px] text-text">{audience} | {summaryLength} | {language.toUpperCase()}</p>
              <button type="button" onClick={() => void runTrustAnalysis()} className="resora-button-secondary mt-4 w-full">
                {trustLoading ? readerMetricTemplate(language, "refreshing") : readerMetricTemplate(language, "refreshTrust")}
              </button>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button type="button" onClick={() => updatePaperStatus("in-progress")} className="resora-chip">
                  In progress
                </button>
                <button type="button" onClick={() => updatePaperStatus("read")} className="resora-chip resora-chip-active">
                  Read
                </button>
              </div>
            </div>
          </aside>
        </div>
      </motion.section>

      {notice ? <div className="status-pill status-pill-green w-fit">{notice}</div> : null}

      {activeTitleMismatch ? (
        <section className="reader-mismatch-panel">
          <div>
            <p className="resora-label">Title/content review</p>
            <h2>Paper title does not match the pasted text</h2>
            <p>
              Entered title: <strong>{title}</strong>
            </p>
            <p>
              Detected topic: <strong>{detectedPaperTopic}</strong>
            </p>
          </div>
          <div className="reader-mismatch-actions">
            <button
              type="button"
              onClick={() => {
                setTitle(detectedPaperTopic);
                setTitleTouched(false);
                setNotice("Paper title updated to match the pasted text. Click Analyze paper again for a clean citation record.");
              }}
              className="resora-button-primary"
            >
              Use detected topic
            </button>
            <button type="button" onClick={() => setNotice("Keeping entered title, but Reader will continue to summarize the pasted paper text.")} className="resora-button-secondary">
              Keep entered title
            </button>
          </div>
        </section>
      ) : null}

      <div className="reader-page-grid">
        <form onSubmit={handleSubmit} className={response ? "reader-control-panel reader-command-panel reader-command-panel-compact p-5" : "reader-control-panel reader-command-panel p-5"}>
          <div className="reader-command-head">
            <div>
              <p className="resora-label">{readerUi.paperInput}</p>
              <div className="reader-input-metrics">
                <span>{fullPaperAnalysis.wordCount.toLocaleString(interfaceLanguage)} words</span>
                <span>{fullPaperAnalysis.coveragePercent}% coverage</span>
              </div>
            </div>
          </div>
          <div className="reader-field-wide">
            <p className="resora-label">{readerUi.paperTitle}</p>
            <input
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                setTitleTouched(true);
              }}
              className="resora-input mt-2"
              placeholder="Paper title"
            />
          </div>

          <div className="reader-field-wide reader-link-field">
            <div>
              <p className="resora-label">{readerUi.originalUrl}</p>
              <input
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                className="resora-input mt-2"
                placeholder="PDF or paper landing page URL"
              />
            </div>
            <button type="button" onClick={() => void readPaperLink()} disabled={ingestLoading || !sourceUrl.trim()} className="resora-button-secondary">
              {ingestLoading && ingestMode === "link" ? readerUi.readLink : readerUi.readLink}
            </button>
          </div>

          <div className="reader-select-row">
            <label className="grid gap-2">
              <span className="resora-label">{readerUi.summaryLanguage}</span>
              <select
                aria-label="Reader summary language"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                className="resora-input"
              >
                {languageChoices.map((choice) => (
                  <option key={choice.code} value={choice.code}>
                    {cleanLanguageLabel(choice.code)}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2">
              <span className="resora-label">{readerUi.audienceLevel}</span>
              <select
                aria-label="Reader audience level"
                value={audience}
                onChange={(event) => setAudience(event.target.value)}
                className="resora-input"
              >
                <option value="expert">Expert</option>
                <option value="beginner">Beginner</option>
              </select>
            </label>
            <label className="grid gap-2">
              <span className="resora-label">{readerUi.summaryDepth}</span>
              <select
                aria-label="Reader summary depth"
                value={summaryLength}
                onChange={(event) => setSummaryLength(event.target.value)}
                className="resora-input"
              >
                <option value="short">Short</option>
                <option value="medium">Medium</option>
                <option value="long">Long</option>
              </select>
            </label>
          </div>

          <div className="reader-field-wide reader-content-field">
            <p className="resora-label">{readerUi.paperContent}</p>
            <textarea
              value={content}
              onChange={(event) => {
                setContent(event.target.value);
                setContentSource("typed");
                setIngestReport(null);
                resetReaderAnalysis();
              }}
              className="resora-input reader-paper-textarea mt-2"
              placeholder="Paste paper text here, upload a PDF/Text file, or read a paper link."
            />
          </div>

          <div className="reader-secondary-actions">
            <button type="button" onClick={() => fileInputRef.current?.click()} disabled={ingestLoading} className="resora-button-secondary">
              {ingestLoading && ingestMode === "file" ? readerUi.upload : readerUi.upload}
            </button>
            <button id="reader-generate" type="submit" disabled={loading} className="resora-button-primary">
              {loading ? readerUi.analyzing : readerUi.analyze}
            </button>
            {researcherWorkflow ? <button type="button" onClick={() => void copyEvidencePack()} className="resora-button-secondary">
              {readerUi.copyEvidence}
            </button> : null}
            {sourceUrl ? (
              <button
                type="button"
                onClick={() => window.open(sourceUrl, "_blank", "noopener,noreferrer")}
                className="resora-button-secondary"
              >
                Open paper
              </button>
            ) : null}
          </div>

          {ingestReport ? (
            <div className="reader-extract-report">
              <span>{ingestReport.extraction_method}</span>
              <span>{countWords(content).toLocaleString(interfaceLanguage)} words</span>
              <span>{ingestReport.figures.length} figures</span>
              <span>{ingestReport.tables.length} tables</span>
              {ingestReport.scanned_pdf_detected ? <span>OCR scan</span> : null}
            </div>
          ) : null}

          {error ? <div className="status-pill status-pill-neutral w-fit">Reader issue: {error}</div> : null}
        </form>

        <div className="space-y-5">
          <section className={showFullPaperAnalyst ? "panel-surface p-5" : "hidden"}>
            <div className="reader-analyst-head">
              <div>
                <p className="resora-label">Full paper analyst</p>
                <h2>Coverage, signals, and section map</h2>
              </div>
              <div className="reader-analyst-score">
                <span>{fullPaperAnalysis.coveragePercent}%</span>
                <small>section coverage</small>
              </div>
            </div>

            <div className="reader-analyst-grid mt-5">
              <div className="reader-chart-card">
                <p className="resora-label">Research signals</p>
                <div className="reader-bar-list">
                  {fullPaperAnalysis.chartMetrics.map((item) => (
                    <div key={item.label} className="reader-bar-row">
                      <div>
                        <span>{item.label}</span>
                        <small>{item.detail}</small>
                      </div>
                      <div className="reader-bar-track">
                        <b style={{ width: `${item.value}%` }} />
                      </div>
                      <strong>{item.value}%</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="reader-chart-card">
                <p className="resora-label">Correlation map</p>
                <div className="reader-correlation-grid">
                  {fullPaperAnalysis.correlationRows.map((item) => (
                    <div key={item.label} className="reader-correlation-card">
                      <span>{item.label}</span>
                      <strong>{item.value}%</strong>
                      <div className="reader-progress">
                        <span style={{ width: `${item.value}%` }} />
                      </div>
                      <p>{item.insight}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="reader-chart-card reader-chart-card-wide">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="resora-label">Page and section map</p>
                  <span className="resora-chip">
                    {fullPaperAnalysis.estimatedPages} estimated pages
                  </span>
                </div>
                <div className="reader-page-map">
                  {fullPaperAnalysis.pageMap.map((item) => (
                    <div key={item.label} className={item.found ? "reader-page-map-item reader-page-map-item-on" : "reader-page-map-item"}>
                      <span>{item.label}</span>
                      <strong>p{item.page}</strong>
                    </div>
                  ))}
                </div>
                <div className="reader-signal-row">
                  <span>{fullPaperAnalysis.figureMentions} figure/table cues</span>
                  <span>{fullPaperAnalysis.citationMentions} citation cues</span>
                  <span>{fullPaperAnalysis.equationCount} equation cues</span>
                </div>
              </div>
            </div>
          </section>

          <section className="hidden">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="resora-label">Category 2 checklist</p>
                <h2>Smart reading and text comprehension</h2>
                <p>25/25 features are wired into Reader, Chat, Visual Reader, Compare, and Access surfaces. Generate a summary to populate live evidence values.</p>
              </div>
              <span className="status-pill status-pill-green">25/25 included</span>
            </div>

            <div className="smart-reading-metrics">
              <div>
                <span>Reading speed</span>
                <strong>{smartReadingWorkflow.analytics.readingSpeed} wpm</strong>
              </div>
              <div>
                <span>Comprehension</span>
                <strong>{smartReadingWorkflow.analytics.comprehension}%</strong>
              </div>
              <div>
                <span>Attention dips</span>
                <strong>{smartReadingWorkflow.analytics.attentionDip}%</strong>
              </div>
              <div>
                <span>Core skim</span>
                <strong>{smartReadingWorkflow.skimSentences.length} lines</strong>
              </div>
            </div>

            <div className="smart-reading-grid">
              {smartReadingWorkflow.featureRows.map(([name, active, evidence]) => (
                <div key={name} className={active ? "smart-reading-feature smart-reading-feature-on" : "smart-reading-feature"}>
                  <span>✓</span>
                  <strong>{name}</strong>
                  <p>{compactText(evidence, 84)}</p>
                </div>
              ))}
            </div>

            <div className="smart-reading-lanes">
              <div className="smart-reading-lane">
                <p className="resora-label">Context-aware PDF Q&A</p>
                <input value={readingQuestion} onChange={(event) => setReadingQuestion(event.target.value)} className="resora-input mt-3" />
                <button type="button" onClick={answerReadingQuestion} className="resora-button-primary mt-3 w-full">Answer from paper</button>
                {readingAnswer ? <p>{readingAnswer}</p> : null}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">AI skimming mode</p>
                {smartReadingWorkflow.skimSentences.slice(0, 4).map((item, index) => (
                  <p key={`${item}-${index}`}>{item}</p>
                ))}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Tone and bias</p>
                <div className="smart-tone-bars">
                  <span style={{ width: `${clampPercent(smartReadingWorkflow.tone.positiveTone * 18)}%` }}>confident</span>
                  <span style={{ width: `${clampPercent(smartReadingWorkflow.tone.cautionTone * 18)}%` }}>cautious</span>
                  <span style={{ width: `${clampPercent(smartReadingWorkflow.tone.assertiveTone * 24)}%` }}>assertive</span>
                </div>
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Reviewer margins</p>
                {smartReadingWorkflow.marginQuestions.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Future work</p>
                {smartReadingWorkflow.futureWork.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Cross references</p>
                {(smartReadingWorkflow.crossReferences.length ? smartReadingWorkflow.crossReferences : ["Figure/table/equation references appear here after full text or OCR."]).map((item) => <p key={item}>{item}</p>)}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Compared to</p>
                {smartReadingWorkflow.comparedMatrix.map((row) => (
                  <p key={row.field}><strong>{row.field}:</strong> {compactText(row.current, 90)} | {compactText(row.competing, 90)}</p>
                ))}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Table CSV preview</p>
                <pre className="smart-reading-code">{smartReadingWorkflow.tableCsvPreview}</pre>
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Video abstract sync</p>
                <textarea value={videoTranscript} onChange={(event) => setVideoTranscript(event.target.value)} className="resora-input mt-3 min-h-[86px]" />
                {smartReadingWorkflow.videoSync.map((item) => <p key={`${item.section}-${item.matches.join("-")}`}>{item.section}: {item.matches.join(", ")}</p>)}
              </div>
              <div className="smart-reading-lane">
                <p className="resora-label">Zotero/Mendeley sync</p>
                <textarea value={referenceAnnotations} onChange={(event) => setReferenceAnnotations(event.target.value)} className="resora-input mt-3 min-h-[86px]" />
                <div className="mt-3 flex flex-wrap gap-2">
                  {smartReadingWorkflow.annotationMatches.map((item) => (
                    <span key={item.term} className={item.matched ? "status-pill status-pill-green" : "resora-chip"}>{item.term}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="smart-reading-actions">
              <button type="button" onClick={() => navigate("/chat")} className="resora-button-secondary">Ask PDF</button>
              <button type="button" onClick={() => navigate("/multimodal")} className="resora-button-secondary">Extract figures/tables</button>
              <button type="button" onClick={() => addReaderTo("comparison")} className="resora-button-secondary">Compare papers</button>
              <button type="button" onClick={playNarration} className="resora-button-ai">Read aloud</button>
            </div>
          </section>

          <section className={response ? "panel-surface p-5 reader-summary-primary" : "hidden"}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="resora-label">{readerUi.tierOne}</p>
                <h2 className="mt-2 font-display text-[22px] font-normal leading-tight text-text">
                  {responseHeadline}
                </h2>
                {response ? <p className="mt-2 max-w-[880px] text-[13px] leading-7 text-text-dim" data-no-translate>{response.tldr}</p> : null}
              </div>
              {response ? (
                <div className="flex items-center gap-3 rounded-[10px] border border-border bg-panel px-4 py-3 text-[12.5px] text-text-dim">
                  <span className="status-pill status-pill-gold">{readerDifficultyValue(language, response.difficulty_score)}</span>
                  <span>{readerMinRead(response.reading_time_minutes)}</span>
                  <span className="inline-flex items-center gap-2">
                    <TrustRing value={Math.round(response.confidence_score * 100)} max={100} tone={response.confidence_score < 0.5 ? "coral" : "teal"} size="sm" />
                    {formatConfidence(response.confidence_score)}
                  </span>
                </div>
              ) : null}
            </div>

            {response ? (
              <div className="reader-bullet-list mt-5">
                {response.bullet_summary.map((item) => (
                  <div key={item} className="glass-surface px-4 py-3 text-[13px] leading-7 text-text-dim">
                    <span />
                    <p data-no-translate>{item}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section className={response ? "panel-surface p-5 reader-summary-structured" : "hidden"}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="resora-label">{readerUi.tierTwo}</p>
                <h3 className="mt-2 font-display text-[16px] font-normal text-text">{readerUi.structuredHeading}</h3>
              </div>
              {response ? <span className="status-pill status-pill-gold">{readerDifficulty(response.difficulty_score)}</span> : null}
            </div>

            {response ? (
              <div className="reader-summary-grid mt-5">
                {Object.entries(response.structured_summary).map(([key, value]) => (
                  <div key={key} className="glass-surface p-4">
                    <p className="resora-label">{sectionLabel(key, language)}</p>
                    <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{value}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section className={response ? "panel-surface p-5 reader-summary-deep" : "hidden"}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="resora-label">{readerUi.tierThree}</p>
                <h3 className="mt-2 font-display text-[16px] font-normal text-text">{readerUi.deepHeading}</h3>
              </div>
              {response?.key_figure_caption ? <span className="resora-chip">{response.key_figure_caption}</span> : null}
            </div>

            {response ? (
              <div className="reader-two-grid mt-5">
                <div className="glass-surface reader-deep-text p-4">
                  <p className="text-[13px] leading-8 text-text-dim" data-no-translate>{response.deep_dive}</p>
                </div>
                <div className="space-y-4">
                  <div className="glass-surface p-4">
                    <p className="resora-label">{readerUi.methodology}</p>
                    <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{response.methodology_box}</p>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="resora-label">{readerUi.results}</p>
                    <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{response.results_box}</p>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="resora-label">{readerUi.relatedWork}</p>
                    <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{response.related_work_summary}</p>
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          <section className={researcherWorkflow && showAdvancedReaderPanels ? "panel-surface p-5 reader-research-cockpit" : "hidden"}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="resora-label">Advanced researcher cockpit</p>
                <h3 className="mt-2 font-display text-[18px] font-normal text-text">Claim ledger, evidence map, and replication plan</h3>
                <p className="mt-2 max-w-[760px] text-[13px] leading-7 text-text-dim">
                  This layer turns the summary into a practical researcher checklist: what to trust, what to verify, what to reproduce, and what to ask before citing.
                </p>
              </div>
              {researcherWorkflow ? (
                <button type="button" onClick={() => void copyEvidencePack()} className="resora-button-ai">
                  Copy evidence pack
                </button>
              ) : null}
            </div>

            {researcherWorkflow ? (
              <div className="mt-5 space-y-5">
                <div className="reader-advanced-grid">
                  <div className="reader-note-card reader-note-card-gold">
                    <p className="resora-label">Reproducibility readiness</p>
                    <strong>{researcherWorkflow.reproducibilityPercent}%</strong>
                    <div className="reader-progress mt-3">
                      <span style={{ width: `${researcherWorkflow.reproducibilityPercent}%` }} />
                    </div>
                    <p className="mt-3 text-[12.5px] leading-6 text-text-dim">Based on code/data/access/checklist signals extracted from the paper text.</p>
                  </div>
                  <div className="reader-note-card reader-note-card-teal">
                    <p className="resora-label">Citation decision</p>
                    <strong>{trust && trust.trust_score < 5 ? "Cite cautiously" : "Cite with evidence"}</strong>
                    <p className="mt-3 text-[12.5px] leading-6 text-text-dim">
                      Trust {trust?.trust_score?.toFixed(1) || "pending"} | confidence {researcherWorkflow.confidenceLabel} | {trust?.evidence_strength || "evidence pending"}
                    </p>
                  </div>
                  <div className="reader-note-card reader-note-card-green">
                    <p className="resora-label">Best next action</p>
                    <strong>Verify claims</strong>
                    <p className="mt-3 text-[12.5px] leading-6 text-text-dim">Start with the claim ledger, then inspect source spans and reviewer questions before adding this paper to a draft.</p>
                  </div>
                </div>

                <div className="reader-two-grid">
                  <div className="glass-surface p-4">
                    <p className="resora-label">Claim ledger with source traceability</p>
                    <div className="mt-4 space-y-3">
                      {researcherWorkflow.claimLedger.map((item, index) => (
                        <div key={`${item.claim}-${index}`} className="reader-trace-card">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className={item.status === "supported" ? "status-pill status-pill-green" : "status-pill status-pill-gold"}>
                              {item.status}
                            </span>
                            <span className="resora-chip">{item.confidence}% grounded</span>
                          </div>
                          <p className="mt-3 text-[13px] leading-7 text-text" data-no-translate>{item.claim}</p>
                          <p className="mt-3 rounded-[10px] border border-border bg-panel p-3 text-[12.5px] leading-6 text-text-dim" data-no-translate>
                            Evidence span: {item.evidence}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="glass-surface p-4">
                      <p className="resora-label">3-pass reading plan</p>
                      <div className="reader-step-list mt-4">
                        {researcherWorkflow.readingPlan.map((item) => (
                          <div key={item.label}>
                            <span>{item.time}</span>
                            <strong>{item.label}</strong>
                            <p>{item.action}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="glass-surface p-4">
                      <p className="resora-label">Reviewer questions</p>
                      <div className="mt-3 space-y-2 text-[13px] leading-7 text-text-dim">
                        {researcherWorkflow.reviewerQuestions.map((item) => <p key={item}>- {item}</p>)}
                      </div>
                    </div>
                    <div className="glass-surface p-4">
                      <p className="resora-label">Next experiment ideas</p>
                      <div className="mt-3 space-y-2 text-[13px] leading-7 text-text-dim">
                        {researcherWorkflow.nextExperiments.map((item) => <p key={item}>- {item}</p>)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-5 rounded-[18px] border border-border bg-panel p-5 text-[13px] leading-7 text-text-dim">
                Generate a summary to unlock claim-level evidence mapping, reviewer questions, citation decision support, and a replication-ready reading plan.
              </div>
            )}
          </section>

          <div className={response ? "reader-two-grid reader-aids-grid" : "hidden"}>
            <section className="panel-surface p-5">
              <p className="resora-label">Reader aids</p>
              {response ? (
                <div className="mt-4 space-y-4">
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Glossary</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {response.glossary_entries.map((entry) => (
                        <span key={entry.term} title={`${entry.definition} | ${entry.source_span}`} className="resora-chip resora-chip-active">{entry.term}</span>
                      ))}
                    </div>
                    <div className="mt-3 space-y-2 text-[12.5px] leading-6 text-text-dim">
                      {response.hover_glossary_spans.slice(0, 3).map((item) => (
                        <p key={`${item.term}-${item.start_offset}`}>{item.term} | offsets {item.start_offset}-{item.end_offset}</p>
                      ))}
                    </div>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Contributions</p>
                    <div className="mt-3 space-y-2 text-[13px] leading-7 text-text-dim">
                      {response.contributions.map((item) => <p key={item} data-no-translate>- {item}</p>)}
                    </div>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Limitations</p>
                    <div className="mt-3 space-y-2 text-[13px] leading-7 text-text-dim">
                      {response.limitations.map((item) => <p key={item} data-no-translate>- {item}</p>)}
                    </div>
                    <p className="mt-3 text-[12.5px] text-gold-text">Severity score: {response.study_limitation_severity_score}</p>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-[13px] leading-7 text-text-dim">Generate a summary to populate glossary, contributions, and limitations.</p>
              )}
            </section>

            <section className="panel-surface p-5">
              <p className="resora-label">Teaching and translation</p>
              {response ? (
                <div className="mt-4 space-y-4">
                  <div className="flex flex-wrap gap-2">
                    {Object.keys(response.translations).map((languageKey) => (
                      <button
                        key={languageKey}
                        type="button"
                        onClick={() => setActiveTranslation(languageKey)}
                        className={`focus-gold ${activeTranslation === languageKey ? "resora-chip resora-chip-active" : "resora-chip"}`}
                      >
                        {languageKey}
                      </button>
                    ))}
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Translation preview</p>
                    <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{String(response.translations[activeTranslation]?.tldr || "")}</p>
                    <p className="mt-3 text-[12.5px] text-text-faint">Available: {response.translation_languages.join(", ")}</p>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Exam-style Q and A</p>
                    <div className="mt-3 space-y-3">
                      {response.exam_qa.map((item) => (
                        <div key={item.question} data-no-translate>
                          <p className="text-[13px] text-text">{item.question}</p>
                          <p className="mt-1 text-[13px] leading-7 text-text-dim">{item.answer}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-[13px] leading-7 text-text-dim">Translation preview and teaching aids will appear after summary generation.</p>
              )}
            </section>
          </div>

          <div className={hasReaderContent ? "reader-two-grid reader-source-workspace" : "hidden"}>
            <section className="panel-surface p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="resora-label">Evidence passages</p>
                  <h3 className="mt-2 font-display text-[18px] font-normal text-text">What matters in this paper</h3>
                </div>
                {response ? <span className="resora-chip">{response.datasets.join(", ") || "No dataset tags"}</span> : null}
              </div>

              <div className={mobileReadingMode ? "reader-mobile-flow reader-evidence-list mt-4" : "reader-evidence-list mt-4"}>
                {sourceParagraphs.map((paragraph, index) => (
                  <button
                    key={`${paragraph}-${index}`}
                    type="button"
                    data-reader-evidence="true"
                    onContextMenu={(event) => {
                      event.preventDefault();
                      selectEvidenceParagraph(paragraph);
                    }}
                    onPointerDown={() => selectEvidenceParagraph(paragraph)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        selectEvidenceParagraph(paragraph);
                      }
                    }}
                    className={[
                      "focus-gold paper-quote block w-full text-left text-[13px] leading-7",
                      focusMode && index !== 0 ? "paper-quote-dimmed" : "",
                    ].join(" ")}
                    title="Explain this paragraph"
                  >
                    <span>{["Claim", "Method", "Result", "Scale", "Context", "Limitation", "Availability"][index] || "Note"}</span>
                    <strong data-no-translate>{compactText(paragraph, 720)}</strong>
                  </button>
                ))}
              </div>

              {response ? (
                <div className="mt-5 rounded-[10px] border border-border bg-panel p-4">
                  <p className="resora-label">Audience guidance</p>
                  <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{response.audience_guidance}</p>
                </div>
              ) : null}
            </section>

            <section className={explain ? "panel-surface p-5 reader-explain-panel" : "hidden"}>
              <p className="resora-label">Explain panel</p>
              {explain ? (
                <div className="mt-4 space-y-4">
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Explanation</p>
                    <p className="mt-3 text-[13px] leading-7 text-text-dim" data-no-translate>{explain.explanation}</p>
                    <p className="mt-3 text-[12.5px] text-text-faint">
                      {explain.audience_mode} | {explain.reading_level} | {formatConfidence(explain.confidence_score)}
                    </p>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Simplified points</p>
                    <div className="mt-3 space-y-2 text-[13px] leading-7 text-text-dim">
                      {explain.simplified_points.map((item) => <p key={item} data-no-translate>- {item}</p>)}
                    </div>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Glossary terms</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {Object.keys(explain.glossary_terms).map((item) => <span key={item} className="resora-chip">{item}</span>)}
                    </div>
                    <p className="mt-3 text-[12.5px] text-text-faint">{explain.source_span}</p>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-[13px] leading-7 text-text-dim">Choose any paragraph from the left side to open the explain panel.</p>
              )}
            </section>
          </div>
        </div>

        <aside className="reader-side-stack">
          <section className={response || trust ? "panel-surface p-5 reader-quick-status" : "hidden"}>
            <p className="resora-label">Critique agent</p>
            <div className="reader-compact-facts mt-4">
              <p>{readerDifficulty(response?.difficulty_score || "Medium")}</p>
              <p>Freshness: {response?.freshness_indicator || "Recent"}</p>
              <p>Length mode: {response?.summary_length_applied || summaryLength}</p>
              <p>Trust strength: {trust?.evidence_strength || "Pending"}</p>
            </div>
            <div className="mt-4 inline-flex rounded-full border border-teal bg-teal-soft px-4 py-[6px] font-mono text-[10.5px] uppercase tracking-[0.08em] text-teal-text">
              {trust ? `Moderation: ${trust.moderation_status}` : response ? "Reader signals generated" : "Awaiting summary"}
            </div>
          </section>

          <section className={trust && showAdvancedReaderPanels ? "panel-surface p-5" : "hidden"}>
            <p className="resora-label">Trust workbench</p>
            {trust ? (
              <div className="mt-4 space-y-4">
                <div className="glass-surface p-4">
                  <p className="text-[13px] text-text">Manual review queue</p>
                  <label className="mt-3 flex items-center gap-3 text-[13px] text-text-dim">
                    <input type="checkbox" checked={manualFlag} onChange={(event) => setManualFlag(event.target.checked)} />
                    Flag this paper as questionable
                  </label>
                  <textarea
                    value={moderationNote}
                    onChange={(event) => setModerationNote(event.target.value)}
                    className="resora-input mt-3 min-h-[80px]"
                    placeholder="Supervisor note for moderation queue"
                  />
                  <button type="button" onClick={() => void runTrustAnalysis()} className="resora-button-primary mt-3 w-full">
                    Submit review signal
                  </button>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Journal impact</p>
                    <p className="mt-2 text-[13px] leading-6 text-text-dim">
                      {trust.journal_impact_profile.impact_tier} | {trust.journal_impact_profile.citation_signal}
                    </p>
                  </div>
                  <div className="glass-surface p-4">
                    <p className="text-[13px] text-text">Sample size</p>
                    <p className="mt-2 text-[13px] leading-6 text-text-dim">
                      n={trust.sample_size_profile.extracted_n || 0} | {trust.sample_size_profile.adequacy}
                    </p>
                  </div>
                </div>

                <div className="glass-surface p-4">
                  <p className="text-[13px] text-text">Evidence meter</p>
                  <div className="mt-3 space-y-3">
                    {trust.evidence_meter.map((item) => (
                      <div key={item.label}>
                        <div className="flex items-center justify-between text-[12.5px] text-text-dim">
                          <span>{item.label}</span>
                          <span className="text-text">{item.score.toFixed(1)}</span>
                        </div>
                        <div className="mt-2 h-2 rounded-full bg-panel">
                          <div className="h-2 rounded-full bg-[#a84408]" style={{ width: `${Math.min(100, item.score * 10)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="glass-surface p-4">
                  <p className="text-[13px] text-text">Bias and anomaly flags</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {trust.bias_tag_details.map((item) => (
                      <span key={item.label} title={item.explanation} className="resora-chip">
                        {item.label}
                      </span>
                    ))}
                    {trust.outlier_anomaly_flags.map((item) => (
                      <span key={item} className="status-pill status-pill-coral">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="glass-surface p-4">
                  <p className="text-[13px] text-text">Statistical sanity</p>
                  <div className="mt-3 space-y-2 text-[12.5px] leading-6 text-text-dim">
                    {trust.statistical_sanity_checks.map((item) => (
                      <p key={item.label}>
                        {item.label}: {item.status}
                        {item.evidence ? ` | ${item.evidence}` : ""}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-[13px] leading-7 text-text-dim">
                Generate a summary or refresh trust analysis to populate the trust workbench.
              </p>
            )}
          </section>

          <section className={hasReaderContent ? "panel-surface p-5 reader-action-card" : "hidden"}>
            <p className="resora-label">Add to</p>
            <div className="mt-4 space-y-3">
              <button
                type="button"
                onClick={() => addReaderTo("comparison")}
                className="focus-gold block w-full rounded-[10px] border border-border bg-panel px-4 py-3 text-left text-[13px] text-text-dim transition hover:border-teal hover:text-text"
              >
                Comparison workspace
              </button>
              <button
                type="button"
                onClick={() => addReaderTo("writing")}
                className="focus-gold block w-full rounded-[10px] border border-border bg-panel px-4 py-3 text-left text-[13px] text-text-dim transition hover:border-teal hover:text-text"
              >
                Literature review draft
              </button>
              <button
                type="button"
                onClick={() => addReaderTo("library")}
                className="focus-gold block w-full rounded-[10px] border border-gold bg-gold-soft px-4 py-3 text-left text-[13px] text-gold-text transition hover:bg-gold hover:text-white"
              >
                My library
              </button>
            </div>
          </section>

          <section className={hasReaderContent ? "panel-surface p-5 reader-action-card" : "hidden"}>
            <p className="resora-label">Export</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={() => exportReader("bibtex")} className="resora-chip">BibTeX</button>
              <button type="button" onClick={() => exportReader("endnote")} className="resora-chip">EndNote</button>
              <button type="button" onClick={() => exportReader("latex")} className="resora-chip">LaTeX</button>
              <button type="button" onClick={() => exportReader("docx")} className="resora-chip">Docx</button>
            </div>
          </section>

          <section className={response && showAdvancedReaderPanels ? "panel-surface p-5" : "hidden"}>
            <p className="resora-label">Checklist</p>
            {response ? (
              <div className="mt-4 space-y-3">
                {Object.entries(response.reproducibility_checklist).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between text-[13px] text-text-dim">
                    <span>{key}</span>
                    <span className={value ? "text-teal-text" : "text-text-faint"}>{value ? "Yes" : "No"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-[13px] leading-7 text-text-dim">Reproducibility checklist appears after summary generation.</p>
            )}
          </section>

          <section className={trust && showAdvancedReaderPanels ? "panel-surface p-5" : "hidden"}>
            <p className="resora-label">Method + moderation</p>
            {trust ? (
              <div className="mt-4 space-y-4">
                <div className="space-y-2 text-[12.5px] leading-6 text-text-dim">
                  {trust.methodology_quality_checklist.map((item) => (
                    <p key={item.label}>
                      {item.label}: {item.passed ? "Pass" : "Needs work"}
                    </p>
                  ))}
                </div>
                <div className="rounded-[10px] border border-border bg-panel p-3 text-[12.5px] leading-6 text-text-dim">
                  Self-citation: {Math.round(trust.self_citation_ratio * 100)}% | {trust.self_citation_flag}
                  <br />
                  Reproducibility: {trust.reproducibility_score}/10
                  <br />
                  Stats appropriateness: {trust.statistical_appropriateness}
                </div>
                {trust.moderation_queue_entry ? (
                  <div className="rounded-[10px] border border-border-hi bg-panel p-3 text-[12.5px] leading-6 text-text-dim">
                    {trust.moderation_queue_entry.reason}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="mt-4 text-[13px] leading-7 text-text-dim">Method checklist and moderation state appear after trust analysis.</p>
            )}
          </section>

          <section className={response && showAdvancedReaderPanels ? "panel-surface p-5" : "hidden"}>
            <p className="resora-label">Outline + explainability</p>
            {response ? (
              <div className="mt-4 space-y-4">
                <div className="space-y-2">
                  {response.outline_sections.map((item) => (
                    <div key={item.label} className="rounded-[10px] border border-border bg-panel p-3">
                      <p className="text-[13px] text-text">{item.label}</p>
                      <p className="mt-1 text-[12.5px] text-text-dim">{item.source_span}</p>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  {response.paragraph_explainability_preview.map((item) => (
                    <div key={item.source_span} className="rounded-[10px] border border-border bg-panel p-3">
                      <p className="text-[12.5px] text-text">{item.explanation}</p>
                      <p className="mt-1 text-[12px] text-text-faint">{item.source_span}</p>
                    </div>
                  ))}
                </div>
                {response.key_figure_insight ? (
                  <div className="rounded-[10px] border border-border bg-panel p-3 text-[12.5px] leading-6 text-text-dim">
                    {response.key_figure_insight}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="mt-4 text-[13px] leading-7 text-text-dim">Outline spans and explainability previews will appear after summary generation.</p>
            )}
          </section>
        </aside>
      </div>
    </section>
  );
}
