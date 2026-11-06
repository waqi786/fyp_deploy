from __future__ import annotations

import gc
import json
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

_FILE_PARENTS = Path(__file__).resolve().parents
_DEFAULT_ROOT = _FILE_PARENTS[2] / "models" if len(_FILE_PARENTS) > 2 else Path("/models")
ROOT = Path(os.getenv("RESORA_MODELS_DIR", str(_DEFAULT_ROOT)))
M2M_LANGUAGES = {
    "af", "am", "ar", "ast", "az", "ba", "be", "bg", "bn", "br", "bs", "ca", "ceb", "cs", "cy", "da", "de", "el", "en", "es", "et", "fa", "ff", "fi", "fr", "fy", "ga", "gd", "gl", "gu", "ha", "he", "hi", "hr", "ht", "hu", "hy", "id", "ig", "ilo", "is", "it", "ja", "jv", "ka", "kk", "km", "kn", "ko", "lb", "lg", "ln", "lo", "lt", "lv", "mg", "mk", "ml", "mn", "mr", "ms", "my", "ne", "nl", "no", "ns", "oc", "or", "pa", "pl", "ps", "pt", "ro", "ru", "sd", "si", "sk", "sl", "so", "sq", "sr", "ss", "su", "sv", "sw", "ta", "th", "tl", "tn", "tr", "uk", "ur", "uz", "vi", "wo", "xh", "yi", "yo", "zh", "zu",
}
APP_LANGUAGES = {
    "en", "ur", "ar", "fa", "hi", "bn", "pa-Arab", "tr", "id", "ms", "zh-Hans", "zh-Hant", "ja", "ko", "vi", "th", "es", "pt-BR", "pt-PT", "fr", "de", "it", "nl", "pl", "ru", "uk", "sv", "el", "ro", "cs", "hu", "he", "sw", "ta", "ps", "sd",
}
M2M_CODES = {"zh-Hans": "zh", "zh-Hant": "zh", "pt-BR": "pt", "pt-PT": "pt", "pa-Arab": "pa"}
OPUS_CODES = {"zh-Hans": "zh", "zh-Hant": "zh", "pt-BR": "pb", "pt-PT": "pt", "pa-Arab": "pa"}
_MODELS: OrderedDict[str, tuple[Any, Any]] = OrderedDict()
_LOCK = threading.RLock()
_LIMIT = max(1, int(os.getenv("LOCAL_TRANSLATION_MAX_LOADED_MODELS", "1")))


def _load_ct2(key: str, engine: str) -> tuple[Any, Any]:
    with _LOCK:
        loaded = _MODELS.get(key)
        if loaded:
            _MODELS.move_to_end(key)
            return loaded
        import ctranslate2
        from transformers import AutoTokenizer

        if engine == "m2m100":
            model_path = ROOT / "m2m100" / "ct2"
            tokenizer_path = ROOT / "m2m100" / "tokenizer"
        else:
            model_path = ROOT / "opus" / key / "ct2"
            tokenizer_path = ROOT / "opus" / key / "tokenizer"
        if not (model_path / "model.bin").is_file():
            raise FileNotFoundError(f"{engine} model is not downloaded")
        translator = ctranslate2.Translator(
            str(model_path), device="cpu", compute_type="int8",
            inter_threads=max(1, int(os.getenv("LOCAL_TRANSLATION_THREADS", "1"))),
            intra_threads=max(1, int(os.getenv("LOCAL_TRANSLATION_THREADS", "1"))),
        )
        tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True, use_fast=False)
        _MODELS[key] = (translator, tokenizer)
        while len(_MODELS) > _LIMIT:
            _MODELS.popitem(last=False)
            gc.collect()
        return translator, tokenizer


def clear_loaded_models() -> None:
    with _LOCK:
        _MODELS.clear()
        gc.collect()


def loaded_model_names() -> list[str]:
    with _LOCK:
        return list(_MODELS)


