"""One-prompt credential smoke checks; never prints keys, bodies, prompts, or outputs."""
from __future__ import annotations

import os
import argparse
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
CLIENT = httpx.Client(timeout=12.0)


def report(name: str, status: int | str, model: str = "-") -> None:
    print(f"{name}: {status}; model={model}")


def test_openai_compatible(name: str, base_url: str, key_env: str, preferred: str | None = None,
                           free_only: bool = False) -> None:
    key = os.getenv(key_env, "")
    if not key:
        report(name, "skipped (no key)")
        return
    headers = {"Authorization": f"Bearer {key}"}
    try:
        listing = CLIENT.get(base_url + "/models", headers=headers)
        if listing.is_error:
            report(name, f"fails (model discovery HTTP {listing.status_code})")
            return
        models = listing.json().get("data", [])
        ids = [str(row.get("id", "")).removeprefix("models/") for row in models if row.get("id")]
        if free_only:
            ids = [str(row.get("id", "")).removeprefix("models/") for row in models
                   if str(row.get("id", "")).endswith(":free")
                   and (row.get("pricing") or {}).get("prompt") == "0"
                   and (row.get("pricing") or {}).get("completion") == "0"]
        if not ids:
            report(name, "fails (no eligible models)")
            return
        model = preferred if preferred in ids else next((item for item in ids if "flash" in item.lower()), ids[0])
        started = time.monotonic()
        response = CLIENT.post(base_url + "/chat/completions", headers=headers, json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with only OK."}],
            "max_tokens": 8,
            "temperature": 0,
        })
        outcome = "works" if response.is_success else f"fails (chat HTTP {response.status_code})"
        report(name, f"{outcome} ({(time.monotonic()-started)*1000:.0f}ms)", model)
    except Exception as exc:
        # Exception text can contain request details; emit only its type.
        report(name, f"fails ({type(exc).__name__})")


def list_qwen_free_models() -> None:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        report("openrouter_qwen_catalog", "skipped (no key)")
        return
    try:
        response = CLIENT.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {key}"})
        if response.is_error:
            report("openrouter_qwen_catalog", f"fails (HTTP {response.status_code})")
            return
        rows = response.json().get("data", [])
        ids = sorted({str(item.get("id", "")) for item in rows
                      if "qwen" in (str(item.get("id", "")) + " " + str(item.get("name", ""))).casefold()
                      and str(item.get("id", "")).endswith(":free")
                      and (item.get("pricing") or {}).get("prompt") == "0"
                      and (item.get("pricing") or {}).get("completion") == "0"})
        print("OpenRouter free Qwen model IDs: " + (", ".join(ids) if ids else "none available"))
    except Exception as exc:
        report("openrouter_qwen_catalog", f"fails ({type(exc).__name__})")


def test_tavily() -> None:
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        report("tavily", "skipped (no key)")
        return
    try:
        response = CLIENT.post("https://api.tavily.com/search", json={
            "api_key": key, "query": "machine learning in healthcare research", "search_depth": "basic", "max_results": 1,
        })
        report("tavily", "works" if response.is_success else f"fails (search HTTP {response.status_code})")
    except Exception as exc:
        report("tavily", f"fails ({type(exc).__name__})")


def test_exa() -> None:
    key = os.getenv("EXA_API_KEY", "")
    if not key:
        report("exa", "skipped (no key)")
        return
    try:
        response = CLIENT.post("https://api.exa.ai/search", headers={"x-api-key": key}, json={
            "query": "machine learning in healthcare research", "numResults": 1,
            "contents": {"text": False},
        })
        report("exa", "works" if response.is_success else f"fails (search HTTP {response.status_code})")
    except Exception as exc:
        report("exa", f"fails ({type(exc).__name__})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="gemini,openrouter,groq,tavily,exa")
    parser.add_argument("--list-qwen", action="store_true", help="List public zero-priced OpenRouter Qwen :free model IDs")
    args = parser.parse_args()
    selected = {name.strip() for name in args.providers.split(",")}
    if "gemini" in selected:
        test_openai_compatible("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                               "GEMINI_API_KEY", os.getenv("AI_ROUTER_MODEL_GEMINI", "gemini-3.8-flash"))
    if "openrouter" in selected:
        test_openai_compatible("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", free_only=True)
    if "groq" in selected:
        test_openai_compatible("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
                               os.getenv("AI_ROUTER_MODEL_GROQ", "openai/gpt-oss-20b"))
    if "tavily" in selected:
        test_tavily()
    if "exa" in selected:
        test_exa()
    if args.list_qwen:
        list_qwen_free_models()
    CLIENT.close()


if __name__ == "__main__":
    main()
