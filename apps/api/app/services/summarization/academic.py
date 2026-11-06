import math
import re

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "using", "study", "paper", "results",
}

ACRONYM_MAP = {
    "RAG": "Retrieval-Augmented Generation",
    "BM25": "Best Matching 25",
    "LLM": "Large Language Model",
    "NLP": "Natural Language Processing",
    "OCR": "Optical Character Recognition",
    "AUC": "Area Under the Curve",
    "F1": "F1 Score",
}

TRANSLATION_PREFIXES = {
    "ur": "اردو خلاصہ",
    "es": "Resumen",
    "fr": "Resume",
    "de": "Zusammenfassung",
    "ar": "ملخص",
    "tr": "Ozet",
    "zh": "摘要",
    "hi": "सारांश",
    "fa": "خلاصه",
    "id": "Ringkasan",
}


TRANSLATION_PREFIXES.update(
    {
        "ur": "اردو خلاصہ",
        "fr": "Résumé",
        "ar": "ملخص",
        "tr": "Özet",
        "zh": "摘要",
        "hi": "सारांश",
        "fa": "خلاصه",
    }
)

TRANSLATION_PREFIXES = {
    "ur": "خلاصہ",
    "es": "Resumen",
    "fr": "Résumé",
    "de": "Zusammenfassung",
    "ar": "ملخص",
    "tr": "Özet",
    "zh": "摘要",
    "hi": "सारांश",
    "fa": "خلاصه",
    "id": "Ringkasan",
}

