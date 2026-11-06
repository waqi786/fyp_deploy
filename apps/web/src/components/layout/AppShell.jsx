import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { NavLink, useLocation } from "react-router-dom";
import { createPortal } from "react-dom";
import { ResoraLogo } from "../common/ResoraLogo";


import { researchLanguages } from "../../i18n/languages";
import { hasSearchCatalog } from "../../pages/search/copy";

/* Main tab labels, written by hand for every interface language (machine catalogs mistranslate single words
   such as "Home" or "Gaps"). The tabs are marked data-no-translate so the app-wide translator leaves them alone. */
const TAB_KEYS = ["home", "search", "library", "reader", "compare", "gaps", "write"];
const TAB_LABELS = {
  en: ["Home", "Search", "Library", "Reader", "Compare", "Gaps", "Write"],
  ur: ["ہوم", "تلاش", "لائبریری", "ریڈر", "موازنہ", "خلا", "تحریر"],
  ar: ["الرئيسية", "بحث", "المكتبة", "القارئ", "مقارنة", "الفجوات", "الكتابة"],
  fa: ["خانه", "جستجو", "کتابخانه", "خواننده", "مقایسه", "شکاف‌ها", "نوشتن"],
  hi: ["होम", "खोज", "लाइब्रेरी", "रीडर", "तुलना", "अंतराल", "लेखन"],
  bn: ["হোম", "অনুসন্ধান", "লাইব্রেরি", "রিডার", "তুলনা", "ঘাটতি", "লেখা"],
  "pa-Arab": ["ہوم", "تلاش", "لائبریری", "ریڈر", "مقابلہ", "خلا", "لکھائی"],
  tr: ["Ana sayfa", "Ara", "Kütüphane", "Okuyucu", "Karşılaştır", "Boşluklar", "Yaz"],
  id: ["Beranda", "Cari", "Pustaka", "Pembaca", "Bandingkan", "Celah", "Tulis"],
  ms: ["Utama", "Cari", "Pustaka", "Pembaca", "Banding", "Jurang", "Tulis"],
  "zh-Hans": ["首页", "搜索", "文库", "阅读器", "比较", "研究空白", "写作"],
  "zh-Hant": ["首頁", "搜尋", "文庫", "閱讀器", "比較", "研究空白", "寫作"],
  ja: ["ホーム", "検索", "ライブラリ", "リーダー", "比較", "研究ギャップ", "執筆"],
  ko: ["홈", "검색", "라이브러리", "리더", "비교", "연구 공백", "글쓰기"],
  vi: ["Trang chủ", "Tìm kiếm", "Thư viện", "Trình đọc", "So sánh", "Khoảng trống", "Viết"],
  th: ["หน้าแรก", "ค้นหา", "คลัง", "อ่าน", "เปรียบเทียบ", "ช่องว่าง", "เขียน"],
  es: ["Inicio", "Buscar", "Biblioteca", "Lector", "Comparar", "Vacíos", "Escribir"],
  "pt-BR": ["Início", "Buscar", "Biblioteca", "Leitor", "Comparar", "Lacunas", "Escrever"],
  "pt-PT": ["Início", "Pesquisar", "Biblioteca", "Leitor", "Comparar", "Lacunas", "Escrever"],
  fr: ["Accueil", "Rechercher", "Bibliothèque", "Lecteur", "Comparer", "Lacunes", "Rédiger"],
  de: ["Start", "Suche", "Bibliothek", "Lesen", "Vergleichen", "Lücken", "Schreiben"],
  it: ["Home", "Cerca", "Libreria", "Lettore", "Confronta", "Lacune", "Scrivi"],
  nl: ["Home", "Zoeken", "Bibliotheek", "Lezer", "Vergelijken", "Hiaten", "Schrijven"],
  pl: ["Start", "Szukaj", "Biblioteka", "Czytnik", "Porównaj", "Luki", "Pisz"],
  ru: ["Главная", "Поиск", "Библиотека", "Чтение", "Сравнить", "Пробелы", "Письмо"],
  uk: ["Головна", "Пошук", "Бібліотека", "Читання", "Порівняти", "Прогалини", "Письмо"],
  sv: ["Hem", "Sök", "Bibliotek", "Läsare", "Jämför", "Luckor", "Skriv"],
  el: ["Αρχική", "Αναζήτηση", "Βιβλιοθήκη", "Ανάγνωση", "Σύγκριση", "Κενά", "Γραφή"],
  ro: ["Acasă", "Căutare", "Bibliotecă", "Cititor", "Compară", "Lacune", "Scrie"],
  cs: ["Domů", "Hledat", "Knihovna", "Čtečka", "Porovnat", "Mezery", "Psaní"],
  hu: ["Kezdőlap", "Keresés", "Könyvtár", "Olvasó", "Összevetés", "Hiányok", "Írás"],
  he: ["בית", "חיפוש", "ספרייה", "קורא", "השוואה", "פערים", "כתיבה"],
  sw: ["Nyumbani", "Tafuta", "Maktaba", "Msomaji", "Linganisha", "Mapengo", "Andika"],
  ta: ["முகப்பு", "தேடல்", "நூலகம்", "வாசிப்பு", "ஒப்பீடு", "இடைவெளிகள்", "எழுது"],
  ps: ["کور", "لټون", "کتابتون", "لوستونکی", "پرتله", "تشې", "لیکل"],
  sd: ["گهر", "ڳولا", "لائبريري", "پڙهندڙ", "ڀيٽ", "خال", "لکڻ"],
};
const TAB_ROUTES = ["/", "/search", "/library", "/reader", "/comparison", "/gaps", "/writing"];

function tabsFor(language) {
  const labels = TAB_LABELS[language] || TAB_LABELS.en;
  return TAB_ROUTES.map((to, index) => ({ to, key: TAB_KEYS[index], label: labels[index] }));
}

const themeOptions = ["dark", "light"];
const settingDefaults = {
  fontSize: "normal",
  dyslexia: "false",
  reducedMotion: "false",
  notifications: "priority",
  privacyMode: "standard",
  aiMemory: "project",
  citationStyle: "APA",
  autoSave: "true",
  cloudSync: "true",
  exportFormat: "PDF",
  region: "PK",
};

function readSetting(key) {
  if (typeof window === "undefined") {
    return settingDefaults[key];
  }
  return window.localStorage.getItem(`resora-setting-${key}`) || settingDefaults[key];
}

const navigationItems = [
  { id: "workspace", to: "/", icon: HomeIcon },
  { id: "search", to: "/search", icon: SearchIcon },
  { id: "writing", to: "/library", icon: ReaderIcon },
  { id: "compare", to: "/comparison", icon: CompareIcon },
  { id: "gaps", to: "/gaps", icon: GapIcon },
  { id: "writing", to: "/writing", icon: WritingIcon },
];

const legacyLanguageOptions = [
  { code: "en", native: "English", short: "EN" },
  { code: "ur", native: "اردو", short: "UR" },
  { code: "zh", native: "中文", short: "ZH" },
  { code: "es", native: "Español", short: "ES" },
  { code: "hi", native: "हिन्दी", short: "HI" },
  { code: "ar", native: "العربية", short: "AR" },
];

