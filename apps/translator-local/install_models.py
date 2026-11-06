from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from argostranslate import package


ROOT = Path(os.getenv("ARGOS_MODEL_DIR", "/models/argos"))
APPROVED_LANGUAGES = {
    "en", "ur", "ar", "fa", "hi", "bn", "pa-Arab", "tr", "id", "ms",
    "zh-Hans", "zh-Hant", "ja", "ko", "vi", "th", "es", "pt-BR", "pt-PT",
    "fr", "de", "it", "nl", "pl", "ru", "uk", "sv", "el", "ro", "cs",
    "hu", "he", "sw", "ta", "ps", "sd",
}
ARGOS_CODES = {
    "zh-Hans": "zh", "zh-Hant": "zt", "pt-BR": "pb", "pt-PT": "pt",
    "pa-Arab": "pa", "he": "he",
}
UPSTREAM_LICENSE = "mit-or-cc0"
UPSTREAM_LICENSE_EVIDENCE = "https://github.com/argosopentech/argos-translate/issues/533"
def is_official_url(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host == "argos-net.com" or host.endswith(".argos-net.com") or host == "argosopentech.nyc3.digitaloceanspaces.com"


def download_limited(url: str, remaining_bytes: int) -> Path:
    if not is_official_url(url):
        raise ValueError("Unapproved Argos model host")
    request = urllib.request.Request(url, headers={"User-Agent": "Resora-Argos-Model-Installer/1.0"})
    temporary_path: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            if not is_official_url(response.geturl()):
                raise ValueError("Argos model download redirected to an unapproved host")
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > remaining_bytes:
                raise ValueError("Argos model download budget reached")
            with tempfile.NamedTemporaryFile(prefix="resora-argos-", suffix=".argosmodel", delete=False) as output:
                temporary_path = output.name
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > remaining_bytes:
                        raise ValueError("Argos model download budget reached")
                    output.write(chunk)
        return Path(temporary_path)
    except Exception:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        raise


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    requested = {
        item.strip() for item in os.getenv("ARGOS_TARGET_LANGUAGES", "en,es,fr,de,ru,zh,ar,hi").split(",")
        if item.strip()
    } & APPROVED_LANGUAGES
    codes = {ARGOS_CODES.get(code, code.split("-")[0]) for code in requested}
    codes.discard("en")

    packs = package.get_available_packages()
    existing = {(item.from_code, item.to_code) for item in package.get_installed_packages()}
    max_download_bytes = max(0, int(os.getenv("ARGOS_MAX_DOWNLOAD_MB", "4096"))) * 1024 * 1024
    downloaded_bytes = 0
    new_install_count = 0
    records: list[dict[str, str]] = []
    for language in sorted(codes):
        for source, target in (("en", language), (language, "en")):
            candidate = next((item for item in packs if item.type == "translate" and item.from_code == source and item.to_code == target), None)
            if candidate is None:
                continue
            links = [str(url) for url in candidate.links]
            if not links or not any(is_official_url(link) for link in links):
                continue
            # The official package index does not publish license or size fields.
            # The Argos maintainer states the distributed Argos model binaries use
            # the same MIT/CC0 terms; pin installation to the official index only.
            if downloaded_bytes >= max_download_bytes:
                break
            if (source, target) in existing:
                records.append({
                    "package": f"{source}->{target}", "version": str(candidate.package_version),
                    "source": links[0], "license": UPSTREAM_LICENSE, "license_evidence": UPSTREAM_LICENSE_EVIDENCE,
                    "source_url": links[0], "commercial_use": True,
                })
                continue
            archive: Path | None = None
            try:
                url = next(link for link in links if is_official_url(link))
                archive = download_limited(url, max_download_bytes - downloaded_bytes)
                size = archive.stat().st_size
                package.install_from_path(str(archive))
                existing.add((source, target))
                new_install_count += 1
                records.append({
                    "package": f"{source}->{target}", "version": str(candidate.package_version),
                    "source": links[0], "license": UPSTREAM_LICENSE, "license_evidence": UPSTREAM_LICENSE_EVIDENCE,
                    "source_url": links[0], "commercial_use": True,
                })
                downloaded_bytes += size
            except Exception as exc:
                print(f"Skipping {source}->{target}: {type(exc).__name__}", flush=True)
            finally:
                if archive:
                    archive.unlink(missing_ok=True)

    manifest = {
        "license_basis": UPSTREAM_LICENSE,
        "license_evidence": UPSTREAM_LICENSE_EVIDENCE,
        "index_license": "https://github.com/argosopentech/argospm-index/blob/main/LICENSE",
        "index_metadata_has_per_pack_license": False,
        "installed_pairs": sorted([f"{source}->{target}" for source, target in existing]),
        "installed_packs": records,
    }
    (ROOT / "translation-licenses.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    models_manifest_path = ROOT.parent / "models-manifest.json"
    try:
        models_manifest = json.loads(models_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        models_manifest = {"schema_version": 1, "opus_models": []}
    by_pair = {item.get("pair"): item for item in models_manifest.get("argos_models", []) if item.get("pair")}
    for item in records:
        source, target = item["package"].split("->", 1)
        by_pair[item["package"]] = {
            "pair": item["package"], "key": item["package"], "model": item["source_url"],
            "package_version": item["version"], "license": UPSTREAM_LICENSE,
            "license_source": UPSTREAM_LICENSE_EVIDENCE, "commercial_use": True,
            "engine": "Argos Translate", "attribution": "Argos Translate package; license basis is the upstream maintainer statement, since the package index has no per-pack license field.",
        }
    models_manifest["schema_version"] = max(1, int(models_manifest.get("schema_version", 1)))
    models_manifest["argos_models"] = list(by_pair.values())
    models_manifest_path.write_text(json.dumps(models_manifest, indent=2), encoding="utf-8")
    print(f"Argos packs available: {len(manifest['installed_pairs'])}; new installs: {new_install_count}", flush=True)


if __name__ == "__main__":
    main()
