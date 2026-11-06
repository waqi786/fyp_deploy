#!/usr/bin/env python3
"""Exercise the configured translation chain against all Resora locales.

Run from the repository root with the API environment loaded:
    python scripts/verify_translation.py
"""
from __future__ import annotations

import json
import sys
import argparse
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.services.language.config import SUPPORTED_LANGUAGES  # noqa: E402
from app.services.search.translation import TranslationUnavailable, translation_metrics, translate_text  # noqa: E402

SENTENCE = "The model reached 86.9% accuracy [12]. DOI 10.1007/s12525-021-00475-2; equation x^2."
PROTECTED = ("86.9%", "[12]", "10.1007/s12525-021-00475-2", "x^2")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Resora translation providers and protected academic tokens.")
    parser.add_argument("--provider-order", help="Override provider order, e.g. translator_local for local-only verification")
    parser.add_argument("--only", help="Verify one language code (useful for a live Search result smoke check)")
    args = parser.parse_args()
    if args.provider_order:
        os.environ["TRANSLATION_PROVIDER_ORDER"] = args.provider_order
    results = []
    languages = [language for language in SUPPORTED_LANGUAGES if not args.only or language.code == args.only]
    for language in languages:
        before = translation_metrics()
        started = time.perf_counter()
        try:
            output = translate_text(SENTENCE, language.code, source_language="en")
            elapsed = time.perf_counter() - started
            after = translation_metrics()
            used = [name for name, stats in after.items() if stats.get("successes", 0) > before.get(name, {}).get("successes", 0)]
            intact = all(token in output for token in PROTECTED)
            local_engines = [name.removeprefix("local_") for name in used if name.startswith("local_")]
            results.append({"language": language.code, "success": bool(output.strip()) and intact,
                            "provider": local_engines[-1] if local_engines else used[-1] if used else "cache", "protected_tokens_intact": intact,
                            "output_nonempty": bool(output.strip()), "seconds": round(elapsed, 3)})
        except (TranslationUnavailable, ValueError) as exc:
            elapsed = time.perf_counter() - started
            results.append({"language": language.code, "success": False, "provider": None,
                            "protected_tokens_intact": False, "reason": str(exc), "seconds": round(elapsed, 3)})
    print(json.dumps({"total": len(results), "succeeded": sum(item["success"] for item in results),
                      "average_seconds_per_sentence": round(sum(item["seconds"] for item in results) / max(1, len(results)), 3),
                      "results": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["success"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