const legacyLanguageNativeNames = {
  en: "English",
  ur: "اردو",
  zh: "中文",
  es: "Español",
  hi: "हिन्दी",
  ar: "العربية",
};

// Only languages whose Search interface is translated can be chosen, so no screen is left half in English.
const languageOptions = researchLanguages.filter((language) => hasSearchCatalog(language.code)).map((language) => ({
  code: language.code,
  native: language.nativeName,
  short: language.code.toUpperCase(),
}));
const languageNativeNames = Object.fromEntries(languageOptions.map((language) => [language.code, language.native]));

const copy = {
  en: {
    product: "Resora",
    productShort: "Research OS",
    liveWorkspace: "live workspace",
    nav: {
      workspace: ["Home", "start"],
      search: ["Search", "discover"],
      reader: ["Reader", "summaries"],
      chat: ["Chat", "ask papers"],
      multimodal: ["Multimodal", "figures"],
      compare: ["Compare", "tables"],
      gaps: ["Gaps", "trends"],
      writing: ["Writing", "drafts"],
      team: ["Team", "workspace"],
      access: ["Access", "language/a11y"],
      analytics: ["Analytics", "graphs"],
      trust: ["Trust", "security"],
      devai: ["Dev AI", "platform"],
      assurance: ["Assurance", "coverage"],
      control: ["Control", "status"],
    },
    meta: {
      home: ["Home", "Research workspace"],
      search: ["Search", "Find papers"],
      reader: ["Reader", "Read papers"],
      multimodal: ["Multimodal", "Read visuals"],
      chat: ["Chat", "Ask papers"],
      compare: ["Compare", "Compare evidence"],
      gaps: ["Gaps", "Find topics"],
      writing: ["Writing", "Draft with sources"],
      team: ["Team", "Work together"],
      access: ["Access", "Read your way"],
      analytics: ["Analytics", "Track trends"],
      trust: ["Trust", "Protect research"],
      devai: ["Dev AI", "Connect tools"],
      assurance: ["Assure", "Launch checklist"],
      control: ["Control", "Product status"],
    },
    ui: {
      currentView: "Current view",
      focus: "Focus",
      language: "Language",
      theme: "Theme",
      ltr: "LTR",
      rtl: "RTL",
      languageLabel: "Interface language",
      federated: "Live federated research workspace",
      neonGrade: "Fast, cited research workflows.",
      contextPanel: "Context panel",
      contextText: "Your current screen and next step stay clear.",
      quickActions: "Quick actions",
      aiSurface: "AI surface",
      aiSurfaceText: "Use search, reading, chat, writing, and collaboration with sources and confidence.",
      footer: "Source-grounded. Trust-first. Demo-ready.",
      userName: "Waqar Ali",
      settings: "Settings",
      appearance: "Appearance",
      density: "Density",
      compact: "Compact",
      comfortable: "Comfortable",
      compactHelp: "Cleaner screens with fewer paragraphs and tighter cards.",
      sources: "Research databases",
      sourceList: "OpenAlex, Semantic Scholar, arXiv, Crossref, CORE, PMC.",
      account: "Account",
      software: "Software",
      apiKeys: "API keys",
      apiKeyPlaceholder: "Paste key locally",
      profileName: "Research profile",
      notifications: "Notifications",
      storage: "Storage",
      dataControls: "Data controls",
      close: "Close",
    },
    themes: { dark: "Dark", light: "Light", contrast: "Contrast" },
  },
  ur: {
    product: "ریسورا",
    productShort: "تحقیقی نظام",
    liveWorkspace: "لائیو ورک اسپیس",
    nav: {
      workspace: ["ہوم", "آغاز"],
      search: ["تلاش", "تحقیقی دریافت"],
      reader: ["ریڈر", "خلاصے"],
      chat: ["چیٹ", "مقالات سے سوال"],
      multimodal: ["ملٹی موڈل", "اشکال/جدول"],
      compare: ["موازنہ", "تحقیقی جدول"],
      gaps: ["تحقیقی خلا", "رجحانات"],
      writing: ["تحریر", "مسودے"],
      team: ["ٹیم", "مشترکہ کام"],
      access: ["رسائی", "زبان/آسانی"],
      analytics: ["تجزیات", "گراف"],
      trust: ["اعتماد", "سکیورٹی"],
      devai: ["ڈویلپر ذہانت", "پلیٹ فارم"],
      assurance: ["تصدیق", "کوریج"],
      control: ["کنٹرول", "حالت"],
    },
    meta: {
      home: ["مرکزی صفحہ", "تحقیقی آپریٹنگ سسٹم"],
      search: ["تلاش", "تحقیقی ورک اسپیس"],
      reader: ["ریڈر", "مقالے کی سمجھ"],
      multimodal: ["ملٹی موڈل", "اشکال، جدول اور مساوات"],
      chat: ["چیٹ", "ماخذی چیٹ سسٹم"],
      compare: ["موازنہ", "متعدد مقالوں کا موازنہ"],
      gaps: ["تحقیقی خلا", "خلا اور رجحان کی شناخت"],
      writing: ["تحریر", "لٹریچر ریویو اور حوالہ جات"],
      team: ["ٹیم", "تعاون اور ورک اسپیس کنٹرول"],
      access: ["رسائی", "ذاتی ترجیحات اور آسان رسائی"],
      analytics: ["تجزیات", "تحقیقی بصیرت اور visualization"],
      trust: ["اعتماد", "سکیورٹی، تعمیل، موبائل اور آف لائن"],
      devai: ["ڈویلپر ذہانت", "توسیع پذیری اور اعلی ذہانت"],
      assurance: ["تصدیق", "تمام فیچرز کی verification matrix"],
      control: ["کنٹرول", "پلیٹ فارم کی حالت"],
    },
    ui: {
      currentView: "موجودہ منظر",
      focus: "مرکزی کام",
      language: "زبان",
      theme: "تھیم",
      ltr: "بائیں سے دائیں",
      rtl: "دائیں سے بائیں",
      languageLabel: "انٹرفیس کی زبان",
      federated: "لائیو فیڈریٹڈ تحقیقی ورک اسپیس",
      neonGrade: "سولڈ نیون UI، source-grounded workflows، production gates واضح۔",
      contextPanel: "سیاق و سباق پینل",
      contextText: "ہر اسکرین پر product status اور اگلا قدم واضح رہتا ہے، ایک سنجیدہ SaaS workbench کی طرح۔",
      quickActions: "فوری اقدامات",
      aiSurface: "AI سطح",
      aiSurfaceText: "Search، Reader، Chat، Compare اور Assurance استعمال کر کے product کو real user کی طرح validate کریں۔",
      footer: "Source-grounded analysis اور trust-first UI patterns کے ساتھ production-ready research workbench۔",
      userName: "وقار علی",
    },
    themes: { dark: "ڈارک", light: "لائٹ", contrast: "ہائی کنٹراسٹ" },
  },
  zh: {
    product: "Resora",
    productShort: "研究系统",
    liveWorkspace: "实时工作区",
    nav: {
      workspace: ["主页", "开始"],
      search: ["搜索", "发现"],
      reader: ["阅读器", "摘要"],
      chat: ["聊天", "问论文"],
      multimodal: ["多模态", "图表"],
      compare: ["比较", "表格"],
      gaps: ["研究空白", "趋势"],
      writing: ["写作", "草稿"],
      team: ["团队", "协作"],
      access: ["访问", "语言/无障碍"],
      analytics: ["分析", "图谱"],
      trust: ["信任", "安全"],
      devai: ["开发智能", "平台"],
      assurance: ["验证", "覆盖"],
      control: ["控制台", "状态"],
    },
    meta: {
      home: ["主页", "研究操作系统"],
      search: ["搜索", "研究工作区"],
      reader: ["阅读器", "论文理解"],
      multimodal: ["多模态", "图、表和公式"],
      chat: ["聊天", "来源问答系统"],
      compare: ["比较", "多论文比较"],
      gaps: ["研究空白", "空白与趋势检测"],
      writing: ["写作", "文献综述与参考管理"],
      team: ["团队", "协作与工作区控制"],
      access: ["访问", "个性化与无障碍"],
      analytics: ["分析", "可视化与研究智能"],
      trust: ["信任", "安全、合规、移动与离线"],
      devai: ["开发智能", "扩展性与高级智能"],
      assurance: ["验证", "完整功能验证矩阵"],
      control: ["控制台", "平台状态"],
    },
    ui: {},
    themes: { dark: "深色", light: "浅色", contrast: "高对比" },
  },
  es: {
    product: "Resora",
    productShort: "Sistema de investigación",
    liveWorkspace: "espacio en vivo",
    nav: {
      workspace: ["Inicio", "empezar"],
      search: ["Buscar", "descubrir"],
      reader: ["Lector", "resúmenes"],
      chat: ["Chat", "preguntar"],
      multimodal: ["Multimodal", "figuras"],
      compare: ["Comparar", "tablas"],
      gaps: ["Brechas", "tendencias"],
      writing: ["Escritura", "borradores"],
      team: ["Equipo", "colaboración"],
      access: ["Acceso", "idioma/a11y"],
      analytics: ["Analítica", "gráficos"],
      trust: ["Confianza", "seguridad"],
      devai: ["IA dev", "plataforma"],
      assurance: ["Verificación", "cobertura"],
      control: ["Control", "estado"],
    },
    meta: {
      home: ["Inicio", "Sistema operativo de investigación"],
      search: ["Buscar", "Espacio de investigación"],
      reader: ["Lector", "Comprensión de papers"],
      multimodal: ["Multimodal", "Figuras, tablas y ecuaciones"],
      chat: ["Chat", "Sistema con fuentes"],
      compare: ["Comparar", "Comparación multi-paper"],
      gaps: ["Brechas", "Detección de brechas y tendencias"],
      writing: ["Escritura", "Revisión literaria y referencias"],
      team: ["Equipo", "Colaboración y control"],
      access: ["Acceso", "Personalización y accesibilidad"],
      analytics: ["Analítica", "Visualización e inteligencia"],
      trust: ["Confianza", "Seguridad, cumplimiento y móvil"],
      devai: ["IA dev", "Extensibilidad e IA avanzada"],
      assurance: ["Verificación", "Matriz completa de funciones"],
      control: ["Control", "Estado de plataforma"],
    },
    ui: {},
    themes: { dark: "Oscuro", light: "Claro", contrast: "Contraste" },
  },
  hi: {
    product: "Resora",
    productShort: "शोध प्रणाली",
    liveWorkspace: "लाइव वर्कस्पेस",
    nav: {
      workspace: ["होम", "शुरू"],
      search: ["खोज", "डिस्कवरी"],
      reader: ["रीडर", "सारांश"],
      chat: ["चैट", "पेपर से सवाल"],
      multimodal: ["मल्टीमोडल", "चित्र"],
      compare: ["तुलना", "तालिकाएँ"],
      gaps: ["रिसर्च गैप", "रुझान"],
      writing: ["लेखन", "ड्राफ्ट"],
      team: ["टीम", "सहयोग"],
      access: ["एक्सेस", "भाषा/a11y"],
      analytics: ["एनालिटिक्स", "ग्राफ"],
      trust: ["ट्रस्ट", "सुरक्षा"],
      devai: ["डेवलपर बुद्धि", "प्लेटफॉर्म"],
      assurance: ["सत्यापन", "कवरेज"],
      control: ["कंट्रोल", "स्थिति"],
    },
    meta: {
      home: ["होम", "शोध ऑपरेटिंग सिस्टम"],
      search: ["खोज", "रिसर्च वर्कस्पेस"],
      reader: ["रीडर", "पेपर समझना"],
      multimodal: ["मल्टीमोडल", "चित्र, तालिका और समीकरण"],
      chat: ["चैट", "स्रोत-आधारित चैट सिस्टम"],
      compare: ["तुलना", "मल्टी-पेपर तुलना"],
      gaps: ["रिसर्च गैप", "गैप और ट्रेंड पहचान"],
      writing: ["लेखन", "लिटरेचर रिव्यू और रेफरेंस"],
      team: ["टीम", "सहयोग और वर्कस्पेस कंट्रोल"],
      access: ["एक्सेस", "पर्सनलाइजेशन और एक्सेसिबिलिटी"],
      analytics: ["एनालिटिक्स", "विज़ुअलाइज़ेशन और इंटेलिजेंस"],
      trust: ["ट्रस्ट", "सुरक्षा, कम्प्लायंस, मोबाइल"],
      devai: ["डेवलपर बुद्धि", "विस्तार और उन्नत बुद्धि"],
      assurance: ["सत्यापन", "पूर्ण फीचर वेरिफिकेशन"],
      control: ["कंट्रोल", "प्लेटफॉर्म स्थिति"],
    },
    ui: {},
    themes: { dark: "डार्क", light: "लाइट", contrast: "कॉन्ट्रास्ट" },
  },
  ar: {
    product: "ريسورا",
    productShort: "نظام البحث",
    liveWorkspace: "مساحة عمل مباشرة",
    nav: {
      workspace: ["الرئيسية", "ابدأ"],
      search: ["بحث", "اكتشاف"],
      reader: ["القارئ", "ملخصات"],
      chat: ["الدردشة", "اسأل الأوراق"],
      multimodal: ["متعدد الوسائط", "الأشكال"],
      compare: ["مقارنة", "جداول"],
      gaps: ["الفجوات", "اتجاهات"],
      writing: ["الكتابة", "مسودات"],
      team: ["الفريق", "تعاون"],
      access: ["الوصول", "لغة/إتاحة"],
      analytics: ["تحليلات", "رسوم"],
      trust: ["الثقة", "الأمان"],
      devai: ["ذكاء المطور", "منصة"],
      assurance: ["التحقق", "تغطية"],
      control: ["التحكم", "الحالة"],
    },
    meta: {
      home: ["الرئيسية", "نظام تشغيل البحث"],
      search: ["بحث", "مساحة البحث"],
      reader: ["القارئ", "فهم الأوراق"],
      multimodal: ["متعدد الوسائط", "الأشكال والجداول والمعادلات"],
      chat: ["الدردشة", "نظام دردشة موثق"],
      compare: ["مقارنة", "مقارنة عدة أوراق"],
      gaps: ["الفجوات", "كشف الفجوات والاتجاهات"],
      writing: ["الكتابة", "مراجعة أدبية وإدارة مراجع"],
      team: ["الفريق", "تعاون وتحكم مساحة العمل"],
      access: ["الوصول", "تخصيص وإتاحة"],
      analytics: ["تحليلات", "تصور وذكاء بحثي"],
      trust: ["الثقة", "أمان وامتثال وموبايل"],
      devai: ["ذكاء المطور", "قابلية التوسع وذكاء متقدم"],
      assurance: ["التحقق", "مصفوفة تحقق الميزات"],
      control: ["التحكم", "حالة المنصة"],
    },
    ui: {},
    themes: { dark: "داكن", light: "فاتح", contrast: "تباين" },
  },
};

