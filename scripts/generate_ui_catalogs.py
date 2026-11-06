from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "apps" / "web" / "src" / "i18n" / "catalogs"
TRANSLATOR_DIR = ROOT / "apps" / "translator-local"
sys.path.insert(0, str(TRANSLATOR_DIR))

from engine_manager import M2M_CODES, translate_batch_with_engine  # noqa: E402


LOCALES = [
    "en", "ur", "ar", "fa", "hi", "bn", "pa-Arab", "tr", "id", "ms",
    "zh-Hans", "zh-Hant", "ja", "ko", "vi", "th", "es", "pt-BR", "pt-PT",
    "fr", "de", "it", "nl", "pl", "ru", "uk", "sv", "el", "ro", "cs",
    "hu", "he", "sw", "ta", "ps", "sd",
]
TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}|\b(Resora|API|AI|FYP|PDFs?|PWA|RTL|LTR|WCAG|DOI|URL|JSON|CSV|HTML|CSS|TTS|RAG|OCR|OpenAlex|Crossref|PubMed|arXiv|CORE|PMC|DOAJ|Unpaywall|Scopus|IEEE|ACM|Springer|ScienceDirect|Wiley|DBLP|Dimensions|LaTeX|GitHub|Trivy)\b", re.I)
MARKER = re.compile(r"RESORATOKENX\d+XEND")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static UI catalogs with the installed local M2M-100 model.")
    parser.add_argument("--languages", nargs="*", choices=LOCALES, default=[code for code in LOCALES if code != "en"])
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0, help="Translate only the first N messages for a smoke run.")
    args = parser.parse_args()

    source_path = CATALOG_DIR / "en.json"
    source: dict[str, str] = json.loads(source_path.read_text(encoding="utf-8"))
    entries = list(source.items())
    if args.limit:
        entries = entries[:args.limit]
    status: dict[str, object] = {
        "source_locale": "en",
        "source_message_count": len(source),
        "generation_engine": "M2M-100 local INT8",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "machine_generated_requires_native_review",
        "locales": {"en": {"message_count": len(source), "status": "source_locale", "notes": []}},
    }
    status_path = CATALOG_DIR / "catalog-status.json"
    if not args.limit and status_path.exists():
        try:
            previous = json.loads(status_path.read_text(encoding="utf-8"))
            if previous.get("source_message_count") == len(source):
                status = previous
        except (OSError, json.JSONDecodeError):
            pass
    status["source_message_count"] = len(source)
    status["generated_at"] = datetime.now(timezone.utc).isoformat()

    def write_status() -> None:
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_status()
    for locale in args.languages:
        output_path = CATALOG_DIR / f"{locale}.json"
        if not args.limit and output_path.exists():
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
                if len(existing) == len(source) and all(key in existing for key in source):
                    status.setdefault("locales", {}).setdefault(locale, {
                        "message_count": len(existing), "status": "machine_generated_requires_native_review",
                        "untranslated_fallback_count": 0, "untranslated_fallback_keys": [], "notes": [],
                    })
                    write_status()
                    print(f"{locale}: already complete", flush=True)
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        target_code = M2M_CODES.get(locale, locale)
        output: dict[str, str] = {}
        fallbacks: list[str] = []
        for offset in range(0, len(entries), max(1, args.batch_size)):
            chunk = entries[offset:offset + max(1, args.batch_size)]
            layouts: list[list[tuple[str, str]]] = []
            fragments: list[str] = []
            token_maps: list[dict[str, str]] = []
            for message, _english in chunk:
                tokens: dict[str, str] = {}
                layout: list[tuple[str, str]] = []
                cursor = 0

                def protect(match: re.Match[str]) -> str:
                    marker = f"RESORATOKENX{len(tokens)}XEND"
                    tokens[marker] = match.group(0)
                    fragment = message[nonlocal_cursor[0]:match.start()]
                    if fragment:
                        layout.append(("fragment", str(len(fragments))))
                        fragments.append(fragment)
                    layout.append(("token", marker))
                    nonlocal_cursor[0] = match.end()
                    return marker

                nonlocal_cursor = [cursor]
                TOKEN.sub(protect, message)
                cursor = nonlocal_cursor[0]
                tail = message[cursor:]
                if tail:
                    layout.append(("fragment", str(len(fragments))))
                    fragments.append(tail)
                layouts.append(layout)
                token_maps.append(tokens)
            try:
                translated_fragments = translate_batch_with_engine("m2m100", fragments, "en", target_code) if fragments else []
            except Exception:
                translated_fragments = []
            if len(translated_fragments) != len(fragments):
                raise RuntimeError(f"M2M-100 returned an incomplete {locale} batch at {offset}")
            for (message, _), layout, tokens in zip(chunk, layouts, token_maps):
                if any(not translated_fragments[int(value)].strip() for kind, value in layout if kind == "fragment"):
                    value = message
                    fallbacks.append(message)
                else:
                    value = "".join(
                        tokens[token] if kind == "token" else translated_fragments[int(token)]
                        for kind, token in layout
                    )
                output[message] = value
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        notes = []
        if locale == "pa-Arab":
            notes.append("M2M-100 Punjabi output uses the Gurmukhi token; verify or replace with Shahmukhi before production.")
        if locale == "zh-Hant":
            notes.append("M2M-100 uses the generic zh token; verify Traditional Chinese script before production.")
        status["locales"][locale] = {
            "message_count": len(output), "status": "machine_generated_requires_native_review",
            "untranslated_fallback_count": len(fallbacks), "untranslated_fallback_keys": fallbacks,
            "notes": notes,
        }
        write_status()
        print(f"{locale}: {len(output)} messages; {len(fallbacks)} English fallbacks", flush=True)


if __name__ == "__main__":
    main()