def _manifest() -> dict[str, Any]:
    path = ROOT / "models-manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _approved_opus_pairs() -> dict[str, dict[str, Any]]:
    records = _manifest().get("opus_models", [])
    accepted: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("license") not in {"apache-2.0", "cc-by-4.0", "mit"}:
            continue
        if record.get("commercial_use") is not True:
            continue
        pair = record.get("pair")
        model_key = record.get("key")
        if (isinstance(pair, str) and isinstance(model_key, str)
                and (ROOT / "opus" / model_key / "ct2" / "model.bin").is_file()
                and (ROOT / "opus" / model_key / "tokenizer" / "config.json").is_file()):
            accepted[pair] = record
    return accepted


def _opus_display_pair(pair: str) -> str:
    source, separator, target = pair.partition("->")
    inverse = {value: key for key, value in reversed(list(OPUS_CODES.items()))}
    return f"{inverse.get(source, source)}->{inverse.get(target, target)}" if separator else pair


def argos_license_pairs() -> dict[str, dict[str, Any]]:
    records = _manifest().get("argos_models", [])
    approved: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("license") not in {"mit", "mit-or-cc0", "cc0-1.0", "cc-by-4.0", "apache-2.0"} or record.get("commercial_use") is not True:
            continue
        pair = record.get("pair")
        if isinstance(pair, str):
            approved[pair] = record
    return approved


def engine_status() -> dict[str, dict[str, Any]]:
    disabled = {part.strip().casefold() for part in os.getenv("TRANSLATION_DISABLE_ENGINES", "").split(",") if part.strip()}
    argos_pairs = argos_license_pairs()
    m2m_path = ROOT / "m2m100" / "ct2" / "model.bin"
    tokenizer_path = ROOT / "m2m100" / "tokenizer" / "vocab.json"
    opus_pairs = _approved_opus_pairs()
    argos_state = "disabled" if "argos" in disabled else "available" if argos_pairs else "missing"
    m2m_state = "disabled" if "m2m100" in disabled else "available" if m2m_path.is_file() and tokenizer_path.is_file() else "missing"
    opus_state = "disabled" if "opus_mt" in disabled or "opus" in disabled else "available" if opus_pairs else "missing"
    return {
        "argos": {"status": argos_state, "state": argos_state, "loaded": False, "languages": sorted({code for pair in argos_pairs for code in pair.split("->")}), "pairs": sorted(argos_pairs)},
        "m2m100": {"status": m2m_state, "state": "loaded" if m2m_state == "available" and "m2m100" in _MODELS else m2m_state, "languages": sorted(APP_LANGUAGES), "model_languages": sorted(M2M_LANGUAGES), "quantization": "int8", "loaded": "m2m100" in _MODELS, "script_notes": {"pa-Arab": "M2M-100 Punjabi output uses the Gurmukhi token; Shahmukhi is not guaranteed", "zh-Hant": "M2M-100 uses the zh token; Traditional Chinese script is not guaranteed"}},
        "opus_mt": {"status": opus_state, "state": "loaded" if opus_state == "available" and any(key.startswith("opus-") for key in _MODELS) else opus_state, "languages": sorted({code for pair in map(_opus_display_pair, opus_pairs) for code in pair.split("->")}), "pairs": sorted(map(_opus_display_pair, opus_pairs)), "loaded": any(key.startswith("opus-") for key in _MODELS)},
    }


def _translate_m2m(text: str, source: str, target: str) -> str:
    translator, tokenizer = _load_ct2("m2m100", "m2m100")
    source_code = M2M_CODES.get(source, source)
    target_code = M2M_CODES.get(target, target)
    if source_code not in M2M_LANGUAGES or target_code not in M2M_LANGUAGES:
        raise ValueError("M2M-100 has no code for this language")
    tokenizer.src_lang = source_code
    source_tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
    output = translator.translate_batch([source_tokens], target_prefix=[[f"__{target_code}__"]], max_decoding_length=512)
    target_tokens = output[0].hypotheses[0]
    target_ids = tokenizer.convert_tokens_to_ids(target_tokens)
    return tokenizer.decode(target_ids, skip_special_tokens=True).strip()