Object.assign(copy.ur.ui, {
  federated: "لائیو فیڈریٹڈ تحقیقی ورک اسپیس",
  neonGrade: "ٹھوس نیون انٹرفیس، ماخذ پر مبنی ورک فلو، اور واضح پروڈکشن گیٹس۔",
  contextText: "ہر اسکرین پر مصنوعات کی حالت اور اگلا قدم واضح رہتا ہے، جیسے ایک سنجیدہ خدماتی سافٹ ویئر ورک بینچ۔",
  aiSurface: "مصنوعی ذہانت سطح",
  aiSurfaceText: "تلاش، ریڈر، چیٹ، موازنہ اور تصدیق استعمال کر کے پروڈکٹ کو حقیقی صارف کی طرح جانچیں۔",
  footer: "ماخذ پر مبنی تجزیہ اور اعتماد کو ترجیح دینے والے انٹرفیس پیٹرنز کے ساتھ پروڈکشن ریڈی تحقیقی ورک بینچ۔",
});

Object.assign(copy.zh.ui, {
  currentView: "当前视图",
  focus: "重点",
  language: "语言",
  theme: "主题",
  ltr: "从左到右",
  rtl: "从右到左",
  languageLabel: "界面语言",
  federated: "实时联合研究工作区",
  neonGrade: "纯色霓虹界面、来源支撑流程和清晰生产关卡。",
  contextPanel: "上下文面板",
  contextText: "每个页面都会显示产品状态和下一步操作，像严肃的软件服务工作台。",
  quickActions: "快捷操作",
  aiSurface: "智能工作区",
  aiSurfaceText: "使用搜索、阅读器、聊天、比较和验证，以真实用户方式检查产品。",
  footer: "具备来源支撑分析和信任优先界面的生产级研究工作台。",
  userName: "Waqar Ali",
});

