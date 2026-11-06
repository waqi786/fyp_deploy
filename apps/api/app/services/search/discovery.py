import re
from collections import Counter, defaultdict

from app.schemas.paper import PaperRecord
from app.services.retrieval.vector_store import FaissLiteStore


TRANSLATIONS = {
    "ur": {
        "مشین لرننگ": "machine learning",
        "مصنوعی ذہانت": "artificial intelligence",
        "ڈیپ فیک": "deepfake",
        "شناخت": "detection",
        "تحقیق": "research",
        "مقالہ": "paper",
        "مصنف": "author",
        "زبان": "language",
        "خلاصہ": "summary",
        "سرچ": "search",
        "تلاش": "search",
        "اعصابی نیٹ ورک": "neural networks",
        "کینسر": "cancer",
        "پھیپھڑے": "lung",
        "machine learning": "machine learning",
        "zaban": "language",
        "tashkhees": "diagnosis",
        "taleem": "education",
    },
    "hi": {
        "मशीन लर्निंग": "machine learning",
        "कृत्रिम बुद्धिमत्ता": "artificial intelligence",
        "डीपफेक": "deepfake",
        "पहचान": "detection",
        "शोध": "research",
        "पेपर": "paper",
        "लेखक": "author",
        "भाषा": "language",
        "सारांश": "summary",
        "कैंसर": "cancer",
    },
    "ar": {
        "تعلم الآلة": "machine learning",
        "التعلم الآلي": "machine learning",
        "الذكاء الاصطناعي": "artificial intelligence",
        "التزييف العميق": "deepfake",
        "كشف": "detection",
        "بحث": "research",
        "ورقة": "paper",
        "مؤلف": "author",
        "لغة": "language",
        "ملخص": "summary",
        "سرطان": "cancer",
    },
    "es": {
        "aprendizaje automatico": "machine learning",
        "aprendizaje automático": "machine learning",
        "deteccion": "detection",
        "detección": "detection",
        "busqueda": "search",
        "búsqueda": "search",
        "autor": "author",
        "idioma": "language",
        "resumen": "summary",
        "cancer": "cancer",
        "cáncer": "cancer",
    },
    "zh": {
        "机器学习": "machine learning",
        "深度伪造": "deepfake",
        "检测": "detection",
        "研究": "research",
        "作者": "author",
        "语言": "language",
        "摘要": "summary",
        "癌症": "cancer",
    }
}

COMMON_CORRECTIONS = {
    "retrival": "retrieval",
    "transfomer": "transformer",
    "acadmic": "academic",
    "diagosis": "diagnosis",
}