ACADEMIC_TRANSLATION_TERMS = {
    "ur": {
        "this paper": "یہ مقالہ",
        "this study": "یہ مطالعہ",
        "we introduce": "ہم پیش کرتے ہیں",
        "we propose": "ہم تجویز کرتے ہیں",
        "we present": "ہم پیش کرتے ہیں",
        "our method": "ہمارا طریقہ",
        "our approach": "ہمارا طریقہ",
        "machine learning": "مشین لرننگ",
        "logistic regression": "لاجسٹک ریگریشن",
        "deep learning": "ڈیپ لرننگ",
        "neural network": "نیورل نیٹ ورک",
        "neural networks": "نیورل نیٹ ورکس",
        "artificial intelligence": "مصنوعی ذہانت",
        "deepfake": "ڈیپ فیک",
        "diabetes": "ذیابیطس",
        "prediction": "پیش گوئی",
        "dataset": "ڈیٹا سیٹ",
        "datasets": "ڈیٹا سیٹس",
        "model": "ماڈل",
        "models": "ماڈلز",
        "method": "طریقہ",
        "methodology": "طریقہ کار",
        "results": "نتائج",
        "accuracy": "درستی",
        "baseline": "بنیادی معیار",
        "baselines": "بنیادی معیارات",
        "limitation": "حد",
        "limitations": "حدود",
        "future work": "آئندہ کام",
        "samples": "نمونے",
        "patients": "مریض",
        "classification": "درجہ بندی",
        "detection": "تشخیص",
        "summary": "خلاصہ",
        "evidence": "شواہد",
        "confidence": "اعتماد",
        "problem": "مسئلہ",
        "findings": "نتائج",
        "conclusion": "نتیجہ",
        "compares": "موازنہ کرتا ہے",
        "main idea": "مرکزی خیال",
        "in simple words": "سادہ الفاظ میں",
        "simple explanation": "سادہ تشریح",
        "how they did it": "انہوں نے یہ کیسے کیا",
        "how it works": "یہ کیسے کام کرتا ہے",
        "what it found": "اس نے کیا پایا",
        "what they found": "انہوں نے کیا پایا",
        "important caution": "اہم احتیاط",
        "why it matters": "یہ کیوں اہم ہے",
        "what to check next": "اگلی چیز جو چیک کرنی ہے",
        "takeaway": "اہم نکتہ",
        "what to remember": "یاد رکھنے والی بات",
        "title": "عنوان",
        "tldr": "مختصر خلاصہ",
        "the": "",
        "a": "ایک",
        "with": "کے ساتھ",
        "and": "اور",
        "for": "کے لیے",
        "evaluates": "جانچتا ہے",
        "better": "بہتر",
        "than": "سے",
        "external validation": "بیرونی توثیق",
        "discusses": "زیر بحث لاتا ہے",
        "recall": "ریکال",
        "precision": "پریسیژن",
        "interpretability": "قابل فہم ہونا",
        "uses": "استعمال کرتا ہے",
        "improves": "بہتر کرتا ہے",
        "shows": "دکھاتا ہے",
        "show": "دکھاتے ہیں",
        "reports": "رپورٹ کرتا ہے",
    },
    "hi": {
        "this paper": "यह पेपर",
        "this study": "यह अध्ययन",
        "we introduce": "हम प्रस्तुत करते हैं",
        "we propose": "हम प्रस्तावित करते हैं",
        "machine learning": "मशीन लर्निंग",
        "logistic regression": "लॉजिस्टिक रिग्रेशन",
        "deep learning": "डीप लर्निंग",
        "neural networks": "न्यूरल नेटवर्क",
        "artificial intelligence": "कृत्रिम बुद्धिमत्ता",
        "diabetes": "मधुमेह",
        "prediction": "पूर्वानुमान",
        "dataset": "डेटासेट",
        "model": "मॉडल",
        "method": "विधि",
        "methodology": "कार्यप्रणाली",
        "results": "परिणाम",
        "accuracy": "सटीकता",
        "limitation": "सीमा",
        "limitations": "सीमाएं",
        "future work": "भविष्य का काम",
        "classification": "वर्गीकरण",
        "detection": "पहचान",
        "evidence": "साक्ष्य",
        "confidence": "विश्वास",
        "problem": "समस्या",
        "findings": "निष्कर्ष",
        "conclusion": "निष्कर्ष",
        "compares": "तुलना करता है",
        "main idea": "मुख्य विचार",
        "in simple words": "सरल शब्दों में",
        "simple explanation": "सरल व्याख्या",
        "how they did it": "उन्होंने यह कैसे किया",
        "how it works": "यह कैसे काम करता है",
        "what it found": "इसने क्या पाया",
        "what they found": "उन्होंने क्या पाया",
        "important caution": "महत्वपूर्ण सावधानी",
        "why it matters": "यह क्यों महत्वपूर्ण है",
        "what to check next": "आगे क्या जांचें",
        "takeaway": "मुख्य बात",
        "what to remember": "याद रखने वाली बात",
        "title": "शीर्षक",
        "tldr": "संक्षिप्त सार",
        "the": "",
        "a": "एक",
        "with": "के साथ",
        "and": "और",
        "for": "के लिए",
        "evaluates": "मूल्यांकन करता है",
        "better": "बेहतर",
        "than": "से",
        "external validation": "बाहरी सत्यापन",
        "discusses": "चर्चा करता है",
        "models": "मॉडल",
        "recall": "रिकॉल",
        "precision": "प्रिसिजन",
        "interpretability": "व्याख्येयता",
        "uses": "उपयोग करता है",
        "improves": "सुधारता है",
        "shows": "दिखाता है",
        "show": "दिखाते हैं",
    },
    "ar": {
        "this paper": "تدرس هذه الورقة",
        "this study": "تدرس هذه الدراسة",
        "we introduce": "نقدم",
        "we propose": "نقترح",
        "machine learning": "تعلم الآلة",
        "logistic regression": "الانحدار اللوجستي",
        "deep learning": "التعلم العميق",
        "neural networks": "الشبكات العصبية",
        "artificial intelligence": "الذكاء الاصطناعي",
        "diabetes": "السكري",
        "prediction": "التنبؤ",
        "dataset": "مجموعة البيانات",
        "model": "نموذج",
        "method": "طريقة",
        "methodology": "المنهجية",
        "results": "النتائج",
        "accuracy": "الدقة",
        "limitation": "قيد",
        "limitations": "قيود",
        "future work": "عمل مستقبلي",
        "classification": "التصنيف",
        "detection": "الكشف",
        "evidence": "الدليل",
        "confidence": "الثقة",
        "problem": "المشكلة",
        "findings": "النتائج",
        "conclusion": "الخلاصة",
        "compares": "يقارن",
        "main idea": "الفكرة الرئيسية",
        "in simple words": "بكلمات بسيطة",
        "simple explanation": "شرح مبسط",
        "how they did it": "كيف فعلوا ذلك",
        "how it works": "كيف يعمل",
        "what it found": "ما الذي وجده",
        "what they found": "ما الذي وجدوه",
        "important caution": "تنبيه مهم",
        "why it matters": "لماذا يهم",
        "what to check next": "ما يجب فحصه بعد ذلك",
        "takeaway": "الخلاصة الأساسية",
        "what to remember": "ما يجب تذكره",
        "title": "العنوان",
        "tldr": "ملخص قصير",
        "the": "",
        "a": "",
        "with": "مع",
        "and": "و",
        "for": "لـ",
        "evaluates": "يقيم",
        "better": "أفضل",
        "than": "من",
        "external validation": "تحقق خارجي",
        "discusses": "يناقش",
        "models": "نماذج",
        "recall": "الاسترجاع",
        "precision": "الدقة الإيجابية",
        "interpretability": "قابلية التفسير",
        "uses": "يستخدم",
        "improves": "يحسن",
        "shows": "يوضح",
        "show": "توضح",
    },
    "es": {
        "this paper": "este artículo",
        "this study": "este estudio",
        "we introduce": "presentamos",
        "we propose": "proponemos",
        "machine learning": "aprendizaje automático",
        "logistic regression": "regresión logística",
        "deep learning": "aprendizaje profundo",
        "deepfake": "deepfake",
        "frequency-aware": "consciente de frecuencia",
        "attention": "atención",
        "spatial encoder": "codificador espacial",
        "dual-branch": "doble rama",
        "dual-branch architecture": "arquitectura de doble rama",
        "combines": "combina",
        "that combines": "que combina",
        "architecture": "arquitectura",
        "is evaluated": "se evalúa",
        "is evaluated on": "se evalúa en",
        "evaluated": "evaluado",
        "reports": "reporta",
        "outperforming": "superando",
        "outperforming previous baselines": "superando líneas base anteriores",
        "previous": "anteriores",
        "baselines": "líneas base",
        "cross-dataset": "entre conjuntos de datos",
        "available": "disponible",
        "code": "código",
        "ablation": "ablación",
        "robustness": "robustez",
        "is robustness": "es la robustez",
        "against": "frente a",
        "messaging-app re-encoding": "recodificación de aplicaciones de mensajería",
        "the work reports": "el trabajo reporta",
        "neural networks": "redes neuronales",
        "artificial intelligence": "inteligencia artificial",
        "diabetes": "diabetes",
        "prediction": "predicción",
        "dataset": "conjunto de datos",
        "model": "modelo",
        "method": "método",
        "methodology": "metodología",
        "results": "resultados",
        "accuracy": "precisión",
        "limitation": "limitación",
        "limitations": "limitaciones",
        "future work": "trabajo futuro",
        "classification": "clasificación",
        "detection": "detección",
        "evidence": "evidencia",
        "confidence": "confianza",
        "problem": "problema",
        "findings": "hallazgos",
        "conclusion": "conclusión",
        "compares": "compara",
        "main idea": "idea principal",
        "in simple words": "en palabras simples",
        "simple explanation": "explicación simple",
        "how they did it": "cómo lo hicieron",
        "how it works": "cómo funciona",
        "what it found": "qué encontró",
        "what they found": "qué encontraron",
        "important caution": "precaución importante",
        "why it matters": "por qué importa",
        "what to check next": "qué revisar después",
        "takeaway": "punto clave",
        "what to remember": "qué recordar",
        "title": "título",
        "tldr": "resumen breve",
        "the": "el",
        "a": "un",
        "with": "con",
        "and": "y",
        "for": "para",
        "evaluates": "evalúa",
        "better": "mejor",
        "than": "que",
        "external validation": "validación externa",
        "discusses": "discute",
        "models": "modelos",
        "recall": "recall",
        "precision": "precisión",
        "interpretability": "interpretabilidad",
        "uses": "usa",
        "improves": "mejora",
        "shows": "muestra",
        "show": "muestran",
    },
    "zh": {
        "this paper": "本文",
        "this study": "本研究",
        "we introduce": "我们提出",
        "we propose": "我们提出",
        "machine learning": "机器学习",
        "logistic regression": "逻辑回归",
        "deep learning": "深度学习",
        "neural networks": "神经网络",
        "artificial intelligence": "人工智能",
        "diabetes": "糖尿病",
        "prediction": "预测",
        "dataset": "数据集",
        "model": "模型",
        "method": "方法",
        "methodology": "方法论",
        "results": "结果",
        "accuracy": "准确率",
        "limitation": "局限",
        "limitations": "局限",
        "future work": "未来工作",
        "classification": "分类",
        "detection": "检测",
        "evidence": "证据",
        "confidence": "置信度",
        "problem": "问题",
        "findings": "发现",
        "conclusion": "结论",
        "compares": "比较",
        "main idea": "核心观点",
        "in simple words": "简单来说",
        "simple explanation": "简单解释",
        "how they did it": "他们的方法",
        "how it works": "工作方式",
        "what it found": "主要发现",
        "what they found": "他们发现",
        "important caution": "重要注意",
        "why it matters": "重要性",
        "what to check next": "下一步检查",
        "takeaway": "要点",
        "what to remember": "需要记住",
        "title": "标题",
        "tldr": "简短摘要",
        "the": "",
        "a": "",
        "with": "使用",
        "and": "和",
        "for": "用于",
        "evaluates": "评估",
        "better": "更好",
        "than": "比",
        "external validation": "外部验证",
        "discusses": "讨论",
        "models": "模型",
        "recall": "召回率",
        "precision": "精确率",
        "interpretability": "可解释性",
        "uses": "使用",
        "improves": "改进",
        "shows": "显示",
        "show": "显示",
    },
}