Object.assign(copy.es.ui, {
  currentView: "Vista actual",
  focus: "Enfoque",
  language: "Idioma",
  theme: "Tema",
  ltr: "izquierda a derecha",
  rtl: "derecha a izquierda",
  languageLabel: "Idioma de interfaz",
  federated: "Espacio de investigación federado en vivo",
  neonGrade: "Interfaz neón sólida, flujos con fuentes y puertas de producción visibles.",
  contextPanel: "Panel de contexto",
  contextText: "Cada pantalla mantiene visible el estado del producto y las próximas acciones, como un banco de trabajo de software serio.",
  quickActions: "Acciones rápidas",
  aiSurface: "Superficie de IA",
  aiSurfaceText: "Usa Búsqueda, Lector, Chat, Comparación y Verificación para validar el producto como usuario real.",
  footer: "Workbench de investigación listo para producción con análisis basado en fuentes e interfaz centrada en confianza.",
  userName: "Waqar Ali",
});

Object.assign(copy.hi.ui, {
  currentView: "वर्तमान दृश्य",
  focus: "फोकस",
  language: "भाषा",
  theme: "थीम",
  ltr: "बाएं से दाएं",
  rtl: "दाएं से बाएं",
  languageLabel: "इंटरफेस भाषा",
  federated: "लाइव फेडरेटेड शोध कार्यक्षेत्र",
  neonGrade: "ठोस नियोन UI, स्रोत-आधारित वर्कफ्लो और स्पष्ट प्रोडक्शन गेट।",
  contextPanel: "संदर्भ पैनल",
  contextText: "हर स्क्रीन पर उत्पाद स्थिति और अगला कदम दिखता है, जैसे गंभीर सॉफ्टवेयर सेवा वर्कबेंच।",
  quickActions: "त्वरित क्रियाएं",
  aiSurface: "बुद्धिमान सतह",
  aiSurfaceText: "खोज, रीडर, चैट, तुलना और सत्यापन से उत्पाद को वास्तविक उपयोगकर्ता की तरह जांचें।",
  footer: "स्रोत-आधारित विश्लेषण और भरोसा-प्रथम UI पैटर्न वाला प्रोडक्शन-रेडी शोध वर्कबेंच।",
  userName: "Waqar Ali",
});

Object.assign(copy.ar.ui, {
  currentView: "العرض الحالي",
  focus: "التركيز",
  language: "اللغة",
  theme: "السمة",
  ltr: "من اليسار إلى اليمين",
  rtl: "من اليمين إلى اليسار",
  languageLabel: "لغة الواجهة",
  federated: "مساحة بحث موحدة مباشرة",
  neonGrade: "واجهة نيون صلبة، تدفقات موثقة بالمصادر، وبوابات إنتاج واضحة.",
  contextPanel: "لوحة السياق",
  contextText: "كل شاشة تعرض حالة المنتج والخطوة التالية بوضوح، مثل منصة خدمة برمجية احترافية.",
  quickActions: "إجراءات سريعة",
  aiSurface: "سطح الذكاء الاصطناعي",
  aiSurfaceText: "استخدم البحث والقارئ والدردشة والمقارنة والتحقق لفحص المنتج كمستخدم حقيقي.",
  footer: "منصة بحث جاهزة للإنتاج مع تحليل موثق بالمصادر وواجهة تضع الثقة أولا.",
  userName: "Waqar Ali",
});