# Clean multilingual query terms. The older table above may contain mojibake from
# copied UI text, so this assignment intentionally overrides it with ASCII-safe
# Unicode escapes that Python reads as real Urdu/Hindi/Arabic/Chinese phrases.
TRANSLATIONS = {
    "ur": {
        "\u0645\u0635\u0646\u0648\u0639\u06cc \u0630\u06c1\u0627\u0646\u062a": "artificial intelligence",
        "\u0645\u0635\u0646\u0648\u0639\u06cc \u0630\u06c1\u06cc\u0646\u062a": "artificial intelligence",
        "\u0645\u0634\u06cc\u0646 \u0644\u0631\u0646\u0646\u06af": "machine learning",
        "\u06af\u06c1\u0631\u06cc \u0633\u06cc\u06a9\u06be": "deep learning",
        "\u0627\u0639\u0635\u0627\u0628\u06cc \u0646\u06cc\u0679 \u0648\u0631\u06a9": "neural networks",
        "\u0688\u06cc\u067e \u0641\u06cc\u06a9": "deepfake",
        "\u062a\u0634\u062e\u06cc\u0635": "diagnosis",
        "\u0634\u0646\u0627\u062e\u062a": "detection",
        "\u0630\u06cc\u0627\u0628\u06cc\u0637\u0633": "diabetes",
        "\u0633\u0631\u0637\u0627\u0646": "cancer",
        "\u067e\u06be\u06cc\u067e\u06be\u0691\u0648\u06ba": "lung",
        "\u067e\u06cc\u0634 \u06af\u0648\u0626\u06cc": "prediction",
        "\u062a\u062d\u0642\u06cc\u0642": "research",
        "\u0645\u0642\u0627\u0644\u06c1": "paper",
        "\u0645\u0636\u0645\u0648\u0646": "paper",
        "\u0645\u0635\u0646\u0641": "author",
        "\u0632\u0628\u0627\u0646": "language",
        "\u062e\u0644\u0627\u0635\u06c1": "summary",
        "\u0633\u0631\u0686": "search",
        "\u062a\u0644\u0627\u0634": "search",
        "masnoi zahanat": "artificial intelligence",
        "machine learning": "machine learning",
        "zaban": "language",
        "tashkhees": "diagnosis",
        "taleem": "education",
    },
    "hi": {
        "\u0915\u0943\u0924\u094d\u0930\u093f\u092e \u092c\u0941\u0926\u094d\u0927\u093f\u092e\u0924\u094d\u0924\u093e": "artificial intelligence",
        "\u092e\u0936\u0940\u0928 \u0932\u0930\u094d\u0928\u093f\u0902\u0917": "machine learning",
        "\u0917\u0939\u0930\u0940 \u0938\u0940\u0916": "deep learning",
        "\u0928\u094d\u092f\u0942\u0930\u0932 \u0928\u0947\u091f\u0935\u0930\u094d\u0915": "neural networks",
        "\u0921\u0940\u092a\u092b\u0947\u0915": "deepfake",
        "\u092a\u0939\u091a\u093e\u0928": "detection",
        "\u0928\u093f\u0926\u093e\u0928": "diagnosis",
        "\u092e\u0927\u0941\u092e\u0947\u0939": "diabetes",
        "\u0915\u0948\u0902\u0938\u0930": "cancer",
        "\u092b\u0947\u092b\u0921\u093c\u093e": "lung",
        "\u092a\u0942\u0930\u094d\u0935\u093e\u0928\u0941\u092e\u093e\u0928": "prediction",
        "\u092d\u0935\u093f\u0937\u094d\u092f\u0935\u093e\u0923\u0940": "prediction",
        "\u0936\u094b\u0927": "research",
        "\u092a\u0947\u092a\u0930": "paper",
        "\u0932\u0947\u0916\u0915": "author",
        "\u092d\u093e\u0937\u093e": "language",
        "\u0938\u093e\u0930\u093e\u0902\u0936": "summary",
    },
    "ar": {
        "\u0627\u0644\u0630\u0643\u0627\u0621 \u0627\u0644\u0627\u0635\u0637\u0646\u0627\u0639\u064a": "artificial intelligence",
        "\u0630\u0643\u0627\u0621 \u0627\u0635\u0637\u0646\u0627\u0639\u064a": "artificial intelligence",
        "\u062a\u0639\u0644\u0645 \u0627\u0644\u0622\u0644\u0629": "machine learning",
        "\u0627\u0644\u062a\u0639\u0644\u0645 \u0627\u0644\u0622\u0644\u064a": "machine learning",
        "\u0627\u0644\u062a\u0639\u0644\u0645 \u0627\u0644\u0639\u0645\u064a\u0642": "deep learning",
        "\u0627\u0644\u0634\u0628\u0643\u0627\u062a \u0627\u0644\u0639\u0635\u0628\u064a\u0629": "neural networks",
        "\u0627\u0644\u062a\u0632\u064a\u064a\u0641 \u0627\u0644\u0639\u0645\u064a\u0642": "deepfake",
        "\u0643\u0634\u0641": "detection",
        "\u062a\u0634\u062e\u064a\u0635": "diagnosis",
        "\u0627\u0644\u0633\u0643\u0631\u064a": "diabetes",
        "\u0633\u0643\u0631\u064a": "diabetes",
        "\u0633\u0631\u0637\u0627\u0646": "cancer",
        "\u0627\u0644\u0631\u0626\u0629": "lung",
        "\u062a\u0646\u0628\u0624": "prediction",
        "\u062a\u0648\u0642\u0639": "prediction",
        "\u0628\u062d\u062b": "research",
        "\u0648\u0631\u0642\u0629": "paper",
        "\u0623\u0648\u0631\u0627\u0642": "papers",
        "\u0645\u0624\u0644\u0641": "author",
        "\u0643\u0627\u062a\u0628": "author",
        "\u0644\u063a\u0629": "language",
        "\u0645\u0644\u062e\u0635": "summary",
    },
    "es": {
        "inteligencia artificial": "artificial intelligence",
        "aprendizaje automatico": "machine learning",
        "aprendizaje autom\u00e1tico": "machine learning",
        "aprendizaje profundo": "deep learning",
        "redes neuronales": "neural networks",
        "deteccion": "detection",
        "detecci\u00f3n": "detection",
        "diabetes": "diabetes",
        "prediccion": "prediction",
        "predicci\u00f3n": "prediction",
        "busqueda": "search",
        "b\u00fasqueda": "search",
        "autor": "author",
        "idioma": "language",
        "resumen": "summary",
        "cancer": "cancer",
        "c\u00e1ncer": "cancer",
    },
    "zh": {
        "\u4eba\u5de5\u667a\u80fd": "artificial intelligence",
        "\u673a\u5668\u5b66\u4e60": "machine learning",
        "\u6a5f\u5668\u5b78\u7fd2": "machine learning",
        "\u6df1\u5ea6\u5b66\u4e60": "deep learning",
        "\u795e\u7ecf\u7f51\u7edc": "neural networks",
        "\u795e\u7d93\u7db2\u7d61": "neural networks",
        "\u6df1\u5ea6\u4f2a\u9020": "deepfake",
        "\u6aa2\u6e2c": "detection",
        "\u68c0\u6d4b": "detection",
        "\u8bca\u65ad": "diagnosis",
        "\u7cd6\u5c3f\u75c5": "diabetes",
        "\u764c\u75c7": "cancer",
        "\u80ba": "lung",
        "\u9884\u6d4b": "prediction",
        "\u9810\u6e2c": "prediction",
        "\u7814\u7a76": "research",
        "\u8bba\u6587": "paper",
        "\u8ad6\u6587": "paper",
        "\u4f5c\u8005": "author",
        "\u8bed\u8a00": "language",
        "\u8a9e\u8a00": "language",
        "\u6458\u8981": "summary",
    },
}


