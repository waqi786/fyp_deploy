"""Generate Search UI catalogs (apps/web/src/i18n/search-copy/<locale>.json) from the English source.

Source of truth: `export const searchCopyEn = { ... } as const;` in apps/web/src/pages/search/copy.ts.

What this script guarantees:
  * placeholders such as {count} or {language} survive translation (masked as numbers, verified after);
  * product names and identifiers (Resora, DOI, BibTeX, APA, CSV, example DOI) are never translated;
  * a label is re-translated when its English text changes (hashes kept in catalog-status.json);
  * labels removed from the source are pruned, so catalogs never drift;
  * if a translation breaks a placeholder, the English text is kept and the label is listed for review;
  * apps/api/app/services/search/ui_copy_en.json is refreshed, so the API can fill any label still missing.

Usage (run from the repo root, in a separate terminal — it can take a while on CPU):
  python scripts/generate_search_copy.py --force              # all locales, AI router wording (recommended)
  python scripts/generate_search_copy.py --engine m2m         # offline: local M2M-100 (weaker wording)
  python scripts/generate_search_copy.py --locales ur,zh-Hans # only some locales
  python scripts/generate_search_copy.py --engine chain       # use Resora's translation chain (local first, then providers)
  python scripts/generate_search_copy.py --check              # CI: fail if any catalog is missing labels or placeholders
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = ROOT / "apps" / "web" / "src" / "pages" / "search" / "copy.ts"
OUTPUT_DIR = ROOT / "apps" / "web" / "src" / "i18n" / "search-copy"
STATUS_FILE = OUTPUT_DIR / "catalog-status.json"
# The API fills missing labels at runtime from this copy of the English source (see app/services/search/ui_copy.py).
API_SOURCE_FILE = ROOT / "apps" / "api" / "app" / "services" / "search" / "ui_copy_en.json"
LOCALES = [
    "ur", "ar", "fa", "hi", "bn", "pa-Arab", "tr", "id", "ms", "zh-Hans", "zh-Hant", "ja", "ko", "vi", "th",
    "es", "pt-BR", "pt-PT", "fr", "de", "it", "nl", "pl", "ru", "uk", "sv", "el", "ro", "cs", "hu", "he",
    "sw", "ta", "ps", "sd",
]
# Catalogs written or checked by a native speaker: never overwritten by machine output (only missing labels are added).
HUMAN_REVIEWED = {"ur"}
# Labels that are identifiers or pure formatting: copied, never translated.
DO_NOT_TRANSLATE = {"exampleDoi", "yearRange", "cmpExportCsv", "cmpExportMarkdownShort", "cmpExportJsonShort", "cmpExportXlsx", "cmpDoiLabel"}
# Words that stay as written in every language.
PROTECTED_TERMS = ["Resora", "BibTeX", "DOI", "APA", "CSV"]
PLACEHOLDER = re.compile(r"\{(\w+)\}")
MASK_BASE = 9301  # numbers survive machine translation far better than braces or invented tokens
BATCH_SIZE = 48


def source_copy() -> dict[str, str]:
    source = SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index("export const searchCopyEn = {")
    end = source.index("} as const;", start)
    matches = re.findall(r'^\s*(\w+):\s*("(?:[^"\\]|\\.)*")\s*,?\s*$', source[start:end], re.MULTILINE)
    values = {key: json.loads(value) for key, value in matches}
    if len(values) < 100:
        raise RuntimeError(f"Only extracted {len(values)} English Search labels from {SOURCE_FILE}; refusing partial output")
    return values


def text_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def placeholders(value: str) -> list[str]:
    return sorted(PLACEHOLDER.findall(value))


def mask(value: str) -> tuple[str, dict[str, str]]:
    """Replace {placeholders} and protected terms with distinctive numbers; return the mapping to restore them."""
    mapping: dict[str, str] = {}
    counter = MASK_BASE

    def take(original: str) -> str:
        nonlocal counter
        token = str(counter)
        counter += 1
        mapping[token] = original
        return token

    masked = PLACEHOLDER.sub(lambda match: take(match.group(0)), value)
    for term in PROTECTED_TERMS:
        if term in masked:
            masked = masked.replace(term, take(term))
    return masked, mapping


def unmask(value: str, mapping: dict[str, str]) -> str | None:
    """Restore masked tokens; None if any token was lost or changed (native digits are normalised first)."""
    digits = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९০১২৩৪৫৬৭৮৯", "0123456789" * 4)
    restored = value.translate(digits) if mapping else value
    for token, original in mapping.items():
        spaced = re.compile(r"\s?".join(token))  # engines sometimes insert spaces inside numbers
        if not spaced.search(restored):
            return None
        restored = spaced.sub(lambda _match: original, restored, count=1)
    return " ".join(restored.split())


def m2m_translator(target: str) -> Callable[[list[str]], list[str]]:
    sys.path.insert(0, str(ROOT / "apps" / "translator-local"))
    from engine_manager import M2M_CODES, translate_batch_with_engine  # type: ignore

    code = M2M_CODES.get(target, target)
    return lambda values: translate_batch_with_engine("m2m100", values, "en", code)


def chain_translator(target: str) -> Callable[[list[str]], list[str]]:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.services.search.translation import translate_batch  # type: ignore

    # UI labels are public, non-user text: cached and shareable.
    return lambda values: translate_batch(values, target, source_language="en", user_content=False)


def llm_translator(target: str) -> Callable[[list[str]], list[str]]:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.services.search.ui_copy import llm_translate_labels  # type: ignore

    # Fluent interface wording from the configured AI provider; public product text only (user_content=False).
    return lambda values: llm_translate_labels(values, target)


def translate_labels(entries: list[tuple[str, str]], translate: Callable[[list[str]], list[str]]) -> tuple[dict[str, str], list[str]]:
    results: dict[str, str] = {}
    needs_review: list[str] = []
    for offset in range(0, len(entries), BATCH_SIZE):
        chunk = entries[offset : offset + BATCH_SIZE]
        masked = [mask(value) for _, value in chunk]
        outputs = translate([text for text, _ in masked])
        if len(outputs) != len(chunk):
            raise RuntimeError("The translation engine returned an incomplete batch")
        for (key, english), (_, mapping), output in zip(chunk, masked, outputs):
            restored = unmask(output or "", mapping) if output else None
            if not restored or placeholders(restored) != placeholders(english):
                results[key] = english
                needs_review.append(key)
            else:
                results[key] = restored
    return results, needs_review


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def check(source: dict[str, str], locales: list[str]) -> int:
    problems = 0
    for locale in locales:
        path = OUTPUT_DIR / f"{locale}.json"
        if not path.exists():
            continue  # a language without a catalog is simply not selectable in the UI
        catalog = load_json(path)
        missing = [key for key in source if key not in catalog]
        broken = [key for key in source if key in catalog and placeholders(str(catalog[key])) != placeholders(source[key])]
        if missing or broken:
            problems += 1
            print(f"{locale}: {len(missing)} missing, {len(broken)} broken placeholders {broken[:6]}")
    if problems:
        print("Run: python scripts/generate_search_copy.py")
    else:
        print("All search catalogs are complete.")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--locales", help="Comma-separated locale codes (default: all)")
    parser.add_argument("--engine", choices=["llm", "m2m", "chain"], default="llm",
                        help="llm = AI router (best wording, default); m2m = offline local model; chain = Resora translation chain")
    parser.add_argument("--force", action="store_true", help="Re-translate every label, replacing old (machine) wording")
    parser.add_argument("--check", action="store_true", help="Only verify catalogs; exit 1 when incomplete")
    args = parser.parse_args()

    source = source_copy()
    API_SOURCE_FILE.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    locales = [item.strip() for item in args.locales.split(",")] if args.locales else LOCALES
    if args.check:
        return check(source, locales)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "en.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashes = {key: text_hash(value) for key, value in source.items()}
    status = load_json(STATUS_FILE)
    status.update({
        "source_locale": "en",
        "source_message_count": len(source),
        "generation_engine": {"llm": "AI router", "m2m": "M2M-100 local", "chain": "Resora translation chain"}[args.engine],
        "review_status": "machine_generated_requires_native_review",
    })
    status.setdefault("locales", {})
    print(f"{len(source)} Search labels → {len(locales)} languages ({args.engine})", flush=True)

    for locale in locales:
        output = OUTPUT_DIR / f"{locale}.json"
        previous = {str(key): str(value) for key, value in load_json(output).items()}
        previous_hashes = status["locales"].get(locale, {}).get("source_hashes", {})
        reviewed = locale in HUMAN_REVIEWED
        todo = [
            (key, value)
            for key, value in source.items()
            if key not in DO_NOT_TRANSLATE
            and (
                key not in previous
                or placeholders(previous[key]) != placeholders(value)
                or (not reviewed and (args.force or previous_hashes.get(key) != hashes[key]))
            )
        ]
        catalog = {key: previous[key] for key in source if key in previous}
        catalog.update({key: source[key] for key in DO_NOT_TRANSLATE if key in source})
        review: list[str] = list(status["locales"].get(locale, {}).get("needs_review", []))
        if todo:
            engines = {"llm": llm_translator, "m2m": m2m_translator, "chain": chain_translator}
            translated, needs_review = translate_labels(todo, engines[args.engine](locale))
            catalog.update(translated)
            review = sorted(set(key for key in review if key in source and key not in translated) | set(needs_review))
        ordered = {key: catalog[key] for key in source if key in catalog}  # same order as the source; obsolete keys pruned
        output.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status["locales"][locale] = {
            "message_count": len(ordered),
            "status": "human_reviewed" if reviewed else "machine_generated_requires_native_review",
            "source_hashes": hashes,
            "needs_review": review,
            "notes": (["M2M-100 Punjabi uses Gurmukhi, not Shahmukhi."] if locale == "pa-Arab" and args.engine == "m2m" else []),
        }
        status["generated_at"] = datetime.now(timezone.utc).isoformat()
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{locale}: {len(todo)} translated, {len(review)} need review", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