function getLegacyCopy(language) {
  if (language === "ur") {
    return {
      ...copy.en,
      productShort: "تحقیقی OS",
      liveWorkspace: "لائیو ورک اسپیس",
      nav: {
        workspace: ["ہوم", "آغاز"],
        search: ["تلاش", "دریافت"],
        reader: ["ریڈر", "خلاصے"],
        chat: ["چیٹ", "مقالوں سے پوچھیں"],
        multimodal: ["ملٹی موڈل", "اشکال"],
        compare: ["موازنہ", "جدول"],
        gaps: ["خلا", "رجحانات"],
        writing: ["تحریر", "مسودے"],
        team: ["ٹیم", "ورک اسپیس"],
        access: ["رسائی", "زبان/a11y"],
        analytics: ["تجزیات", "گراف"],
        trust: ["اعتماد", "سیکیورٹی"],
        devai: ["ڈیولپر AI", "پلیٹ فارم"],
        assurance: ["یقین دہانی", "کوریج"],
        control: ["کنٹرول", "حالت"],
      },
      meta: {
        home: ["ہوم", "تحقیقی ورک اسپیس"],
        search: ["تلاش", "مقالے تلاش کریں"],
        reader: ["ریڈر", "مقالے پڑھیں"],
        multimodal: ["ملٹی موڈل", "بصری مواد پڑھیں"],
        chat: ["چیٹ", "مقالوں سے پوچھیں"],
        compare: ["موازنہ", "ثبوت کا موازنہ"],
        gaps: ["خلا", "موضوعات تلاش کریں"],
        writing: ["تحریر", "ماخذ کے ساتھ مسودہ"],
        team: ["ٹیم", "مل کر کام کریں"],
        access: ["رسائی", "اپنے انداز سے پڑھیں"],
        analytics: ["تجزیات", "رجحانات دیکھیں"],
        trust: ["اعتماد", "تحقیق محفوظ رکھیں"],
        devai: ["ڈیولپر AI", "ٹولز جوڑیں"],
        assurance: ["یقین دہانی", "لانچ چیک لسٹ"],
        control: ["کنٹرول", "پروڈکٹ حالت"],
      },
      ui: {
        ...copy.en.ui,
        currentView: "موجودہ منظر",
        focus: "توجہ",
        language: "زبان",
        theme: "تھیم",
        ltr: "LTR",
        rtl: "RTL",
        languageLabel: "انٹرفیس زبان",
        contextPanel: "سیاق پینل",
        contextText: "آپ کی موجودہ اسکرین اور اگلا قدم واضح رہتا ہے.",
        quickActions: "فوری اقدامات",
        aiSurface: "AI سطح",
        aiSurfaceText: "تلاش، مطالعہ، چیٹ، تحریر اور تعاون کو ماخذ اور اعتماد کے ساتھ استعمال کریں.",
        footer: "ماخذی. اعتماد پہلے. ڈیمو کے لیے تیار.",
        settings: "ترتیبات",
        appearance: "ظاہری شکل",
        density: "کثافت",
        compact: "مختصر",
        comfortable: "آرام دہ",
        compactHelp: "کم متن اور ٹائٹ کارڈز کے ساتھ صاف اسکرینز.",
        sources: "تحقیقی ڈیٹابیس",
        account: "اکاؤنٹ",
        software: "سافٹ ویئر",
        apiKeys: "API کیز",
        apiKeyPlaceholder: "کلید مقامی طور پر پیسٹ کریں",
        profileName: "تحقیقی پروفائل",
        notifications: "اطلاعات",
        storage: "اسٹوریج",
        dataControls: "ڈیٹا کنٹرولز",
        close: "بند کریں",
      },
      themes: { dark: "ڈارک", light: "لائٹ", contrast: "کنٹراسٹ" },
    };
  }
  return copy.en;
}

function getCopy(_language) {
  return copy.en;
}

function pageMeta(pathname, language) {
  const dictionary = getCopy(language);
  const meta = dictionary.meta;
  if (pathname.startsWith("/search")) {
    return { section: meta.search[0], detail: meta.search[1] };
  }
  if (pathname.startsWith("/summaries")) {
    return { section: meta.reader[0], detail: meta.reader[1] };
  }
  if (pathname.startsWith("/multimodal")) {
    return { section: meta.multimodal[0], detail: meta.multimodal[1] };
  }
  if (pathname.startsWith("/chat")) {
    return { section: meta.chat[0], detail: meta.chat[1] };
  }
  if (pathname.startsWith("/comparison")) {
    return { section: meta.compare[0], detail: meta.compare[1] };
  }
  if (pathname.startsWith("/gaps")) {
    return { section: meta.gaps[0], detail: meta.gaps[1] };
  }
  if (pathname.startsWith("/writing") || pathname.startsWith("/library")) {
    return { section: meta.writing[0], detail: meta.writing[1] };
  }
  if (pathname.startsWith("/collaboration")) {
    return { section: meta.team[0], detail: meta.team[1] };
  }
  if (pathname.startsWith("/personalization")) {
    return { section: meta.access[0], detail: meta.access[1] };
  }
  if (pathname.startsWith("/analytics")) {
    return { section: meta.analytics[0], detail: meta.analytics[1] };
  }
  if (pathname.startsWith("/security-mobile")) {
    return { section: meta.trust[0], detail: meta.trust[1] };
  }
  if (pathname.startsWith("/developer-ai")) {
    return { section: meta.devai[0], detail: meta.devai[1] };
  }
  if (pathname.startsWith("/assurance")) {
    return { section: meta.assurance[0], detail: meta.assurance[1] };
  }
  if (pathname.startsWith("/control") || pathname.startsWith("/dashboard")) {
    return { section: meta.control[0], detail: meta.control[1] };
  }
  return { section: meta.home[0], detail: meta.home[1] };
}

function navLinkClass({ isActive }) {
  return [
    "focus-gold group nav-label-button",
    isActive ? "nav-label-button-active" : "",
  ].join(" ");
}