def localize_academic_text(text: str, language: str) -> str:
    language_key = language.lower()
    if language_key == "en" or not text or not text.strip():
        return text

    # Prefer a real provider-backed translation. The terminology map remains a
    # best-effort fallback for offline/demo environments and is never the source
    # of truth when a provider returns translated text.
    try:
        from app.services.search.translation import translate_text
        translated_text = translate_text(text, language_key)
        if translated_text and translated_text.strip():
            return translated_text
    except Exception:
        pass

    if language_key not in ACADEMIC_TRANSLATION_TERMS:
        return text
    translated = text
    terms = ACADEMIC_TRANSLATION_TERMS[language_key]
    for source, target in sorted(terms.items(), key=lambda item: len(item[0]), reverse=True):
        translated = re.sub(rf"\b{re.escape(source)}\b", target, translated, flags=re.IGNORECASE)
    return translated


def localize_list(items: list[str], language: str) -> list[str]:
    return [localize_academic_text(item, language) for item in items]


def extract_glossary(content: str, limit: int = 8) -> dict[str, str]:
    phrases = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", content)
    glossary = {}
    for phrase in phrases:
        if len(glossary) >= limit:
            break
        glossary[phrase] = f"{phrase} is an important concept referenced in the paper."
    for acronym, expansion in ACRONYM_MAP.items():
        if acronym in content and len(glossary) < limit:
            glossary[acronym] = expansion
    return glossary