def _translate_opus(text: str, source: str, target: str) -> str:
    pair = f"{OPUS_CODES.get(source, source)}->{OPUS_CODES.get(target, target)}"
    records = _approved_opus_pairs()
    if pair not in records:
        raise LookupError("OPUS-MT pair is not installed")
    key = records[pair]["key"]
    translator, tokenizer = _load_ct2(key, "opus_mt")
    tokens = tokenizer.tokenize(text)
    output = translator.translate_batch([tokens], max_decoding_length=512)
    return tokenizer.convert_tokens_to_string(output[0].hypotheses[0]).strip()


def translate_with_engine(engine: str, text: str, source: str, target: str) -> str:
    disabled = {part.strip().casefold() for part in os.getenv("TRANSLATION_DISABLE_ENGINES", "").split(",") if part.strip()}
    if engine in disabled or (engine == "opus_mt" and "opus" in disabled):
        raise LookupError(f"{engine} disabled")
    if source == target:
        return text
    if engine == "m2m100":
        return _translate_m2m(text, source, target)
    if engine == "opus_mt":
        return _translate_opus(text, source, target)
    if engine != "argos":
        raise LookupError("Unknown local translation engine")
    allowed_pairs = argos_license_pairs()
    from argostranslate import translate

    installed = {language.code: language for language in translate.get_installed_languages()}
    source_code = M2M_CODES.get(source, source.split("-")[0])
    target_code = M2M_CODES.get(target, target.split("-")[0])
    source_language, target_language = installed.get(source_code), installed.get(target_code)
    if source_language is None or target_language is None:
        raise LookupError("Argos language pack is not installed")
    direct_key = f"{source_code}->{target_code}"
    if direct_key in allowed_pairs:
        direct = source_language.get_translation(target_language)
        if direct is not None:
            return direct.translate(text)
    pivot = installed.get("en")
    first_key, second_key = f"{source_code}->en", f"en->{target_code}"
    if source_code != "en" and target_code != "en" and pivot is not None and first_key in allowed_pairs and second_key in allowed_pairs:
        first = source_language.get_translation(pivot)
        second = pivot.get_translation(target_language)
        if first is not None and second is not None:
            return second.translate(first.translate(text))
    raise LookupError("No verified Argos route for this language pair")


def translate_batch_with_engine(engine: str, texts: list[str], source: str, target: str) -> list[str]:
    if engine == "m2m100":
        translator, tokenizer = _load_ct2("m2m100", "m2m100")
        source_code, target_code = M2M_CODES.get(source, source), M2M_CODES.get(target, target)
        if source_code not in M2M_LANGUAGES or target_code not in M2M_LANGUAGES:
            raise LookupError("M2M-100 has no code for this language")
        tokenizer.src_lang = source_code
        token_batch = [tokenizer.convert_ids_to_tokens(tokenizer.encode(text)) for text in texts]
        output = translator.translate_batch(token_batch, target_prefix=[[f"__{target_code}__"]] * len(texts), max_decoding_length=512)
        return [tokenizer.decode(tokenizer.convert_tokens_to_ids(item.hypotheses[0]), skip_special_tokens=True).strip() for item in output]
    if engine == "opus_mt":
        pair = f"{OPUS_CODES.get(source, source)}->{OPUS_CODES.get(target, target)}"
        record = _approved_opus_pairs().get(pair)
        if not record:
            raise LookupError("OPUS-MT pair is not installed")
        translator, tokenizer = _load_ct2(record["key"], "opus_mt")
        output = translator.translate_batch([tokenizer.tokenize(text) for text in texts], max_decoding_length=512)
        return [tokenizer.convert_tokens_to_string(item.hypotheses[0]).strip() for item in output]
    return [translate_with_engine(engine, text, source, target) for text in texts]


def license_inventory() -> dict[str, Any]:
    manifest = _manifest()
    return {"status": "ready" if manifest else "models_missing", **manifest}
