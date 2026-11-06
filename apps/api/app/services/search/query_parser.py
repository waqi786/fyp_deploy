from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QueryUnderstanding:
    original_query: str
    query: str
    year_from: int | None = None
    open_access_only: bool = False
    author: str | None = None
    reviews_only: bool = False


_PREFIXES = [
    r"^(?:hey|hi|hello|please|kindly|can you|could you|would you|i want to|i wanna|i would like to|i need you to|help me)\b[\s,:-]*",
    r"^(?:search|find|look up|look for|show)\s+(?:for\s+)?(?:me\s+)?",
    r"^(?:wanna|want to|would like to)\s+",
    r"^(?:hola|por favor|busca|buscar)\s+",
    r"^(?:bonjour|s'il vous pla\u00eet|recherche|chercher|veuillez)\s+",
    r"^(?:hallo|bitte|suche|suchen)\s+",
    r"^(?:mujhe|mujhay|please|plz)\s+",
    r"^(?:\u0627\u0628\u062d\u062b \u0639\u0646|\u0627\u0628\u062d\u062b|\u0645\u0646 \u0641\u0636\u0644\u0643|\u0644\u0648 \u0633\u0645\u062d\u062a)\s*",
    r"^(?:\u0628\u0631\u0627\u06c1 \u06a9\u0631\u0645|\u0645\u062c\u06be\u06d2|\u062a\u0644\u0627\u0634 \u06a9\u0631\u06cc\u06ba|\u062a\u0644\u0627\u0634 \u06a9\u0631\u0648|\u0688\u06be\u0648\u0646\u0688\u0648)\s*",
    r"^(?:\u0915\u0943\u092a\u092f\u093e|\u092e\u0941\u091d\u0947|\u0916\u094b\u091c\u0947\u0902|\u0916\u094b\u091c\u094b|\u0922\u0942\u0902\u0922\u0947\u0902)\s*",
    r"^(?:\u8bf7\u5e2e\u6211|\u8bf7|\u641c\u7d22|\u67e5\u627e)\s*",
]
_YEAR = r"(?:19|20|\u06f1\u06f9|\u06f2\u06f0)[0-9\u06f0-\u06f9\u0660-\u0669]{2}"
_TRAILING = [
    r"\s+(?:papers?|articles?|research)\s*$",
    r"\s+(?:papers?|articles?)\s+(?:please\s+)?(?:kindly\s+)?(?:search\s+it|search\s+this|search|find)\s*\.?$",
    r"\s+(?:please\s+)?(?:kindly\s+)?(?:search\s+it|search\s+this|search\s+for\s+me|find\s+it|search|find)\s*\.?$",
    r"\s+(?:papers?\s+chahiye|ke baare mein|ke bare mein)\s*$",
    r"\s+(?:\u062a\u0644\u0627\u0634 \u06a9\u0631\u06cc\u06ba|\u062a\u0644\u0627\u0634 \u06a9\u0631\u0648|\u062c\u0633\u062a\u062c\u0648 \u06a9\u0631\u06cc\u06ba)\s*$",
    r"\s+(?:\u0916\u094b\u091c\u0947\u0902|\u0916\u094b\u091c\u094b|\u0922\u0942\u0902\u0922\u0947\u0902|\u092a\u0947\u092a\u0930 \u0916\u094b\u091c\u0947\u0902)\s*$",
    r"\s+\u8bba\u6587\s*$",
]


def understand_research_query(value: str) -> QueryUnderstanding:
    original = " ".join((value or "").split())
    text = re.sub(r"^[\s,:;.!?]+|[\s,:;.!?]+$", "", original)
    year_from = None
    year_pattern = re.compile(rf"\b(?:since|from|after)\s+(19\d{{2}}|20\d{{2}})\b|({_YEAR})\s*(?:\u0633\u06d2|\u06a9\u06d2 \u0628\u0639\u062f)", re.IGNORECASE)
    year_match = year_pattern.search(text)
    if year_match:
        digits = year_match.group(1) or year_match.group(2)
        year_from = int("".join(str(unicodedata.digit(char)) for char in digits)) if digits else None
        text = text[:year_match.start()] + " " + text[year_match.end():]

    open_access_pattern = r"\bopen[- ]access\b|\u0645\u0641\u062a\u0648\u062d\u06c1? \u0631\u0633\u0627\u0626\u06cc|\u0913\u092a\u0928 \u090f\u0915\u094d\u0938\u0947\u0938"
    reviews_pattern = r"\b(?:reviews?\s+only|review papers?|systematic reviews?)\b|\u0635\u0631\u0641 \u062c\u0627\u0626\u0632\u06d2|\u0915\u0947\u0935\u0932 \u0938\u092e\u0940\u0915\u094d\u0937\u093e"
    open_access = bool(re.search(open_access_pattern, text, re.IGNORECASE))
    reviews_only = bool(re.search(reviews_pattern, text, re.IGNORECASE))
    text = re.sub(open_access_pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(reviews_pattern, " ", text, flags=re.IGNORECASE)

    author = None
    author_match = re.search(r"\bby\s+(.+?)(?=\s+(?:since|from|after)\s+\d{4}\b|$)", text, re.IGNORECASE)
    if author_match:
        author = author_match.group(1).strip(" ,.;") or None
        text = text[:author_match.start()] + " " + text[author_match.end():]

    for _ in range(3):
        for pattern in _PREFIXES:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:papers?|research|articles?|studies)\s+(?:about|on|related to|regarding|sobre|sur|\xFCber)\s+", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"(?i)\b(?:art[i\xED]culos?|articles?)\s+(?:sobre|sur|\xFCber|about|on)\s+", " ", text)
        text = re.sub(r"(?i)^(?:des|les|los|las)\s+(?=articles?|art[i\xED]culos?)", " ", text)
        text = re.sub(r"(?i)^(?:des|les|los|las)\s+", " ", text)
        text = re.sub(r"(?i)^artikel\s+\xFCber\s+", " ", text)
        text = re.sub(r"\s+\u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902\s*$", " ", text)
        text = re.sub(r"(?i)^\s*(?:about|on)\s+", "", text)
        text = re.sub(r"\s*(?:\u06a9\u06d2 \u0628\u0627\u0631\u06d2 \u0645\u06cc\u06ba|\u06a9\u06d2 \u0645\u062a\u0639\u0644\u0642)\s*(?:\u062a\u062d\u0642\u06cc\u0642|\u0645\u0642\u0627\u0644\u0627\u062a?|\u0645\u0642\u0627\u0644\u06d2)?\s*$", " ", text)
        text = re.sub(r"\s+(?:\u062a\u062d\u0642\u06cc\u0642|\u0645\u0642\u0627\u0644\u0627\u062a?|\u0645\u0642\u0627\u0644\u06d2|\u0623\u0648\u0631\u0627\u0642|\u0648\u0631\u0642)\s*$", " ", text)
        text = re.sub(r"\s*(?:\u092a\u0947\u092a\u0930|\u0936\u094b\u0927|\u0905\u0927\u094d\u092f\u092f\u0928)\s*$", " ", text)
        text = re.sub(r"\u8bba\u6587\s*$", " ", text)
        text = re.sub(r"(?i)\s+(?:papers?|articles?|research|studies|art[i\xED]culos?|articles?)\s*$", " ", text)
        for pattern in _TRAILING:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:please|kindly|it|this|that|i)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"^[\s,:;.!?]+|[\s,:;.!?]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return QueryUnderstanding(original, text or original, year_from, open_access, author, reviews_only)


def query_understanding_dict(value: str) -> dict[str, object]:
    return asdict(understand_research_query(value))