export function AppShell({ children, theme, onThemeChange, language, onLanguageChange, density, onDensityChange, direction }) {
  const location = useLocation();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreTriggerRef = useRef(null);
  const moreMenuRef = useRef(null);
  const [productSettings, setProductSettings] = useState(() =>
    Object.fromEntries(Object.keys(settingDefaults).map((key) => [key, readSetting(key)])),
  );
  const navScrollRef = useRef(null);
  const dictionary = getCopy(language);
  const meta = pageMeta(location.pathname, language);
  const isSearchRoute = location.pathname.startsWith("/search");
  const isReaderRoute = location.pathname.startsWith("/summaries");
  const isHomeRoute = location.pathname === "/";
  const selectedLanguage = languageOptions.find((option) => option.code === language) || languageOptions[0];
  const selectedLanguageName = languageNativeNames[selectedLanguage.code] || selectedLanguage.native;
  const brandLogo = theme === "dark" ? "/brand-dark.png" : "/brand-light.png";

  const contextualHints = [
    { label: dictionary.ui.currentView, value: meta.section },
    { label: dictionary.ui.focus, value: meta.detail },
    { label: dictionary.ui.language, value: `${selectedLanguageName} (${dictionary.ui[direction] || direction.toUpperCase()})` },
    { label: dictionary.ui.theme, value: dictionary.themes[theme] || theme },
  ];
  const primaryMobileItems = navigationItems;

  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const activeItem = navScrollRef.current?.querySelector(".nav-label-button-active");
    activeItem?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [location.pathname]);

  useEffect(() => {
    document.body.dataset.fontSize = productSettings.fontSize;
    document.body.dataset.dyslexia = productSettings.dyslexia;
    document.body.dataset.reducedMotion = productSettings.reducedMotion;
    Object.entries(productSettings).forEach(([key, value]) => {
      window.localStorage.setItem(`resora-setting-${key}`, value);
    });
  }, [productSettings]);

  useEffect(() => {
    if (!moreOpen) return undefined;
    const closeOutside = (event) => {
      if (!moreMenuRef.current?.contains(event.target) && !moreTriggerRef.current?.contains(event.target)) setMoreOpen(false);
    };
    const closeEscape = (event) => {
      if (event.key === "Escape") {
        setMoreOpen(false);
        moreTriggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, [moreOpen]);

  useEffect(() => {
    if (!settingsOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event) => { if (event.key === "Escape") setSettingsOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [settingsOpen]);
  function updateProductSetting(key, value) {
    setProductSettings((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="app-root-shell min-h-screen overflow-x-hidden pb-20 lg:h-screen lg:overflow-hidden lg:pb-0">
        <div
          className={[
            "app-grid-shell grid min-h-screen grid-cols-1 lg:h-screen lg:grid-cols-1",
          "",
          ].join(" ")}
        >
        <header className="resora-topbar">
          <NavLink to="/" className="resora-brand" aria-label="Resora home">
            <img className="resora-brand-mark" src={brandLogo} alt="" />
            <span>Resora</span>
          </NavLink>
          <nav className="resora-tab-nav" aria-label="Main navigation">
            {tabsFor(language).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.to === "/"} data-no-translate="" lang={language}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="resora-topbar-actions">
            <button
              type="button"
              className="resora-theme-toggle"
              role="switch"
              aria-checked={theme === "dark"}
              onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              <span className={theme === "dark" ? "active" : ""} aria-hidden="true">☼</span>
              <span className={theme === "light" ? "active" : ""} aria-hidden="true">☾</span>
            </button>
            <button type="button" className="resora-avatar" onClick={() => setSettingsOpen(true)} aria-label="Open profile and settings">WA</button>
          </div>
        </header>
        <nav className="mobile-bottom-nav" aria-label="Mobile navigation">
          {tabsFor(language).map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} data-no-translate="" lang={language}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <aside className="app-sidebar hidden" aria-hidden="true">
          <div className="sidebar-body flex min-h-0 w-full flex-1 flex-col gap-4 overflow-hidden px-3 pb-3 pt-4">
            <div className="flex items-center gap-3 px-1">
              <ResoraLogo size={50} className="shrink-0 drop-shadow-[0_0_18px_rgba(255,106,0,0.28)]" />
              <div className="min-w-0">
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold-text">{dictionary.product}</p>
                <p className="mt-1 truncate text-[12px] text-text-dim">{dictionary.productShort}</p>
              </div>
            </div>

            <div className="neon-divider" />

            <nav ref={navScrollRef} className="resora-scroll sidebar-nav-scroll flex min-h-0 w-full flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden pr-2">
              {navigationItems.map((item) => {
                const Icon = item.icon;
                const itemCopy = dictionary.nav[item.id] || copy.en.nav[item.id];
                return (
                  <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass} title={itemCopy[0]}>
                    <span className="nav-label-icon">
                      <Icon />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-semibold leading-4">{itemCopy[0]}</span>
                      <span className="mt-0.5 block truncate font-mono text-[9.5px] uppercase tracking-[0.08em] text-text-faint group-hover:text-text-dim">
                        {itemCopy[1]}
                      </span>
                    </span>
                  </NavLink>
                );
              })}
            </nav>
          </div>

          <div className="sidebar-footer grid w-full shrink-0 gap-2 border-t border-border bg-black px-3 py-3 shadow-[0_-10px_30px_rgba(255,106,0,0.08)]">
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="focus-gold flex h-10 w-full items-center justify-between rounded-[15px] border border-gold bg-gold-soft px-4 text-[13px] font-semibold text-gold-text outline-none shadow-[0_0_22px_rgba(255,106,0,0.18)] transition hover:bg-[rgba(255,106,0,0.18)] hover:text-white"
              title={dictionary.ui.settings || "Settings"}
            >
              <span>{dictionary.ui.settings || "Settings"}</span>
              <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-gold-text">{density || "compact"}</span>
            </button>
            <div className="sidebar-profile-card flex min-w-0 items-center gap-3 rounded-[16px] border border-gold bg-[rgba(255,106,0,0.18)] px-3 py-2 shadow-[0_0_22px_rgba(255,106,0,0.12)]">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-semibold text-text">{dictionary.ui.userName}</p>
                <p className="truncate font-mono text-[9.5px] uppercase tracking-[0.08em] text-gold-text">{dictionary.liveWorkspace}</p>
              </div>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gold bg-gold-soft font-mono text-[9.5px] uppercase tracking-[0.08em] text-gold-text shadow-[0_0_18px_rgba(255,106,0,0.22)]">
                WA
              </div>
            </div>
          </div>
        </aside>

        <div className="main-scroll-pane resora-scroll min-w-0 overflow-x-hidden lg:h-screen lg:overflow-y-auto">
          {isSearchRoute || isHomeRoute || isReaderRoute ? (
            <main className="mx-auto max-w-[1600px] px-4 py-4 md:px-6 xl:px-8">
              {children}
            </main>
          ) : (
            <>
              <motion.header
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
                className="hidden"
              >
                <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-3 md:px-6 xl:px-8">
                  <div>
                    <p className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-text-dim">
                      <span className="ai-dot mr-2" />
                      {dictionary.product} / {meta.section}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-3">
                      <h1 className="font-display text-[22px] font-normal leading-none text-text">{meta.detail}</h1>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSettingsOpen(true)}
                      className="focus-gold rounded-full border border-border-hi bg-panel-raised px-3 py-[6px] font-mono text-[10.5px] uppercase tracking-[0.08em] text-text-dim transition hover:border-cyan hover:text-text"
                    >
                      {dictionary.ui.settings || "Settings"}
                    </button>
                    {themeOptions.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => onThemeChange(option)}
                        className={[
                          "focus-gold rounded-full border px-3 py-[6px] font-mono text-[10.5px] uppercase tracking-[0.08em] transition",
                          theme === option
                            ? "border-gold bg-gold-soft text-gold-text"
                            : "border-border-hi bg-panel-raised text-text-dim hover:text-text",
                        ].join(" ")}
                      >
                        {dictionary.themes[option] || option}
                      </button>
                    ))}
                  </div>
                </div>
              </motion.header>

              <main className="mx-auto max-w-[1600px] px-4 py-5 md:px-6 xl:px-8">{children}</main>
            </>
          )}
        </div>

        {false ? <aside className="context-scroll-pane resora-scroll hidden border-l border-border bg-panel 2xl:flex 2xl:h-screen 2xl:flex-col 2xl:overflow-y-auto">
          <div className="flex flex-col gap-2 p-3">
            <div className="rounded-[18px] border border-cyan bg-[rgba(0,20,34,0.76)] p-3 shadow-[0_0_24px_rgba(0,208,255,0.1)]">
              <p className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-cyan-text">{dictionary.ui.contextPanel}</p>
              <h2 className="mt-2 font-display text-[14px] leading-snug text-text">{meta.detail}</h2>
              <div className="neon-divider my-3" />
              <p className="text-[11px] leading-5 text-text-dim">{dictionary.ui.contextText}</p>
            </div>
            <div className="rounded-[18px] border border-border bg-panel-raised p-3 shadow-[0_0_18px_rgba(0,0,0,0.22)]">
              <p className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-text-dim">{dictionary.ui.quickActions}</p>
              <div className="mt-2 flex flex-col gap-1.5">
                {contextualHints.map((item) => (
                  <div key={item.label} className="rounded-[11px] border border-border bg-panel px-2 py-1.5">
                    <span className="block text-[10px] text-text-faint">{item.label}</span>
                    <span className="mt-0.5 block truncate font-mono text-[9.5px] uppercase tracking-[0.08em] text-gold-text">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[18px] border border-teal bg-teal-soft p-3">
              <p className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-teal-text">{dictionary.ui.aiSurface}</p>
              <p className="mt-2 text-[11px] leading-5 text-text-dim">{dictionary.ui.aiSurfaceText}</p>
            </div>
            <div className="rounded-[16px] border border-gold bg-gold-soft px-3 py-2 text-[10.5px] leading-5 text-gold-text">
              {dictionary.ui.footer}
            </div>
          </div>
        </aside> : null}
      </div>

      <nav className="hidden">
        <div className="grid grid-cols-5 gap-1">
          {primaryMobileItems.map((item) => {
            const Icon = item.icon;
            const itemCopy = dictionary.nav[item.id] || copy.en.nav[item.id];
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => ["focus-gold nav-icon-button !h-11 !w-full", isActive ? "nav-icon-button-active" : ""].join(" ")}
                title={itemCopy[0]}
              >
                <span className="flex h-11 items-center justify-center">
                  <Icon />
                </span>
              </NavLink>
            );
          })}
        </div>
      </nav>

      {settingsOpen ? createPortal(
        <div className={["settings-overlay", isHomeRoute ? "home-settings-overlay" : ""].join(" ")} role="presentation" onClick={() => setSettingsOpen(false)}>
          <motion.section
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 24 }}
            transition={{ duration: 0.2 }}
            className="settings-panel"
            role="dialog"
            aria-modal="true"
            aria-label={dictionary.ui.settings || "Settings"}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="resora-label">{dictionary.ui.appearance || "Appearance"}</p>
                <h2>{dictionary.ui.settings || "Settings"}</h2>
              </div>
              <button type="button" onClick={() => setSettingsOpen(false)} className="resora-button-secondary !min-h-[34px] !px-3">
                {dictionary.ui.close || "Close"}
              </button>
            </div>

            <div className="settings-section">
              <p className="resora-label">{dictionary.ui.theme}</p>
              <div className="settings-segment">
                {themeOptions.map((option) => (
                  <button key={option} type="button" onClick={() => onThemeChange(option)} className={theme === option ? "active" : ""}>
                    {dictionary.themes[option] || option}
                  </button>
                ))}
              </div>
              <p className="settings-help">Applies instantly across every screen and stays saved for this browser.</p>
            </div>

            <div className="settings-section">
              <p className="resora-label">{dictionary.ui.language}</p>
              <select value={language} onChange={(event) => onLanguageChange(event.target.value)} className="resora-input w-full">
                {languageOptions.map((option) => (
                  <option key={option.code} value={option.code}>{languageNativeNames[option.code] || option.native}</option>
                ))}
              </select>
            </div>

            <div className="settings-section">
              <p className="resora-label">{dictionary.ui.account || "Account"}</p>
              <input className="resora-input mt-3 w-full" placeholder={dictionary.ui.profileName || "Research profile"} defaultValue={dictionary.ui.userName || "Waqar Ali"} />
              <div className="settings-list">
                <span>Plan: Research Pro</span>
                <span>Workspace: Final Year Project</span>
              </div>
            </div>

            <div className="settings-section">
              <NavLink to="/open-source" onClick={() => setSettingsOpen(false)} className="settings-help underline">
                Open-source notices
              </NavLink>
            </div>

            <div className="settings-section">
              <p className="resora-label">Accessibility</p>
              <div className="settings-segment">
                {["normal", "large", "xl"].map((option) => (
                  <button key={option} type="button" onClick={() => updateProductSetting("fontSize", option)} className={productSettings.fontSize === option ? "active" : ""}>
                    {option === "xl" ? "Extra large" : option}
                  </button>
                ))}
              </div>
              <div className="settings-switch-list">
                <button type="button" className={productSettings.dyslexia === "true" ? "active" : ""} onClick={() => updateProductSetting("dyslexia", productSettings.dyslexia === "true" ? "false" : "true")}>
                  <span>Dyslexia-friendly reading</span>
                  <strong>{productSettings.dyslexia === "true" ? "On" : "Off"}</strong>
                </button>
                <button type="button" className={productSettings.reducedMotion === "true" ? "active" : ""} onClick={() => updateProductSetting("reducedMotion", productSettings.reducedMotion === "true" ? "false" : "true")}>
                  <span>Reduce motion</span>
                  <strong>{productSettings.reducedMotion === "true" ? "On" : "Off"}</strong>
                </button>
              </div>
            </div>

            <div className="settings-section">
              <p className="resora-label">{dictionary.ui.density || "Density"}</p>
              <div className="settings-segment">
                {["compact", "comfortable"].map((option) => (
                  <button key={option} type="button" onClick={() => onDensityChange(option)} className={density === option ? "active" : ""}>
                    {dictionary.ui[option] || option}
                  </button>
                ))}
              </div>
              <p className="settings-help">{dictionary.ui.compactHelp || "Cleaner screens with fewer paragraphs and tighter cards."}</p>
            </div>

            <div className="settings-section">
              <p className="resora-label">Research defaults</p>
              <label className="settings-field">
                <span>Citation style</span>
                <select value={productSettings.citationStyle} onChange={(event) => updateProductSetting("citationStyle", event.target.value)} className="resora-input">
                  <option>APA</option>
                  <option>IEEE</option>
                  <option>MLA</option>
                  <option>Chicago</option>
                  <option>Harvard</option>
                </select>
              </label>
              <label className="settings-field">
                <span>Export format</span>
                <select value={productSettings.exportFormat} onChange={(event) => updateProductSetting("exportFormat", event.target.value)} className="resora-input">
                  <option>PDF</option>
                  <option>DOCX</option>
                  <option>BibTeX</option>
                  <option>CSV</option>
                  <option>JSON</option>
                </select>
              </label>
              <p className="settings-help">{dictionary.ui.sourceList || "OpenAlex, Semantic Scholar, arXiv, Crossref, CORE, PMC."}</p>
            </div>

            <div className="settings-section">
              <p className="resora-label">Privacy and AI</p>
              <label className="settings-field">
                <span>Privacy mode</span>
                <select value={productSettings.privacyMode} onChange={(event) => updateProductSetting("privacyMode", event.target.value)} className="resora-input">
                  <option value="standard">Standard</option>
                  <option value="strict">Strict</option>
                  <option value="local">Local only</option>
                </select>
              </label>
              <label className="settings-field">
                <span>AI memory</span>
                <select value={productSettings.aiMemory} onChange={(event) => updateProductSetting("aiMemory", event.target.value)} className="resora-input">
                  <option value="off">Off</option>
                  <option value="project">Project only</option>
                  <option value="workspace">Workspace-wide</option>
                </select>
              </label>
              <div className="settings-switch-list">
                <button type="button" className={productSettings.autoSave === "true" ? "active" : ""} onClick={() => updateProductSetting("autoSave", productSettings.autoSave === "true" ? "false" : "true")}>
                  <span>Auto-save work</span>
                  <strong>{productSettings.autoSave === "true" ? "On" : "Off"}</strong>
                </button>
                <button type="button" className={productSettings.cloudSync === "true" ? "active" : ""} onClick={() => updateProductSetting("cloudSync", productSettings.cloudSync === "true" ? "false" : "true")}>
                  <span>Cloud sync</span>
                  <strong>{productSettings.cloudSync === "true" ? "On" : "Off"}</strong>
                </button>
              </div>
            </div>

            <div className="settings-section">
              <p className="resora-label">Notifications and security</p>
              <label className="settings-field">
                <span>Notifications</span>
                <select value={productSettings.notifications} onChange={(event) => updateProductSetting("notifications", event.target.value)} className="resora-input">
                  <option value="all">All activity</option>
                  <option value="priority">Priority only</option>
                  <option value="quiet">Quiet mode</option>
                </select>
              </label>
              <label className="settings-field">
                <span>Region</span>
                <select value={productSettings.region} onChange={(event) => updateProductSetting("region", event.target.value)} className="resora-input">
                  <option value="PK">Pakistan</option>
                  <option value="US">United States</option>
                  <option value="EU">European Union</option>
                  <option value="GLOBAL">Global</option>
                </select>
              </label>
              <div className="settings-list">
                <span>Two-factor authentication ready</span>
                <span>Session timeout: 30 minutes</span>
                <span>Data export and delete controls enabled</span>
              </div>
            </div>

            <div className="settings-section">
              <p className="resora-label">{dictionary.ui.apiKeys || "API keys"}</p>
              <input className="resora-input mt-3 w-full" type="password" placeholder={dictionary.ui.apiKeyPlaceholder || "Paste key locally"} />
              <p className="settings-help">Keys stay local to this browser in the demo workspace.</p>
            </div>
          </motion.section>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}

function IconStroke({ children }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-[18px] w-[18px]"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.85"
      strokeLinecap="round"
      strokeLinejoin="round"
      shapeRendering="geometricPrecision"
      vectorEffect="non-scaling-stroke"
    >
      {children}
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m4 6 4 4 4-4" />
    </svg>
  );
}

function HomeIcon() {
  return (
    <IconStroke>
      <path d="M4 11.5 12 5l8 6.5" />
      <path d="M6.5 10.5V19h11v-8.5" />
    </IconStroke>
  );
}

function SearchIcon() {
  return (
    <IconStroke>
      <circle cx="10.5" cy="10.5" r="4.5" />
      <path d="M14 14 19 19" />
    </IconStroke>
  );
}

function ReaderIcon() {
  return (
    <IconStroke>
      <path d="M6 5h11a1 1 0 0 1 1 1v12a8 8 0 0 0-6-2.5A8 8 0 0 0 6 18Z" />
      <path d="M6 5a1 1 0 0 0-1 1v12a8 8 0 0 1 6-2.5" />
    </IconStroke>
  );
}

function ChatIcon() {
  return (
    <IconStroke>
      <path d="M5 6.5h14v8H9l-4 3.5Z" />
      <path d="M8 10h7" />
      <path d="M8 12.5h4" />
    </IconStroke>
  );
}

function GridIcon() {
  return (
    <IconStroke>
      <rect x="4.5" y="4.5" width="6" height="6" />
      <rect x="13.5" y="4.5" width="6" height="6" />
      <rect x="4.5" y="13.5" width="6" height="6" />
      <rect x="13.5" y="13.5" width="6" height="6" />
    </IconStroke>
  );
}

function VisualIcon() {
  return (
    <IconStroke>
      <rect x="4" y="5" width="16" height="12" rx="2" />
      <path d="m7 15 3.5-4 2.5 3 1.5-1.8L18 16" />
      <circle cx="8" cy="8.5" r="1" fill="currentColor" stroke="none" />
    </IconStroke>
  );
}

function CompareIcon() {
  return (
    <IconStroke>
      <path d="M7 5v14" />
      <path d="M17 5v14" />
      <path d="M4 8h6" />
      <path d="M14 8h6" />
      <path d="M4 16h6" />
      <path d="M14 16h6" />
    </IconStroke>
  );
}

function GapIcon() {
  return (
    <IconStroke>
      <path d="M5 18c3-8 6-8 9-3 2 3 3 2 5-5" />
      <circle cx="6" cy="17" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="14" cy="15" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="19" cy="10" r="1.4" fill="currentColor" stroke="none" />
    </IconStroke>
  );
}

function WritingIcon() {
  return (
    <IconStroke>
      <path d="M5 19h14" />
      <path d="M7 16 16.5 6.5 18 8 8.5 17.5 6 18Z" />
      <path d="M14.5 8.5 16 10" />
    </IconStroke>
  );
}

function TeamIcon() {
  return (
    <IconStroke>
      <circle cx="8" cy="8" r="2.5" />
      <circle cx="16" cy="8" r="2.5" />
      <path d="M4.5 18c.8-3 2.6-4.5 5.5-4.5" />
      <path d="M19.5 18c-.8-3-2.6-4.5-5.5-4.5" />
      <path d="M9 18h6" />
    </IconStroke>
  );
}

function AccessIcon() {
  return (
    <IconStroke>
      <circle cx="12" cy="5.5" r="2" />
      <path d="M5 10h14" />
      <path d="M12 10v9" />
      <path d="M8 19h8" />
      <path d="M8.5 13.5 12 10l3.5 3.5" />
    </IconStroke>
  );
}

function AnalyticsIcon() {
  return (
    <IconStroke>
      <path d="M5 18V8" />
      <path d="M12 18V5" />
      <path d="M19 18v-7" />
      <path d="M4 19h16" />
    </IconStroke>
  );
}

function ShieldIcon() {
  return (
    <IconStroke>
      <path d="M12 4 18 6.5v5.2c0 3.4-2.2 6.2-6 8.3-3.8-2.1-6-4.9-6-8.3V6.5Z" />
      <path d="m9.5 12 1.6 1.6 3.4-4" />
    </IconStroke>
  );
}

function DeveloperIcon() {
  return (
    <IconStroke>
      <path d="m8 9-4 3 4 3" />
      <path d="m16 9 4 3-4 3" />
      <path d="m14 6-4 12" />
    </IconStroke>
  );
}

function AssuranceIcon() {
  return (
    <IconStroke>
      <path d="M5 12.5 9.2 17 19 7" />
      <path d="M4 5h16" />
      <path d="M4 19h16" />
    </IconStroke>
  );
}
