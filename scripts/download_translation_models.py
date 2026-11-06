#!/usr/bin/env python3
"""Download licensed, CPU/int8 local translation models without API credentials.

Run from the repository root after installing apps/translator-local requirements.
OPUS conversion also needs a CPU PyTorch build; see docs/translation-setup.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "models"
ARGOS_ROOT = MODEL_ROOT / "argos"
OPUS_PAIRS = ("ur", "ar", "fa", "hi", "zh", "es", "fr", "de", "tr")
M2M_REPO = "JustFrederik/m2m_100_418m_ct2_int8"
M2M_BASE = "facebook/m2m100_418M"
M2M_REVISION = "main"
APPROVED_LICENSES = {"apache-2.0", "cc-by-4.0", "mit"}


def _license(info: Any) -> str | None:
    card = getattr(info, "card_data", None)
    if card is None:
        return None
    values = card.to_dict() if hasattr(card, "to_dict") else {}
    value = values.get("license")
    return str(value).casefold() if value else None


def _write_manifest(manifest: dict[str, Any]) -> None:
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    (MODEL_ROOT / "models-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _download_m2m(hub: Any, manifest: dict[str, Any]) -> None:
    info = hub.model_info(M2M_REPO, revision=M2M_REVISION)
    if _license(info) != "mit":
        raise RuntimeError(f"Refusing M2M conversion with unverified license: {_license(info)!r}")
    destination = MODEL_ROOT / "m2m100" / "ct2"
    destination.mkdir(parents=True, exist_ok=True)
    revision = str(info.sha)
    hub.snapshot_download(
        repo_id=M2M_REPO, revision=revision, local_dir=str(destination),
        allow_patterns=["model.bin", "shared_vocabulary.txt", "spm.128k.model", "config.json", "README.md"],
    )
    required = (destination / "model.bin", destination / "shared_vocabulary.txt", destination / "spm.128k.model")
    if not all(path.is_file() for path in required):
        raise RuntimeError("The pinned M2M CTranslate2 model is missing required files")
    tokenizer = MODEL_ROOT / "m2m100" / "tokenizer"
    hub.snapshot_download(
        repo_id=M2M_BASE, revision="55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636", local_dir=str(tokenizer),
        allow_patterns=["config.json", "generation_config.json", "special_tokens_map.json", "tokenizer_config.json", "sentencepiece.bpe.model", "vocab.json"],
    )
    manifest["m2m100"] = {
        "model": M2M_BASE, "converted_repository": M2M_REPO, "revision": revision,
        "license": "MIT", "license_source": f"https://huggingface.co/{M2M_REPO}",
        "base_license": "MIT", "base_license_source": f"https://huggingface.co/{M2M_BASE}",
        "quantization": "int8", "engine": "CTranslate2", "commercial_use": True,
        "languages": "101 M2M-100 language IDs; Resora maps its configured locales in engine_manager.py",
    }
    print(f"M2M-100 INT8 ready ({revision})", flush=True)


def _opus_model(repo: str, key: str, hub: Any, manifest: dict[str, Any], keep_sources: bool) -> None:
    info = hub.model_info(repo)
    model_license = _license(info)
    if model_license not in APPROVED_LICENSES:
        print(f"Excluded {repo}: model-card license is missing or not approved ({model_license or 'unknown'})", flush=True)
        return
    source = MODEL_ROOT / "opus" / key / "source"
    output = MODEL_ROOT / "opus" / key / "ct2"
    source.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    revision = str(info.sha)
    hub.snapshot_download(repo_id=repo, revision=revision, local_dir=str(source))
    try:
        import ctranslate2
        copy_files = [name for name in ("README.md", "generation_config.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.json", "source_vocab.json", "target_vocab.json", "source.spm", "target.spm") if (source / name).exists()]
        converter = ctranslate2.converters.TransformersConverter(str(source), copy_files=copy_files, low_cpu_mem_usage=True)
        converter.convert(str(output), quantization="int8", force=True)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    if not (output / "model.bin").is_file():
        raise RuntimeError(f"CTranslate2 conversion did not create model.bin for {repo}")
    tokenizer = MODEL_ROOT / "opus" / key / "tokenizer"
    tokenizer.mkdir(parents=True, exist_ok=True)
    tokenizer_files = ("config.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.json", "source_vocab.json", "target_vocab.json", "source.spm", "target.spm")
    for filename in tokenizer_files:
        file_path = source / filename
        if file_path.is_file():
            shutil.copy2(file_path, tokenizer / filename)
    if not (tokenizer / "config.json").is_file():
        raise RuntimeError(f"Tokenizer config is missing for {repo}")
    if not keep_sources:
        shutil.rmtree(source, ignore_errors=True)
    manifest["opus_models"].append({
        "key": key, "pair": key.replace("opus-mt-", "").replace("-", "->", 1),
        "model": repo, "revision": revision, "license": model_license,
        "license_source": f"https://huggingface.co/{repo}",
        "license_url": f"https://huggingface.co/{repo}/blob/{revision}/README.md",
        "commercial_use": True, "quantization": "int8", "engine": "CTranslate2",
        "attribution": "Helsinki-NLP OPUS-MT; include the model card license and cited OPUS source when redistributing.",
    })
    print(f"Converted {repo} ({model_license}, int8)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default="ur,ar,fa,hi,zh,es,fr,de,tr,ps,sd", help="Comma-separated Resora language codes")
    parser.add_argument("--no-m2m100", action="store_true", help="Skip the shared M2M-100 model")
    parser.add_argument("--no-opus", action="store_true", help="Skip per-pair OPUS-MT models")
    parser.add_argument("--keep-sources", action="store_true", help="Keep original model files after int8 conversion")
    args = parser.parse_args()
    selected = {item.strip() for item in args.languages.split(",") if item.strip()}
    supported = {"en", "ur", "ar", "fa", "hi", "bn", "pa-Arab", "tr", "id", "ms", "zh", "zh-Hans", "zh-Hant", "ja", "ko", "vi", "th", "es", "pt", "pt-BR", "pt-PT", "fr", "de", "it", "nl", "pl", "ru", "uk", "sv", "el", "ro", "cs", "hu", "he", "sw", "ta", "ps", "sd"}
    invalid = selected - supported
    if invalid:
        parser.error(f"Unsupported language codes: {', '.join(sorted(invalid))}")
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import RepositoryNotFoundError
        hub = HfApi()
    except ImportError:
        print("Install apps/translator-local/requirements.txt first (no API token is needed for these public models).", file=sys.stderr)
        return 2

    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = MODEL_ROOT / "models-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {"schema_version": 1, "argos_models": [], "opus_models": []}
    manifest.setdefault("argos_models", [])
    manifest.setdefault("opus_models", [])

    try:
        if not args.no_m2m100:
            _download_m2m(hub, manifest)
        if not args.no_opus:
            for language in sorted(selected & set(OPUS_PAIRS)):
                for source, target in (("en", language), (language, "en")):
                    pair = f"{source}-{target}"
                    key = f"opus-mt-{pair}"
                    if any(record.get("key") == key for record in manifest["opus_models"]):
                        output = MODEL_ROOT / "opus" / key / "ct2" / "model.bin"
                        tokenizer_config = MODEL_ROOT / "opus" / key / "tokenizer" / "config.json"
                        if output.is_file() and tokenizer_config.is_file():
                            continue
                    try:
                        _opus_model(f"Helsinki-NLP/{key}", key, hub, manifest, args.keep_sources)
                    except RepositoryNotFoundError:
                        manifest.setdefault("opus_excluded", []).append({"key": key, "reason": "upstream model repository not found; use M2M-100 fallback"})
                        print(f"Excluded {key}: upstream pair model is not published", flush=True)
                    _write_manifest(manifest)
    except Exception as exc:
        _write_manifest(manifest)
        print(f"Model preparation stopped safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    manifest["selected_languages"] = sorted(selected)
    manifest["excluded_languages"] = sorted(selected - set(OPUS_PAIRS))
    _write_manifest(manifest)
    print(f"Model inventory saved to {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