def normalize_natural_language_query(query: str, language: str) -> tuple[str, str | None]:
    normalized = " ".join(query.strip().split())
    if not normalized:
        return "", None

    language_key = language.lower()
    translated = _strip_query_diacritics(normalized)
    changed = False
    for _, source, target in _translation_candidates(language_key):
        source_key = _strip_query_diacritics(source.casefold())
        next_value = re.sub(re.escape(source_key), f" {target} ", translated, flags=re.IGNORECASE)
        if next_value != translated:
            translated = next_value
            changed = True

    translated = _clean_normalized_query(translated)
    if not changed:
        return _clean_normalized_query(normalized), None
    return translated, translated


def _translation_candidates(language_key: str) -> list[tuple[str, str, str]]:
    ordered_languages = []
    if language_key in TRANSLATIONS:
        ordered_languages.append(language_key)
    ordered_languages.extend(code for code in TRANSLATIONS if code not in ordered_languages)
    candidates = [
        (code, source, target)
        for code in ordered_languages
        for source, target in TRANSLATIONS[code].items()
    ]
    return sorted(candidates, key=lambda item: len(item[1]), reverse=True)


def _strip_query_diacritics(text: str) -> str:
    # Arabic/Urdu marks are optional in user input; removing them improves exact phrase matching.
    return re.sub(r"[\u064b-\u065f\u0670]", "", text)


def _clean_normalized_query(query: str) -> str:
    query = re.sub(r"\s+", " ", query).strip()
    query = re.sub(r"\s+([,.;:/])", r"\1", query)
    query = re.sub(r"([(/])\s+", r"\1", query)
    query = re.sub(r"\s+([)])", r"\1", query)
    return query


def interpret_search_query(
    query: str,
    *,
    language: str,
    query_type: str,
    voice_transcript: str | None = None,
    image_caption: str | None = None,
) -> dict[str, str | None]:
    raw_query = voice_transcript if query_type == "voice" and voice_transcript else query
    raw_query = image_caption if query_type == "image" and image_caption else raw_query
    normalized, translated = normalize_natural_language_query(raw_query, language)
    corrected = normalized
    for wrong, right in COMMON_CORRECTIONS.items():
        corrected = re.sub(rf"\b{wrong}\b", right, corrected, flags=re.IGNORECASE)
    boolean_query = _build_boolean_query(corrected)
    return {
        "interpreted_query": corrected,
        "normalized_query": corrected,
        "translated_query": translated,
        "corrected_query": corrected if corrected != normalized else None,
        "boolean_query": boolean_query,
    }


def apply_filters(
    papers: list[PaperRecord],
    *,
    min_citations: int,
    open_access_only: bool,
    study_type: str | None,
    quartile: str | None,
    sample_size_min: int | None,
    year_from: int | None = None,
    year_to: int | None = None,
    methodology: str | None = None,
    author: str | None = None,
    venue: str | None = None,
    institution: str | None = None,
    dataset: str | None = None,
    peer_reviewed_only: bool = False,
    preprint_only: bool = False,
    include_retracted: bool = False,
    paper_language: str | None = None,
) -> list[PaperRecord]:
    filtered = []
    for paper in papers:
        if paper_language and paper.language.casefold() != paper_language.casefold():
            continue
        if paper.citation_count < min_citations:
            continue
        if open_access_only and not paper.is_open_access:
            continue
        if study_type and not _study_type_matches(study_type, paper.study_type or ""):
            continue
        if quartile and (paper.journal_quartile or "").lower() != quartile.lower():
            continue
        if sample_size_min is not None and (paper.sample_size or 0) < sample_size_min:
            continue
        if year_from is not None and (paper.year or 0) < year_from:
            continue
        if year_to is not None and (paper.year or 9999) > year_to:
            continue
        if methodology and methodology.lower() not in {item.lower() for item in paper.methodologies}:
            continue
        if author and not any(_author_matches(author, candidate.get("name", "")) for candidate in paper.authors):
            continue
        if venue and venue.lower() not in (paper.venue or "").lower():
            continue
        if institution and not any(institution.lower() in value.lower() for value in paper.institutions):
            continue
        if dataset and not any(dataset.lower() in value.lower() for value in paper.datasets):
            continue
        if peer_reviewed_only and paper.is_preprint:
            continue
        if preprint_only and not paper.is_preprint:
            continue
        if not include_retracted and paper.is_retracted:
            continue
        filtered.append(paper)
    return filtered


