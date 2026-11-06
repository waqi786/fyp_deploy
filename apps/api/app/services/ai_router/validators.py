"""Small, deterministic output checks shared by router task adapters."""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

_PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_.-]*(?:,[^{}]+)?\}")
_NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:%|\b)")


def translation_output_is_valid(source: str, output: str, language: str, *, allow_identical: bool = False) -> bool:
    """Check placeholder preservation, non-empty output and expected writing system."""
    if not source.strip() or not output.strip():
        return False
    if sorted(_PLACEHOLDER.findall(source)) != sorted(_PLACEHOLDER.findall(output)):
        return False
    target = language.replace("_", "-").casefold()
    if not allow_identical and target not in {"en", "en-us", "en-gb"} and output.strip().casefold() == source.strip().casefold():
        return False
    ranges = {
        "hi": ((0x0900, 0x097F),), "mr": ((0x0900, 0x097F),),
        "ur": ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)),
        "ar": ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)),
        "fa": ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)),
        "zh-hans": ((0x3400, 0x9FFF),), "zh-hant": ((0x3400, 0x9FFF),),
        "ja": ((0x3040, 0x30FF), (0x3400, 0x9FFF)), "ko": ((0xAC00, 0xD7AF),),
        "th": ((0x0E00, 0x0E7F),), "bn": ((0x0980, 0x09FF),),
        "pa-guru": ((0x0A00, 0x0A7F),), "pa-arab": ((0x0600, 0x06FF), (0x0750, 0x077F)),
        "ta": ((0x0B80, 0x0BFF),), "te": ((0x0C00, 0x0C7F),),
        "gu": ((0x0A80, 0x0AFF),), "kn": ((0x0C80, 0x0CFF),),
        "ml": ((0x0D00, 0x0D7F),), "am": ((0x1200, 0x137F),),
        "he": ((0x0590, 0x05FF),), "ps": ((0x0600, 0x06FF),), "sd": ((0x0600, 0x06FF),),
    }
    expected = ranges.get(target)
    if expected:
        script_text = re.sub(r"RESORATOKENX\d+XEND", "", output, flags=re.IGNORECASE)
        script_text = re.sub(r"\{[^{}]*\}|https?://\S+|10\.\d{4,9}/\S+", "", script_text)
        letters = [char for char in script_text if unicodedata.category(char).startswith("L")]
        if letters and sum(any(start <= ord(char) <= end for start, end in expected) for char in letters) / len(letters) < 0.35:
            return False
    return True


def extraction_json_is_valid(output: str, source: str, *, evidence_fields: tuple[str, ...] = ("evidence",)) -> bool:
    """Require object JSON and verify evidence quote strings against the supplied source."""
    try:
        value = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(value, dict):
        return False
    quotes: list[str] = []
    for field in evidence_fields:
        item = value.get(field)
        if isinstance(item, str):
            quotes.append(item)
        elif isinstance(item, list):
            quotes.extend(str(part) for part in item if isinstance(part, str))
        elif item is not None:
            return False
    normalized_source = " ".join(source.casefold().split())
    for quote in quotes:
        normalized_quote = " ".join(quote.casefold().split())
        if not normalized_quote or (normalized_quote not in normalized_source and SequenceMatcher(None, normalized_quote, normalized_source).ratio() < 0.92):
            return False
    return True


def numbers_are_grounded(output: str, evidence: str) -> bool:
    """Reject numeric claims not present in the source/evidence text."""
    source_numbers = {re.sub(r"[, ]", "", item) for item in _NUMBER.findall(evidence)}
    output_numbers = {re.sub(r"[, ]", "", item) for item in _NUMBER.findall(output)}
    return output_numbers.issubset(source_numbers)


def judge_json_is_valid(output: str) -> bool:
    try:
        value: Any = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("choice") in {"a", "b", "merge", "A", "B"} and isinstance(value.get("reason"), str) and bool(value["reason"].strip()) and ("merged_text" not in value or isinstance(value["merged_text"], str))