def infer_difficulty(content: str) -> tuple[str, list[str]]:
    lowered = content.lower()
    score = 0
    if any(token in lowered for token in ("theorem", "proof", "optimization", "ablation", "transformer")):
        score += 2
    if any(token in lowered for token in ("p-value", "confidence interval", "bayesian", "eigen")):
        score += 2
    if len(content.split()) > 900:
        score += 1
    if score >= 4:
        return "Expert", ["Statistics", "Machine Learning", "Research Methods"]
    if score >= 2:
        return "Medium", ["Research Methods", "Domain Basics"]
    return "Easy", ["Basic academic reading"]


def extract_contributions_and_limitations(content: str) -> tuple[list[str], list[str]]:
    sentences = re.split(r"(?<=[.!?])\s+", content)
    contributions = [sentence.strip() for sentence in sentences if any(key in sentence.lower() for key in ("we propose", "we introduce", "our contribution", "we present"))][:4]
    limitations = [sentence.strip() for sentence in sentences if any(key in sentence.lower() for key in ("limitation", "future work", "challenge", "constraint"))][:4]
    return contributions or sentences[:2], limitations or ["Limitations are not stated explicitly."]


def study_limitation_severity(content: str, limitations: list[str]) -> float:
    lowered = content.lower()
    severity = 0.25
    severity += 0.15 if any("small sample" in item.lower() for item in limitations) else 0.0
    severity += 0.2 if any(token in lowered for token in ("bias", "noisy", "constraint", "limited")) else 0.0
    severity += 0.2 if "future work" in lowered and "limitation" in lowered else 0.0
    severity += 0.1 if "single dataset" in lowered or "single-center" in lowered else 0.0
    return round(min(severity, 1.0), 2)


def extract_datasets(content: str) -> list[str]:
    matches = re.findall(r"\b([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,2}\s+(?:dataset|benchmark|corpus))\b", content, re.IGNORECASE)
    return [match.strip() for match in list(dict.fromkeys(matches))[:6]]


def reproducibility_checklist(content: str) -> dict[str, bool]:
    lowered = content.lower()
    return {
        "dataset_named": any(word in lowered for word in ("dataset", "benchmark", "corpus")),
        "metrics_reported": any(word in lowered for word in ("accuracy", "f1", "auc", "precision", "recall")),
        "baselines_reported": any(word in lowered for word in ("baseline", "compared with", "outperforms")),
        "limitations_discussed": "limitation" in lowered or "future work" in lowered,
        "open_access_or_code": any(word in lowered for word in ("github", "open access", "code available")),
    }


def funding_and_coi(content: str) -> list[str]:
    lowered = content.lower()
    findings = []
    if "funded by" in lowered or "supported by" in lowered:
        findings.append("Funding disclosure mentioned")
    if "conflict of interest" in lowered or "competing interest" in lowered:
        findings.append("COI disclosure mentioned")
    return findings or ["No clear funding/COI disclosure detected"]