def enrich_search_results(
    query: str,
    papers: list[PaperRecord],
    *,
    search_mode: str = "hybrid",
    sort_by: str = "relevance",
) -> tuple[list[PaperRecord], dict[str, list[str]], list[str], list[str]]:
    query_terms = _intent_terms(query)
    clusters: defaultdict[str, list[str]] = defaultdict(list)
    suggestions = _suggest_queries(query, papers)
    trending_topics = _trending_topics(papers)
    vector_scores = semantic_vector_scores(query, papers)

    for paper in papers:
        abstract = (paper.abstract or "").lower()
        title = paper.title.lower()
        paper_terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", f"{title} {abstract}"))
        overlap = len(query_terms & paper_terms)
        lexical_dense_score = min(1.0, overlap / max(len(query_terms), 1))
        vector_score = vector_scores.get(paper.paper_id, 0.0)
        dense_score = max(lexical_dense_score, vector_score)
        keyword_score = min(1.0, sum(term in title for term in query_terms) / max(len(query_terms), 1))
        coverage_score = _query_coverage_score(query_terms, f"{title} {abstract}")
        citation_bonus = min(1.0, paper.citation_count / 250)
        oa_bonus = 0.1 if paper.is_open_access else 0.0
        if search_mode == "keyword":
            rank_score = (0.7 * keyword_score) + (0.2 * citation_bonus) + oa_bonus
        elif search_mode == "semantic":
            rank_score = (0.7 * dense_score) + (0.2 * citation_bonus) + oa_bonus
        else:
            rank_score = (0.4 * keyword_score) + (0.35 * dense_score) + (0.15 * citation_bonus) + oa_bonus
        paper_text = f"{title} {abstract}"
        rank_score = (rank_score * 0.72) + (coverage_score * 0.28)
        rank_score = _apply_critical_intent_adjustments(rank_score, query_terms, paper_text)
        if paper.is_retracted:
            rank_score *= 0.18
        if query_terms and coverage_score < 0.35:
            rank_score *= 0.35
        elif query_terms and coverage_score < 0.55:
            rank_score *= 0.65
        paper.ranking_score = round(max(0.0, min(1.0, rank_score)), 3)
        label = infer_cluster_label(paper)
        paper.cluster_label = label
        paper.result_badges = infer_badges(paper)
        paper.micro_summary = build_micro_summary(paper)
        paper.author_match_score = _author_match_score(paper)
        paper.plagiarism_risk_score = _plagiarism_risk_score(paper, papers)
        paper.duplicate_warning = "Potential duplicate wording" if paper.plagiarism_risk_score >= 0.8 else None
        paper.recommendation_reason = _recommendation_reason(paper)
        clusters[label].append(paper.paper_id)

    ranked = sorted(
        papers,
        key=lambda item: _sort_key(item, sort_by),
        reverse=True,
    )
    if sort_by == "relevance":
        ranked = _prioritize_critical_intent_matches(query_terms, ranked)
    return ranked, dict(clusters), suggestions, trending_topics


def search_relevance_score(query: str, paper: PaperRecord) -> float:
    query_terms = _intent_terms(query)
    if not query_terms:
        return 1.0
    text = _paper_semantic_text(paper).lower()
    coverage = _query_coverage_score(query_terms, text)
    title = paper.title.lower()
    title_hits = sum(1 for term in query_terms if any(re.search(rf"\b{re.escape(alias)}\b", title) for alias in _term_aliases(term)))
    title_score = title_hits / max(len(query_terms), 1)
    phrase_bonus = _phrase_bonus(query, text)
    critical_bonus = 0.0
    if "deepfake" in query_terms and _has_term_alias("deepfake", text):
        critical_bonus += 0.18
    if "rag" in query_terms and _has_term_alias("rag", text):
        critical_bonus += 0.18
    if {"urdu", "sentiment"} <= query_terms and "urdu" in text and "sentiment" in text:
        critical_bonus += 0.18
    if {"lung", "cancer", "immunotherapy"} <= query_terms and all(_has_term_alias(term, text) for term in ["lung", "cancer", "immunotherapy"]):
        critical_bonus += 0.16
    if {"protein", "graph"} <= query_terms and _has_term_alias("protein", text) and _has_term_alias("graph", text):
        critical_bonus += 0.16
    score = (coverage * 0.68) + (title_score * 0.22) + phrase_bonus + critical_bonus
    if _looks_like_abstract_only_record(paper):
        score *= 0.52
    if paper.is_retracted:
        score *= 0.18
    return round(min(1.0, score), 3)


def _phrase_bonus(query: str, paper_text: str) -> float:
    lowered = query.lower()
    phrase_map = {
        "convolutional neural": ["convolutional neural", "cnn", "convolutional network"],
        "sentiment analysis": ["sentiment analysis", "sentiment classification", "opinion mining"],
        "lung cancer": ["lung cancer", "non-small-cell lung cancer", "nsclc"],
        "protein folding": ["protein folding", "protein structure", "protein function"],
        "retrieval augmented": ["retrieval augmented", "retrieval-augmented", "rag"],
    }
    bonus = 0.0
    for query_phrase, aliases in phrase_map.items():
        if query_phrase in lowered and any(alias in paper_text for alias in aliases):
            bonus += 0.08
    return min(0.18, bonus)


def _intent_terms(query: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "against",
        "analysis",
        "and",
        "are",
        "based",
        "for",
        "from",
        "how",
        "into",
        "latest",
        "method",
        "methods",
        "of",
        "on",
        "paper",
        "papers",
        "research",
        "study",
        "the",
        "this",
        "using",
        "with",
    }
    return {
        term
        for term in re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", query.lower())
        if len(term) > 2 and term not in stopwords
    }


