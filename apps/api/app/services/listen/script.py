"""Clean listening script: turns raw paper text (PDF pages) into sections of speakable sentences.

What a listener should hear is not what a PDF contains. Before speaking:
  * ligatures (ﬁ ﬂ ﬀ …), soft hyphens and words hyphenated across line breaks are repaired;
  * running headers / footers (lines repeated on many pages), page numbers and line numbers are dropped;
  * inline citation markers ([12], [3–5], (Smith et al., 2020)), URLs, DOIs and e-mail addresses are removed;
  * the reference list (and anything after it, such as appendices of references) is skipped;
  * figure / table captions become one short spoken line ("Figure 3. Accuracy per dataset.");
  * equation-like lines become "Equation — see the paper.";
  * abbreviations, Greek letters, units and comparison signs are expanded with a per-language lexicon;
  * sentences are segmented with the punctuation of each script (Latin . ! ?, Urdu/Arabic ۔ ؟, CJK 。！？,
    Devanagari ।), so highlighting and resume positions are stable in every language.

The builder never invents text: every sentence comes from the document. It is deterministic, so a position
(section index, sentence index) saved on one device points to the same sentence on another.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st", "­": "", "\u200b": ""}

HEADING_WORDS = {
    "abstract", "introduction", "background", "related work", "related works", "literature review", "preliminaries",
    "method", "methods", "methodology", "approach", "proposed method", "model", "materials and methods", "data",
    "dataset", "datasets", "experimental setup", "experiments", "experiment", "evaluation", "results",
    "results and discussion", "discussion", "analysis", "ablation study", "ablation studies", "limitations",
    "future work", "conclusion", "conclusions", "conclusion and future work", "acknowledgments", "acknowledgements",
    "appendix", "supplementary material",
}
REFERENCE_HEADINGS = {"references", "bibliography", "works cited", "literature cited", "reference", "citations"}
SKIP_SECTIONS = {"acknowledgments", "acknowledgements"}

_HEADING = re.compile(
    r"^\s*(?:(?P<num>(?:\d{1,2}(?:\.\d{1,2}){0,2}|[IVX]{1,5}|[A-H])\.?)\s+)?(?P<title>[A-Za-z][A-Za-z &\-]{2,60}?)\s*:?\s*$"
)
_CITATION_BRACKET = re.compile(r"\s?\[(?:\d{1,3}(?:\s*[,–\-]\s*\d{1,3})*)\]")
_CITATION_AUTHOR = re.compile(
    r"\s?\((?:see\s+)?(?:[A-Z][A-Za-z'\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'\-]+|\s+et\s+al\.)?,?\s+\d{4}[a-z]?(?:;\s*)?)+\)"
)
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_DOI = re.compile(r"\b(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?\s*$", re.IGNORECASE)
_LINE_NUMBERS = re.compile(r"^\s*\d{1,4}\s+(?=\S)")
_CAPTION = re.compile(r"^\s*(?P<kind>fig(?:ure)?|table|tab)\.?\s*(?P<num>\d{1,3}[a-z]?)\s*[:.|]\s*(?P<text>.+)$", re.IGNORECASE)
_MATH_CHARS = set("=+−-×÷∑∏∫√≈≠≤≥∈∉⊂⊆∀∃∂∇^_{}|·∞→←⇒")
_SENTENCE = {
    "latin": re.compile(r"(?<=[.!?])\s+(?=[\"'“(\[]?[A-Z0-9À-ɏ])"),
    "arabic": re.compile(r"(?<=[۔؟!.])\s+"),
    "cjk": re.compile(r"(?<=[。！？])"),
    "indic": re.compile(r"(?<=[।॥!?.])\s+"),
}
_ABBREV_END = re.compile(r"\b(?:e\.g|i\.e|et al|Fig|Figs|Eq|Eqs|Sec|Tab|vs|cf|approx|resp|Dr|Mr|Ms|Prof|No|Vol|pp|al)\.$", re.IGNORECASE)

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta",
    "λ": "lambda", "μ": "mu", "ν": "nu", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau", "φ": "phi", "χ": "chi",
    "ψ": "psi", "ω": "omega", "Δ": "delta", "Σ": "sigma", "Ω": "omega",
}

# Per-language lexicon. Keys are regular expressions applied with word boundaries where it makes sense.
LEXICON: dict[str, list[tuple[str, str]]] = {
    "en": [
        (r"\be\.g\.,?", "for example,"), (r"\bi\.e\.,?", "that is,"), (r"\bet al\.", "and colleagues"),
        (r"\bvs\.", "versus"), (r"\bcf\.", "compare"), (r"\bapprox\.", "approximately"), (r"\bFigs?\.\s*(?=\d)", "Figure "),
        (r"\bEqs?\.\s*(?=\d)", "Equation "), (r"\bSec\.\s*(?=\d)", "Section "), (r"\bTab\.\s*(?=\d)", "Table "),
        (r"\bp\s*<\s*0?\.(\d+)", r"p less than 0.\1"), (r"\bp\s*>\s*0?\.(\d+)", r"p greater than 0.\1"),
        (r"\s?±\s?", " plus or minus "), (r"\s?≤\s?", " less than or equal to "), (r"\s?≥\s?", " greater than or equal to "),
        (r"\s?≈\s?", " approximately "), (r"(\d)\s?°C\b", r"\1 degrees Celsius"), (r"(\d)\s?°F\b", r"\1 degrees Fahrenheit"),
        (r"(\d)\s?km/h\b", r"\1 kilometres per hour"), (r"(\d)\s?ms\b", r"\1 milliseconds"), (r"(\d)\s?GB\b", r"\1 gigabytes"),
        (r"(\d)\s?MB\b", r"\1 megabytes"), (r"(\d)\s?%", r"\1 percent"), (r"\bLaTeX\b", "Lah-tech"), (r"\bSQL\b", "S Q L"),
        (r"\bCNNs\b", "C N Ns"), (r"\bCNN\b", "C N N"), (r"\bRNNs?\b", "R N N"), (r"\bGANs?\b", "gan"), (r"\bNLP\b", "N L P"),
        (r"\bLLMs\b", "L L Ms"), (r"\bLLM\b", "L L M"), (r"\bGPU(s?)\b", r"G P U\1"), (r"\bAPI(s?)\b", r"A P I\1"),
        (r"\bAUC\b", "A U C"), (r"\bROC\b", "R O C"), (r"\bF1\b", "F one"), (r"\bBLEU\b", "blue"), (r"\bSOTA\b", "state of the art"),
    ],
    "ur": [(r"\s?±\s?", " جمع یا تفریق "), (r"(\d)\s?%", r"\1 فیصد"), (r"\bet al\.", "اور ساتھی")],
    "hi": [(r"(\d)\s?%", r"\1 प्रतिशत"), (r"\bet al\.", "और सहयोगी")],
    "ar": [(r"(\d)\s?%", r"\1 بالمئة"), (r"\bet al\.", "وزملاؤه")],
    "zh": [(r"(\d)\s?%", r"百分之\1"), (r"\bet al\.", "等人")],
    "es": [(r"(\d)\s?%", r"\1 por ciento"), (r"\bet al\.", "y colaboradores"), (r"\bp\.\s?ej\.", "por ejemplo")],
    "fr": [(r"(\d)\s?%", r"\1 pour cent"), (r"\bet al\.", "et collègues"), (r"\bp\.\s?ex\.", "par exemple")],
    "de": [(r"(\d)\s?%", r"\1 Prozent"), (r"\bet al\.", "und Kollegen"), (r"\bz\.\s?B\.", "zum Beispiel")],
}

INTRO_NOTE = {
    "en": "This is a translated reading of the paper.",
    "ur": "یہ مقالے کا ترجمہ شدہ مطالعہ ہے۔",
    "zh-Hans": "这是论文的译文朗读。",
    "es": "Esta es una lectura traducida del artículo.",
    "ar": "هذه قراءة مترجمة للورقة.",
    "hi": "यह शोधपत्र का अनूदित पाठ है।",
    "fr": "Ceci est une lecture traduite de l'article.",
    "de": "Dies ist eine übersetzte Lesung des Artikels.",
}
EQUATION_LINE = {"en": "Equation — see the paper.", "ur": "مساوات — مقالہ دیکھیں۔", "zh": "公式，请参阅论文。", "es": "Ecuación: consulte el artículo.",
                 "ar": "معادلة — راجع الورقة.", "hi": "समीकरण — शोधपत्र देखें।", "fr": "Équation — voir l'article.", "de": "Gleichung — siehe Artikel."}
AND_COLLEAGUES = {"en": "and colleagues", "ur": "اور ساتھی", "zh": "等人", "es": "y colaboradores", "ar": "وزملاؤه", "hi": "और सहयोगी", "fr": "et collègues", "de": "und Kollegen"}
CHARS_PER_MINUTE = {"latin": 900, "arabic": 800, "indic": 800, "cjk": 280}


@dataclass
class ScriptOptions:
    read_references: bool = False
    read_citations: bool = False
    read_captions: bool = True
    read_equations: bool = True  # as "Equation — see the paper."


@dataclass
class Section:
    title: str
    sentences: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"title": self.title, "sentences": self.sentences, "pages": sorted(set(self.pages))}


def base_language(language: str) -> str:
    return (language or "en").split("-")[0].lower()


def script_family(language: str) -> str:
    base = base_language(language)
    if base in {"ur", "ar", "fa", "ps", "sd", "ug", "he"}:
        return "arabic"
    if base in {"zh", "ja", "ko"}:
        return "cjk" if base != "ko" else "latin"
    if base in {"hi", "mr", "ne", "bn", "pa", "gu", "sa"}:
        return "indic"
    return "latin"


def detect_language(text: str) -> str:
    """Very small script-based guess used only when the caller did not say the language."""
    sample = text[:4000]
    counts = Counter()
    for char in sample:
        code = ord(char)
        if 0x0600 <= code <= 0x06FF:
            counts["arabic"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["cjk"] += 1
        elif 0x0900 <= code <= 0x097F:
            counts["indic"] += 1
        elif char.isalpha():
            counts["latin"] += 1
    if not counts:
        return "en"
    family = counts.most_common(1)[0][0]
    if family == "arabic":
        return "ur" if re.search(r"[ٹڈڑںےۓ]", sample) else "ar"
    return {"cjk": "zh-Hans", "indic": "hi"}.get(family, "en")


def normalize_text(text: str) -> str:
    for source, target in LIGATURES.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)  # hyphenated across a line break
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _repeated_lines(pages: list[str]) -> set[str]:
    """Running headers and footers: short lines that repeat on at least 40 % of pages (min 3 pages)."""
    if len(pages) < 3:
        return set()
    counter: Counter[str] = Counter()
    for page in pages:
        lines = {re.sub(r"\d+", "#", line.strip().lower()) for line in page.splitlines() if 0 < len(line.strip()) <= 90}
        counter.update(lines)
    threshold = max(3, int(len(pages) * 0.4))
    return {line for line, count in counter.items() if count >= threshold}


def _is_equation(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    math = sum(1 for char in stripped if char in _MATH_CHARS)
    letters = sum(1 for char in stripped if char.isalpha())
    words = re.findall(r"[A-Za-z]{4,}", stripped)
    return math >= 2 and (math / max(1, len(stripped)) > 0.08) and len(words) <= 2 and letters < len(stripped) * 0.6


def _heading(line: str) -> tuple[str, str] | None:
    """Returns (kind, title) for a section heading line: kind is 'reference', 'skip' or 'section'."""
    stripped = line.strip()
    if not stripped or len(stripped) > 70:
        return None
    match = _HEADING.match(stripped)
    if not match:
        return None
    title = match.group("title").strip()
    key = re.sub(r"\s+", " ", title.lower())
    if key in REFERENCE_HEADINGS:
        return "reference", title
    if key in SKIP_SECTIONS:
        return "skip", title
    if key in HEADING_WORDS or (match.group("num") and stripped.upper() != stripped and len(title.split()) <= 6 and title[:1].isupper()):
        return "section", title.title() if title.isupper() else title
    if stripped.isupper() and 1 <= len(title.split()) <= 5 and key in HEADING_WORDS | REFERENCE_HEADINGS:
        return "section", title.title()
    return None


def apply_lexicon(sentence: str, language: str) -> str:
    base = base_language(language)
    for pattern, replacement in LEXICON.get(base, []):
        sentence = re.sub(pattern, replacement, sentence)
    if base == "en":
        for letter, name in GREEK.items():
            sentence = sentence.replace(letter, f" {name} ")
    return re.sub(r"\s{2,}", " ", sentence).strip()


def clean_inline(text: str, options: ScriptOptions) -> str:
    text = _URL.sub("", text)
    text = _DOI.sub("", text)
    text = _EMAIL.sub("", text)
    if not options.read_citations:
        text = _CITATION_BRACKET.sub("", text)
        text = _CITATION_AUTHOR.sub("", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def split_sentences(text: str, language: str) -> list[str]:
    family = script_family(language)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = [part for part in _SENTENCE[family].split(text) if part and part.strip()]
    if family == "latin":
        merged: list[str] = []
        for part in parts:  # "e.g." / "Fig." must not end a sentence
            if merged and _ABBREV_END.search(merged[-1]):
                merged[-1] = f"{merged[-1]} {part}"
            else:
                merged.append(part)
        parts = merged
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        while len(part) > 320:  # very long sentences are split at a clause boundary for smooth speech
            cut = max(part.rfind(", ", 0, 300), part.rfind("; ", 0, 300), part.rfind("، ", 0, 300), part.rfind("，", 0, 300))
            cut = cut if cut > 80 else 300
            sentences.append(part[: cut + 1].strip())
            part = part[cut + 1 :].strip()
        if len(re.sub(r"\W", "", part)) >= 2:
            sentences.append(part)
    return sentences


def build_script(
    pages: Iterable[str],
    *,
    language: str | None = None,
    title: str | None = None,
    authors: list[str] | None = None,
    options: ScriptOptions | None = None,
    translated_from: str | None = None,
) -> dict:
    """Build the listening script. Returns {language, sections:[{title, sentences, pages}], characters, minutes}."""
    options = options or ScriptOptions()
    pages = [normalize_text(page or "") for page in pages]
    joined = "\n".join(pages)
    language = language or detect_language(joined)
    base = base_language(language)
    repeated = _repeated_lines(pages)

    sections: list[Section] = []
    intro = Section(title=title or "")
    if translated_from and base_language(translated_from) != base:
        intro.sentences.append(INTRO_NOTE.get(language, INTRO_NOTE.get(base, INTRO_NOTE["en"])))
    if title:
        intro.sentences.append(title.strip().rstrip(".") + ".")
    if authors:
        names = ", ".join(authors[:3])
        if len(authors) > 3:
            names = f"{names} {AND_COLLEAGUES.get(base, AND_COLLEAGUES['en'])}"
        intro.sentences.append(names + ".")
    sections.append(intro)
    current = Section(title="")
    sections.append(current)
    in_references = False
    skipping = False
    paragraph: list[str] = []

    def flush(page_number: int) -> None:
        nonlocal paragraph
        if not paragraph:
            return
        text = clean_inline(" ".join(paragraph), options)
        paragraph = []
        for sentence in split_sentences(text, language):
            spoken = apply_lexicon(sentence, language)
            if spoken:
                current.sentences.append(spoken)
                current.pages.append(page_number)

    for page_index, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            line = _LINE_NUMBERS.sub("", raw) if re.match(r"^\s*\d{1,4}\s+[a-z]", raw) else raw
            stripped = line.strip()
            if not stripped:
                flush(page_index)
                continue
            if re.sub(r"\d+", "#", stripped.lower()) in repeated or _PAGE_NUMBER.match(stripped):
                continue
            heading = _heading(stripped)
            if heading:
                kind, heading_title = heading
                flush(page_index)
                if kind == "reference":
                    in_references = True
                    if not options.read_references:
                        continue
                elif in_references and not options.read_references and heading_title.lower() not in {"appendix", "supplementary material"}:
                    continue
                else:
                    in_references = False
                skipping = kind == "skip"
                current = Section(title=heading_title)
                sections.append(current)
                continue
            if (in_references and not options.read_references) or skipping:
                continue
            caption = _CAPTION.match(stripped)
            if caption:
                flush(page_index)
                if options.read_captions:
                    kind = "Table" if caption.group("kind").lower().startswith("tab") else "Figure"
                    text = clean_inline(caption.group("text"), options)
                    first = split_sentences(text, language)[:1]
                    if first:
                        current.sentences.append(apply_lexicon(f"{kind} {caption.group('num')}. {first[0]}", language))
                        current.pages.append(page_index)
                continue
            if _is_equation(stripped):
                flush(page_index)
                if options.read_equations and (not current.sentences or current.sentences[-1] != EQUATION_LINE.get(base, EQUATION_LINE["en"])):
                    current.sentences.append(EQUATION_LINE.get(base, EQUATION_LINE["en"]))
                    current.pages.append(page_index)
                continue
            paragraph.append(stripped)
        flush(page_index)

    result = [section for section in sections if section.sentences]
    characters = sum(len(sentence) for section in result for sentence in section.sentences)
    minutes = characters / CHARS_PER_MINUTE[script_family(language)]
    return {"language": language, "sections": [section.as_dict() for section in result], "characters": characters, "minutes": round(minutes, 1)}


def script_from_texts(texts: list[str], *, language: str | None = None, title: str | None = None) -> dict:
    """A script for short content (summary, key points, a chat answer): one section, no document heuristics."""
    language = language or detect_language(" ".join(texts))
    options = ScriptOptions()
    sentences: list[str] = []
    for text in texts:
        for sentence in split_sentences(clean_inline(normalize_text(text), options), language):
            sentences.append(apply_lexicon(sentence, language))
    characters = sum(len(sentence) for sentence in sentences)
    return {
        "language": language,
        "sections": [{"title": title or "", "sentences": sentences, "pages": []}] if sentences else [],
        "characters": characters,
        "minutes": round(characters / CHARS_PER_MINUTE[script_family(language)], 1),
    }
