from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
registry_text = (ROOT / "apps/web/src/i18n/languages.ts").read_text(encoding="utf-8")
match_language = re.compile(r'\{ code: "([^"]+)", englishName: "([^"]+)", nativeName: "([^"]*)", direction: "(ltr|rtl)"')
languages = []
for match in match_language.finditer(registry_text):
    code, english, native, direction = match.groups()
    native = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), native)
    languages.append((code, english, native, direction))

catalog_dir = ROOT / "apps/web/src/i18n/catalogs"
english = json.loads((catalog_dir / "en.json").read_text(encoding="utf-8-sig"))
status = json.loads((catalog_dir / "catalog-status.json").read_text(encoding="utf-8-sig"))
source_keys = list(english)
engine = status.get("generation_engine", "Not recorded")
rows = []
counts = {"PRODUCTION": 0, "BETA": 0, "PLANNED": 0}
for code, english_name, native, direction in languages:
    path = catalog_dir / f"{code}.json"
    if path.exists():
        catalog = json.loads(path.read_text(encoding="utf-8-sig"))
        translated = sum(1 for key in source_keys if key in catalog and catalog[key] != key)
        percent = (translated / len(source_keys) * 100) if code != "en" else 100.0
        used_engine = "Source English" if code == "en" else engine
        tier = "PRODUCTION" if False else ("BETA" if percent >= 90 else "PLANNED")
    else:
        translated, percent, used_engine, tier = 0, 0.0, "None", "PLANNED"
    counts[tier] += 1
    qa = "Not run"
    result_engines = "Not verified"
    fonts_verified = "No"
    rtl_verified = "No" if direction == "rtl" else "N/A"
    screenshots = "No"
    rows.append((code, english_name, native or english_name, direction, f"{translated}/{len(source_keys)} ({percent:.1f}%)", used_engine, qa, result_engines, fonts_verified, rtl_verified, screenshots, tier))

columns = ["Code", "English", "Native", "Dir", "Catalog coverage", "Catalog engine", "QA score", "Results engines", "Font verified", "RTL verified", "Screenshots", "Tier"]
lines = ["# Language readiness", "", f"Last generated: {date.today().isoformat()} (offline inventory from checked-in catalog files).", "", f"**Registry:** {len(languages)} languages. **Catalogs:** {len([p for p in catalog_dir.glob('*.json') if p.name != 'catalog-status.json'])} locale files, including English. **Tier counts:** PRODUCTION {counts['PRODUCTION']} · BETA {counts['BETA']} · PLANNED {counts['PLANNED']}.", "", f"Coverage uses translated non-identical strings divided by the {len(source_keys)} source keys in `en.json`; English is the 100% source catalog. Locale metadata currently records `{engine}` and `machine_generated_requires_native_review`. A catalog score is not a language-quality score. No native QA score, results-translation engine coverage, verified font matrix, per-language RTL audit, or requested Home/Search/Compare screenshots are recorded, so no language qualifies for PRODUCTION yet.", "", "## Per-language inventory", "", "| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
for row in rows:
    lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
lines += ["", "## Tier rules", "", "- **PRODUCTION:** catalog is 100%, QA ≥ 90, result translation verified through at least two real engines, and fonts, RTL (when applicable), and screenshots verified on Home, Search, and Compare.", "- **BETA:** catalog coverage is at least 90% or QA remains pending; available with a Beta tag.", "- **PLANNED:** catalog coverage is below 90%; hide from production language pickers.", "", "Current checked-in generated locale files: " + ", ".join(sorted(p.stem for p in catalog_dir.glob("*.json") if p.name != "catalog-status.json")) + ".", "", "## Catalog generation", "", "Catalog generation is not run automatically in this report. The source metadata says M2M-100 local INT8 generated the present non-English catalogs. Native review is pending. Run the resumable generation/QA workflow only from a separate PowerShell window after the AI router and scripts are verified; exact commands will be added here when that workflow is ready.", "", "## Admin visibility", "", "The existing UI does not yet expose this inventory in an admin page. The report is the audited source of truth until the admin language-readiness table is implemented."]
(ROOT / "docs/LANGUAGES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
json_rows = [{"code": row[0], "englishName": row[1], "nativeName": row[2], "direction": row[3], "coverage": row[4], "catalogEngine": row[5], "qaScore": row[6], "resultsEngines": row[7], "fontVerified": row[8], "rtlVerified": row[9], "screenshots": row[10], "tier": row[11]} for row in rows]
(ROOT / "apps/web/src/i18n/language-readiness.json").write_text(json.dumps({"counts": counts, "languages": json_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote docs/LANGUAGES.md: languages={len(languages)}, catalogs={len([p for p in catalog_dir.glob('*.json') if p.name != 'catalog-status.json'])}, tiers={counts}")