def _query_coverage_score(query_terms: set[str], paper_text: str) -> float:
    if not query_terms:
        return 1.0
    paper_text = paper_text.lower()
    matched = 0
    for term in query_terms:
        aliases = _term_aliases(term)
        if any(re.search(rf"\b{re.escape(alias)}\b", paper_text) for alias in aliases):
            matched += 1
    return round(matched / max(len(query_terms), 1), 3)


def _apply_critical_intent_adjustments(rank_score: float, query_terms: set[str], paper_text: str) -> float:
    adjusted = rank_score
    if "rag" in query_terms:
        adjusted = adjusted + 0.22 if _has_term_alias("rag", paper_text) else adjusted * 0.38
    if "deepfake" in query_terms:
        adjusted = adjusted + 0.12 if _has_term_alias("deepfake", paper_text) else adjusted * 0.45
    if "protein" in query_terms and "graph" in query_terms:
        if _has_term_alias("protein", paper_text) and _has_term_alias("graph", paper_text):
            adjusted += 0.14
        else:
            adjusted *= 0.55
    if {"lung", "cancer", "immunotherapy"} <= query_terms:
        if all(_has_term_alias(term, paper_text) for term in ["lung", "cancer", "immunotherapy"]):
            adjusted += 0.12
        else:
            adjusted *= 0.5
    return adjusted


def _prioritize_critical_intent_matches(query_terms: set[str], ranked: list[PaperRecord]) -> list[PaperRecord]:
    if "rag" in query_terms:
        matches = [paper for paper in ranked if _has_term_alias("rag", _paper_semantic_text(paper))]
        if matches:
            return matches
    if "protein" in query_terms and "graph" in query_terms:
        matches = [
            paper
            for paper in ranked
            if _has_term_alias("protein", _paper_semantic_text(paper)) and _has_term_alias("graph", _paper_semantic_text(paper))
        ]
        if matches:
            return matches
    if {"lung", "cancer", "immunotherapy"} <= query_terms:
        matches = [
            paper
            for paper in ranked
            if all(_has_term_alias(term, _paper_semantic_text(paper)) for term in ["lung", "cancer", "immunotherapy"])
        ]
        if matches:
            return matches
    return ranked


def _looks_like_abstract_only_record(paper: PaperRecord) -> bool:
    title = paper.title.strip().lower()
    venue = (paper.venue or "").lower()
    return title.startswith("abstract ") or title.startswith("abstract:") or "conference abstract" in venue


def _study_type_matches(requested: str, actual: str) -> bool:
    requested_key = requested.lower().replace("-", "_").replace(" ", "_")
    actual_key = actual.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "rct": {"rct", "randomized_controlled_trial", "randomized", "clinical"},
        "randomized_controlled_trial": {"rct", "randomized_controlled_trial", "randomized", "clinical"},
        "meta_analysis": {"meta_analysis", "systematic_review", "review"},
        "case_study": {"case_study", "case_report", "clinical"},
        "review": {"review", "survey", "meta_analysis", "systematic_review"},
        "protocol": {"protocol", "registered_protocol", "study_protocol"},
        "experimental": {"experimental", "benchmark", "experiment"},
        "clinical": {"clinical", "rct", "case_study"},
        "general": {"general"},
    }
    return actual_key in aliases.get(requested_key, {requested_key})


def _has_term_alias(term: str, paper_text: str) -> bool:
    lowered = paper_text.lower()
    if term == "rag":
        return bool(
            re.search(r"\brag\b", lowered)
            or re.search(r"\bretrieval[-\s]?augmented\b", lowered)
            or re.search(r"\bretriever[-\s]?augmented\b", lowered)
        )
    return any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in _term_aliases(term))


def _term_aliases(term: str) -> set[str]:
    aliases = {term}
    if term == "rag":
        aliases.update({"retrieval", "retriever", "retrieval-augmented", "retrieval augmented generation"})
    if term == "cnn":
        aliases.update({"convolutional", "convolutional neural network", "convolutional neural networks"})
    if term == "deepfake":
        aliases.update({"deepfakes", "face forgery", "facial forgery", "face manipulation", "manipulated facial", "synthetic media", "deep fake"})
    if term == "detection":
        aliases.update({"detect", "detecting", "detector", "classification", "recognition"})
    if term == "sentiment":
        aliases.update({"opinion", "polarity", "sentiment analysis", "sentiment classification"})
    if term == "urdu":
        aliases.update({"urdu", "roman urdu", "urdu language"})
    if term == "transformer":
        aliases.update({"transformers", "bert", "xlm-roberta", "roberta"})
    if term == "language":
        aliases.update({"languages", "lingual", "cross-lingual", "multilingual"})
    if term == "cancer":
        aliases.update({"cancer", "tumor", "tumour", "oncology", "carcinoma"})
    if term == "lung":
        aliases.update({"lung", "pulmonary", "nsclc", "non-small-cell"})
    if term == "immunotherapy":
        aliases.update({"immunotherapy", "immune checkpoint", "checkpoint inhibitor", "nivolumab", "pembrolizumab"})
    if term == "biomarkers":
        aliases.update({"biomarker", "biomarkers", "marker", "markers"})
    if term == "protein":
        aliases.update({"proteins"})
    if term == "graph":
        aliases.update({"graphs"})
    if term == "benchmark":
        aliases.update({"benchmarks", "evaluation"})
    if term == "dataset":
        aliases.update({"datasets", "corpus"})
    return aliases