def freshness_indicator(year_text: str | int | None) -> str:
    if year_text is None:
        return "Unknown"
    year = int(year_text)
    if year >= 2025:
        return "Very recent"
    if year >= 2022:
        return "Recent"
    if year >= 2018:
        return "Established"
    return "Older but potentially foundational"


def auto_outline(title: str) -> list[str]:
    return [
        f"Problem framing for {title}",
        "Method overview",
        "Results and evidence",
        "Limitations and future work",
    ]


def estimate_reading_time(content: str) -> int:
    return max(1, math.ceil(len(content.split()) / 200))


def related_work_summary(content: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
    related = [
        sentence for sentence in sentences
        if any(token in sentence.lower() for token in ("prior", "previous", "existing", "related work", "baseline", "compared with"))
    ]
    if related:
        return " ".join(related[:2])
    if len(sentences) >= 2:
        return f"This paper positions itself against earlier work by contrasting its method with: {sentences[1]}"
    return "Related work is not explicitly described in the provided content."


def acronym_expansions(content: str) -> dict[str, str]:
    found = {}
    for acronym, expansion in ACRONYM_MAP.items():
        if acronym in content:
            found[acronym] = expansion
    return found


def statistical_flags(content: str) -> list[str]:
    lowered = content.lower()
    flags = []
    if "p <" in lowered or "p-value" in lowered:
        flags.append("Statistical significance reported")
    if "confidence interval" in lowered:
        flags.append("Confidence interval reported")
    if "small sample" in lowered:
        flags.append("Small sample size caveat")
    return flags or ["No explicit statistical signal detected"]


def narration_script(title: str, tldr: str, bullet_summary: list[str], conclusion: str) -> dict[str, str]:
    plain_text = " ".join([f"Title: {title}.", f"TLDR: {tldr}.", *bullet_summary[:3], f"Conclusion: {conclusion}."])
    ssml = (
        "<speak>"
        f"<p><emphasis level='moderate'>{title}</emphasis></p>"
        f"<p>{tldr}</p>"
        + "".join(f"<p>{point}</p>" for point in bullet_summary[:3])
        + f"<p>{conclusion}</p>"
        + "</speak>"
    )
    return {"plain_text": plain_text, "ssml": ssml}


def translate_summary_payload(
    *,
    tldr: str,
    structured_summary: dict[str, str],
    contributions: list[str],
    target_languages: list[str],
) -> dict[str, dict[str, str | list[str]]]:
    translations: dict[str, dict[str, str | list[str]]] = {}
    for language in target_languages:
        translations[language] = {
            "tldr": localize_academic_text(tldr, language),
            "problem": localize_academic_text(structured_summary.get("problem", ""), language),
            "methodology": localize_academic_text(structured_summary.get("methodology", ""), language),
            "findings": localize_academic_text(structured_summary.get("findings", ""), language),
            "conclusion": localize_academic_text(structured_summary.get("conclusion", ""), language),
            "contributions": localize_list(contributions[:3], language),
        }
    return translations


def explain_paragraph(paragraph: str, audience: str = "beginner") -> tuple[str, list[str]]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", paragraph) if sentence.strip()]
    lead = sentences[0] if sentences else paragraph.strip()
    if audience.lower() == "expert":
        explanation = f"This paragraph argues that {lead.lower()}"
    else:
        explanation = f"In simple words, this paragraph says: {lead}"
    points = sentences[:3] if sentences else [paragraph.strip()]
    return explanation, points


def exam_qa(title: str, content: str) -> list[dict[str, str]]:
    contributions, limitations = extract_contributions_and_limitations(content)
    return [
        {"question": f"What problem does {title} address?", "answer": contributions[0]},
        {"question": "What is a key limitation of the paper?", "answer": limitations[0]},
    ]


def key_figure_caption(content: str) -> str | None:
    match = re.search(r"(figure\s+\d+[:.\-]?\s*[^.\n]{10,180})", content, re.IGNORECASE)
    return match.group(1).strip() if match else None


def methodology_and_results_boxes(content: str) -> tuple[str, str]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
    methodology = next((sentence for sentence in sentences if any(word in sentence.lower() for word in ("method", "approach", "framework", "model", "pipeline"))), sentences[0] if sentences else "")
    results = next((sentence for sentence in sentences if any(word in sentence.lower() for word in ("result", "improve", "outperform", "accuracy", "f1"))), sentences[1] if len(sentences) > 1 else methodology)
    return methodology, results
