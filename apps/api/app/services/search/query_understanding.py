from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QueryUnderstanding:
    original_query: str
    query: str
    year_from: int | None = None
    open_access_only: bool = False
    author: str | None = None
    reviews_only: bool = False


_FILLER_PATTERNS = [
    r"^(?:hey|hi|hello|please|kindly|can you|could you|would you|i want to|i wanna|i would like to|help me|i need you to)\b[\s,:-]*",
    r"^(?:search|find|look|show)\s+(?:for\s+)?(?:me\s+)?",
    r"\b(?:kindly\s+)?search\s+(?:for\s+)?(?:it|this|that|about)?\s*$",
    r"\b(?:papers?|research|articles?)\s+(?:about|on|related\s+to)\s+",
    r"(?:\s+papers?|\s+articles?|\s+research)?\s*(?:please\s+)?(?:search\s+it|search\s+this|search\s+for\s+me|find\s+it|kindly search it|تلاش کریں|تلاش کرو|جستجو کریں|खोजें|खोजो|ढूंढें|खोजिए|论文|के पेपर|पेपर खोजें|पेपर ढूंढें|papers chahiye)\s*$",
    r"\b(?:about|on)\s+",
    r"\bplease\b|\bkindly\b|\bi wanna\b|\bi want to\b|\bi would like to\b",
    r"^(?:hola|por favor|busca|buscar)\s+",
    r"^(?:bonjour|s'il vous plaît|recherche|chercher|veuillez)\s+",
    r"^(?:hallo|bitte|suche|suchen)\s+",
    r"^(?:ابحث عن|ابحث|من فضلك|لو سمحت)\s*",
    r"^(?:براہ کرم|مجھے|تلاش کریں|تلاش کرو|ڈھونڈو)\s*",
    r"^(?:कृपया|मुझे|खोजें|खोजो|ढूंढें)\s*",
    r"^(?:请帮我|请|搜索|查找)\s*",
    r"^(?:mujhe|mujhay|please|plz)\s+",
    r"(?:\s+papers? chahiye|\s+ke baare mein|\s+ke bare mein|\s+पर पेपर|\s+के बारे में|\s+论文)\s*$",
    r"(?:\s+पर)\s+",
    r"^search(?:\s+for)?\s+",
    r"^(?:busca|buscar)\s+(?:artículos?\s+)?(?:sobre\s+)?",
    r"^(?:recherche|chercher)\s+(?:des\s+articles?\s+)?(?:sur\s+)?",
    r"^(?:suche|suchen)\s+(?:nach\s+)?",
    r"^(?:搜索|查找)\s*(?:关于|有关)?",
    r"^(?:ابحث عن|ابحث)\s*",
]


def understand_research_query(value: str) -> QueryUnderstanding:
    original = " ".join((value or "").split())
    text = original
    year_from = None
    year_match = re.search(r"\b(?:since|from|after)\s+(19\d{2}|20\d{2})\b|(?:۲۰|19|20)\d{2}\s*(?:سے|کے بعد)", text, re.IGNORECASE)
    if year_match:
        year_value = next((item for item in year_match.groups() if item), None)
        if year_value:
            year_from = int(year_value)
        else:
            digits = re.search(r"(?:19|20)\d{2}", year_match.group(0))
            year_from = int(digits.group(0)) if digits else None
        text = text[:year_match.start()] + " " + text[year_match.end():]

    open_access = bool(re.search(r"\bopen[- ]access\b|مفتوح(?:ہ)? رسائی|ओपन एक्सेस", text, re.IGNORECASE))
    text = re.sub(r"\bopen[- ]access\b|مفتوح(?:ہ)? رسائی|ओपन एक्सेस", " ", text, flags=re.IGNORECASE)
    reviews_only = bool(re.search(r"\b(?:reviews?\s+only|review papers?|systematic reviews?)\b|صرف جائزے|केवल समीक्षा", text, re.IGNORECASE))
    text = re.sub(r"\b(?:reviews?\s+only|review papers?|systematic reviews?)\b|صرف جائزے|केवल समीक्षा", " ", text, flags=re.IGNORECASE)

    author = None
    author_match = re.search(r"\bby\s+(.+?)(?=\s+(?:since|from|after)\s+\d{4}\b|$)", text, re.IGNORECASE)
    if author_match:
        author = author_match.group(1).strip(" ,.;") or None
        text = text[:author_match.start()] + " " + text[author_match.end():]
    else:
        author_match = re.search(r"(?:مصنف|लेखक)\s*[:：]?\s*([^،,;]+)", text)
        if author_match:
            author = author_match.group(1).strip()
            text = text[:author_match.start()] + " " + text[author_match.end():]

    for _ in range(3):
        for pattern in _FILLER_PATTERNS:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:search|find|look up)\s+(?:for\s+)?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:please|kindly|it|this|that|chahiye|papers?|i)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:search|find)\s*$", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^[\s,:;.!?–—-]+|[\s,:;.!?–—-]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return QueryUnderstanding(original, text or original, year_from, open_access, author, reviews_only)


def query_understanding_dict(value: str) -> dict[str, object]:
    return asdict(understand_research_query(value))