def semantic_vector_scores(query: str, papers: list[PaperRecord]) -> dict[str, float]:
    store = FaissLiteStore()
    for paper in papers:
        store.add(paper.paper_id, _paper_semantic_text(paper))
    return {hit.chunk_id: round(hit.score, 4) for hit in store.search(query, top_k=max(len(papers), 1))}


def infer_cluster_label(paper: PaperRecord) -> str:
    text = f"{paper.title} {paper.abstract or ''}".lower()
    if "dataset" in text or "benchmark" in text:
        return "Benchmarks"
    if "survey" in text or "review" in text:
        return "Reviews"
    if "clinical" in text or "diagnosis" in text:
        return "Clinical"
    if "graph" in text:
        return "Graph Methods"
    return "Core Research"


def infer_badges(paper: PaperRecord) -> list[str]:
    badges = []
    if paper.is_open_access:
        badges.append("Open Access")
    if paper.is_retracted:
        badges.append("Retracted")
    if paper.year and paper.year >= 2024:
        badges.append("Recent")
    if paper.citation_count >= 100:
        badges.append("Highly Cited")
    if paper.journal_quartile:
        badges.append(paper.journal_quartile.upper())
    if paper.is_preprint:
        badges.append("Preprint")
    if paper.peer_review_status == "peer_reviewed":
        badges.append("Peer Reviewed")
    if paper.datasets:
        badges.append("Dataset Linked")
    if paper.code_repositories:
        badges.append("Code Available")
    return badges


def infer_metadata_fields(paper: PaperRecord) -> PaperRecord:
    text = f"{paper.title} {paper.abstract or ''}"
    lowered = text.lower()
    if not paper.journal_quartile:
        if paper.citation_count >= 200:
            paper.journal_quartile = "q1"
        elif paper.citation_count >= 75:
            paper.journal_quartile = "q2"
        elif paper.citation_count >= 20:
            paper.journal_quartile = "q3"
        else:
            paper.journal_quartile = "q4"
    if not paper.study_type:
        if "randomized controlled trial" in lowered or re.search(r"\brct\b", lowered):
            paper.study_type = "rct"
        elif "meta-analysis" in lowered or "meta analysis" in lowered or "systematic review" in lowered:
            paper.study_type = "meta_analysis"
        elif "case study" in lowered or "case report" in lowered:
            paper.study_type = "case_study"
        elif "protocol" in lowered or "registered report" in lowered:
            paper.study_type = "protocol"
        elif "survey" in lowered or "review" in lowered:
            paper.study_type = "review"
        elif "randomized" in lowered or "clinical" in lowered:
            paper.study_type = "clinical"
        elif "benchmark" in lowered or "experiment" in lowered:
            paper.study_type = "experimental"
        else:
            paper.study_type = "general"
    if paper.sample_size is None:
        match = re.search(r"\b(?:n\s*=\s*(\d+)|(\d+)\s+(?:samples|participants|subjects|patients))\b", lowered)
        if match:
            paper.sample_size = int(next(group for group in match.groups() if group))
    if "retracted" in lowered or "withdrawn" in lowered:
        paper.is_retracted = True
    paper.is_preprint = paper.source == "arxiv" or "preprint" in lowered
    if paper.source in {"pmc", "openalex", "crossref", "semantic_scholar"} and not paper.is_preprint:
        paper.peer_review_status = "peer_reviewed"
    elif paper.is_preprint:
        paper.peer_review_status = "preprint"
    paper.datasets = _extract_datasets(text)
    paper.methodologies = _extract_methodologies(text)
    paper.code_repositories = re.findall(r"https?://github\.com/[^\s)]+", text)
    paper.institutions = _extract_institutions(paper)
    return paper


def build_discovery_facets(
    papers: list[PaperRecord],
    *,
    query: str = "",
    query_type: str = "natural_language",
    image_caption: str | None = None,
) -> dict[str, list | dict]:
    author_edges = []
    author_mentions: defaultdict[str, list[str]] = defaultdict(list)
    institutions = []
    datasets = []
    code_repositories = []
    recommended = []
    citation_expansion_titles = []
    for paper in papers[:12]:
        author_names = [author.get("name", "") for author in paper.authors if author.get("name")]
        if len(author_names) >= 2:
            author_edges.append({"source": author_names[0], "target": author_names[1], "paper_id": paper.paper_id})
        for author in paper.authors:
            name = str(author.get("name", "")).strip()
            affiliation = str(author.get("affiliation") or author.get("institution") or paper.venue or "Unknown").strip()
            if name:
                author_mentions[name].append(affiliation)
        institutions.extend(paper.institutions)
        datasets.extend(paper.datasets)
        code_repositories.extend(paper.code_repositories)
        recommended.append(
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "reason": paper.recommendation_reason or _recommendation_reason(paper),
            }
        )
        if paper.citation_count >= 75:
            citation_expansion_titles.append(paper.title)
    source_coverage = dict(Counter(paper.source for paper in papers))
    return {
        "author_network": author_edges[:12],
        "author_disambiguation": _author_disambiguation(author_mentions),
        "venue_matches": _unique([paper.venue for paper in papers if paper.venue])[:10],
        "institution_matches": _unique(institutions)[:10],
        "dataset_matches": _unique(datasets)[:10],
        "code_repository_matches": _unique(code_repositories)[:10],
        "recommended_papers": recommended[:5],
        "citation_expansion_titles": citation_expansion_titles[:6],
        "co_citation_pairs": _co_citation_pairs(papers),
        "bibliographic_coupling_pairs": _bibliographic_coupling_pairs(papers),
        "figure_search_matches": _figure_search_matches(papers, query=query, query_type=query_type, image_caption=image_caption),
        "source_coverage": source_coverage,
        "search_insights": _search_insights(papers, source_coverage),
    }


def _suggest_queries(query: str, papers: list[PaperRecord]) -> list[str]:
    base = query.strip()
    suggestions = [f"{base} review", f"{base} benchmark", f"{base} open access", f"{base} dataset", f"{base} github"]
    authors = []
    for paper in papers[:5]:
        if paper.authors:
            author = paper.authors[0].get("name")
            if author:
                authors.append(author)
    if authors:
        suggestions.append(f"{base} {authors[0]}")
    return suggestions[:5]


def _trending_topics(papers: list[PaperRecord]) -> list[str]:
    counter = Counter()
    for paper in papers:
        for token in re.findall(r"\b[a-zA-Z][a-zA-Z-]{4,}\b", f"{paper.title} {paper.abstract or ''}".lower()):
            if token not in {"paper", "study", "using", "their", "these", "review"}:
                counter[token] += 1
    return [token.title() for token, _ in counter.most_common(5)]


def build_micro_summary(paper: PaperRecord) -> str:
    abstract_sentence = (paper.abstract or "").split(".")[0].strip()
    if abstract_sentence:
        return f"{paper.title}: {abstract_sentence}."
    return f"{paper.title}: Research result indexed from {paper.source}."


def _paper_semantic_text(paper: PaperRecord) -> str:
    authors = " ".join(str(author.get("name", "")) for author in paper.authors)
    metadata = " ".join([*paper.datasets, *paper.methodologies, *paper.institutions, paper.venue or ""])
    return f"{paper.title} {paper.abstract or ''} {authors} {metadata}".strip()


def _sort_key(paper: PaperRecord, sort_by: str) -> tuple[float, int, int]:
    if sort_by == "citations":
        return (paper.citation_count, paper.year or 0, int(paper.is_open_access))
    if sort_by == "recent":
        return (paper.year or 0, paper.citation_count, int(paper.is_open_access))
    return (paper.ranking_score, paper.citation_count, paper.year or 0)


def _build_boolean_query(query: str) -> str:
    terms = [term for term in re.findall(r"\b[\w-]+\b", query) if len(term) > 2]
    if not terms:
        return query
    return " AND ".join(f"({term})" for term in terms[:6])


def _extract_datasets(text: str) -> list[str]:
    datasets = re.findall(r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*\s+(?:Dataset|Benchmark|Corpus))\b", text)
    return _unique(datasets)


def _extract_methodologies(text: str) -> list[str]:
    lowered = text.lower()
    mapping = {
        r"\bgraph neural networks?\b": "Graph Neural Network",
        r"\btransformers?\b": "Transformer",
        r"\bbm25\b": "BM25",
        r"\brag\b|\bretrieval[-\s]?augmented\b|\bretriever[-\s]?augmented\b": "Retrieval-Augmented Generation",
        r"\brandomized\b": "Randomized Controlled Trial",
        r"\bsurvey\b": "Survey",
        r"\bbenchmark(?:ing|s)?\b": "Benchmarking",
    }
    methods = [label for pattern, label in mapping.items() if re.search(pattern, lowered)]
    return _unique(methods)


def _extract_institutions(paper: PaperRecord) -> list[str]:
    institutions = []
    for author in paper.authors:
        affiliation = author.get("affiliation") or author.get("institution")
        if affiliation:
            institutions.append(str(affiliation))
    if not institutions and paper.venue:
        institutions.append(paper.venue)
    return _unique(institutions)


def _plagiarism_risk_score(paper: PaperRecord, papers: list[PaperRecord]) -> float:
    title_terms = set(re.findall(r"\b[\w-]+\b", paper.title.lower()))
    max_overlap = 0.0
    for other in papers:
        if other.paper_id == paper.paper_id:
            continue
        other_terms = set(re.findall(r"\b[\w-]+\b", other.title.lower()))
        overlap = len(title_terms & other_terms) / max(len(title_terms | other_terms), 1)
        max_overlap = max(max_overlap, overlap)
    return round(max_overlap, 2)


def _author_match_score(paper: PaperRecord) -> float:
    if not paper.authors:
        return 0.0
    unique_names = {author.get("name", "").strip().lower() for author in paper.authors if author.get("name")}
    return round(min(1.0, len(unique_names) / max(len(paper.authors), 1)), 2)


def _recommendation_reason(paper: PaperRecord) -> str:
    if paper.is_retracted:
        return "Flagged for review because it may be retracted or withdrawn."
    if paper.datasets:
        return "Useful for dataset-centric exploration and benchmark comparison."
    if paper.code_repositories:
        return "Good candidate for reproducible follow-up because code is linked."
    if paper.is_open_access:
        return "Accessible full text makes it easier to compare and cite."
    return "Relevant match based on current search intent and ranking signals."


def _author_disambiguation(author_mentions: dict[str, list[str]]) -> list[dict[str, object]]:
    resolved = []
    for author_name, affiliations in author_mentions.items():
        unique_affiliations = _unique([affiliation for affiliation in affiliations if affiliation])
        resolved.append(
            {
                "author": author_name,
                "distinct_affiliations": unique_affiliations,
                "paper_mentions": len(affiliations),
                "confidence": round(0.55 + min(len(unique_affiliations), 3) * 0.1, 2),
            }
        )
    return resolved[:10]


def _co_citation_pairs(papers: list[PaperRecord]) -> list[dict[str, object]]:
    pairs = []
    for left_index, left in enumerate(papers[:8]):
        for right in papers[left_index + 1:8]:
            title_overlap = len(
                set(re.findall(r"\b[\w-]+\b", left.title.lower()))
                & set(re.findall(r"\b[\w-]+\b", right.title.lower()))
            )
            if title_overlap >= 2 and left.citation_count >= 25 and right.citation_count >= 25:
                pairs.append(
                    {
                        "left_paper_id": left.paper_id,
                        "right_paper_id": right.paper_id,
                        "shared_signal": "title-token overlap plus citation strength",
                        "score": round(min(1.0, (title_overlap / 6) + ((left.citation_count + right.citation_count) / 500)), 2),
                    }
                )
    return pairs[:8]


def _bibliographic_coupling_pairs(papers: list[PaperRecord]) -> list[dict[str, object]]:
    pairs = []
    for left_index, left in enumerate(papers[:8]):
        left_signals = {value.lower() for value in [*left.datasets, *left.methodologies, *left.institutions] if value}
        for right in papers[left_index + 1:8]:
            right_signals = {value.lower() for value in [*right.datasets, *right.methodologies, *right.institutions] if value}
            shared = sorted(left_signals & right_signals)
            if shared:
                pairs.append(
                    {
                        "left_paper_id": left.paper_id,
                        "right_paper_id": right.paper_id,
                        "shared_signals": shared[:4],
                        "score": round(min(1.0, len(shared) / 4), 2),
                    }
                )
    return pairs[:8]


def _figure_search_matches(
    papers: list[PaperRecord],
    *,
    query: str,
    query_type: str,
    image_caption: str | None,
) -> list[dict[str, str]]:
    if query_type != "image" and not image_caption:
        return []
    figure_query = (image_caption or query).lower()
    matches = []
    for paper in papers[:12]:
        text = f"{paper.title} {paper.abstract or ''}"
        caption = re.search(r"(figure\s+\d+[:.\-]?\s*[^.\n]{10,180})", text, re.IGNORECASE)
        if caption or any(token in text.lower() for token in re.findall(r"\b[\w-]+\b", figure_query)):
            matches.append(
                {
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "figure_caption": caption.group(1).strip() if caption else "Figure-adjacent match inferred from query tokens.",
                }
            )
    return matches[:6]


def _search_insights(papers: list[PaperRecord], source_coverage: dict[str, int]) -> dict[str, object]:
    open_access_count = sum(1 for paper in papers if paper.is_open_access)
    retracted_count = sum(1 for paper in papers if paper.is_retracted)
    preprint_count = sum(1 for paper in papers if paper.is_preprint)
    return {
        "source_mix": source_coverage,
        "open_access_ratio": round(open_access_count / max(len(papers), 1), 2),
        "retracted_hits": retracted_count,
        "preprint_hits": preprint_count,
        "semantic_rerank_enabled": True,
        "semantic_backend": "faiss_lite",
    }


def _unique(values: list[str]) -> list[str]:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _author_matches(query: str, candidate_name: str) -> bool:
    query_tokens = _name_tokens(query)
    candidate_tokens = _name_tokens(candidate_name)
    if not query_tokens or not candidate_tokens:
        return False
    if all(token in candidate_tokens for token in query_tokens):
        return True
    if len(query_tokens) == 1:
        return query_tokens[0] in candidate_tokens
    query_family = query_tokens[-1]
    candidate_family = candidate_tokens[-1]
    if query_family != candidate_family:
        return False
    query_given = query_tokens[0]
    candidate_given = candidate_tokens[0]
    return candidate_given.startswith(query_given) or query_given.startswith(candidate_given)


def _name_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z]+", value.lower()) if token]
