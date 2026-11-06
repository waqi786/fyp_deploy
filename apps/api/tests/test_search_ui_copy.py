"""Search interface text fill: placeholders survive, broken output is dropped, results are cached. Fake translator only."""

import json

import pytest

from app.services.search import ui_copy
from app.services.search.ui_copy import SearchUiCopyService, UnsupportedLanguage


@pytest.fixture
def source(monkeypatch, tmp_path):
    english = {
        "findResearch": "Find research.",
        "aboutResults": "About {count} {unit}",
        "researchWithResora": "Research with Resora",
        "exampleDoi": "10.1038/s41586-020-2649-2",
        "broken": "Switched to {language}",
    }
    path = tmp_path / "ui_copy_en.json"
    path.write_text(json.dumps(english), encoding="utf-8")
    monkeypatch.setattr(ui_copy, "SOURCE_FILE", path)
    return english


def fake_translator(calls):
    def translate(values, target):
        calls.append(list(values))
        outputs = []
        for value in values:
            if value.startswith("Switched to"):
                outputs.append("منتقل ہو گیا")  # lost the masked placeholder → must be rejected
            else:
                outputs.append(f"«{value}»")
        return outputs

    return translate


def test_fill_keeps_placeholders_and_protected_names(source, tmp_path):
    calls: list[list[str]] = []
    service = SearchUiCopyService(cache_dir=tmp_path / "cache", translator=fake_translator(calls))
    result = service.catalog("ur")
    messages = result["messages"]
    assert messages["aboutResults"] == "«About {count} {unit}»"
    assert messages["researchWithResora"] == "«Research with Resora»"  # "Resora" masked, restored untouched
    assert messages["exampleDoi"] == source["exampleDoi"]  # identifiers are copied, never sent
    assert "broken" not in messages and result["complete"] is False
    assert all("Resora" not in value for batch in calls for value in batch)  # protected term was masked


def test_results_are_cached_and_only_changes_are_retranslated(source, tmp_path):
    calls: list[list[str]] = []
    service = SearchUiCopyService(cache_dir=tmp_path / "cache", translator=fake_translator(calls))
    service.catalog("ur")
    first_round = len(calls)
    service.catalog("ur")
    # Only the label that failed last time is tried again.
    assert len(calls) == first_round + 1 and calls[-1] == ["Switched to 9301"]


def test_unknown_language_is_rejected(source, tmp_path):
    with pytest.raises(UnsupportedLanguage):
        SearchUiCopyService(cache_dir=tmp_path).catalog("xx")


def test_engine_failure_returns_what_is_cached(source, tmp_path):
    def failing(values, target):
        raise RuntimeError("engine down")

    result = SearchUiCopyService(cache_dir=tmp_path, translator=failing).catalog("de")
    assert result["complete"] is False and result["messages"] == {"exampleDoi": source["exampleDoi"]}


def test_ai_router_translation_sends_public_labels_only(monkeypatch):
    import app.services.ai_router as ai_router

    seen: dict = {}

    class FakeRouter:
        routes = {"short_translation": ()}

        def complete(self, task, prompt, **kwargs):
            seen.update(task=task, prompt=json.loads(prompt), **kwargs)
            labels = json.loads(prompt)["labels"]
            text = json.dumps({key: f"T:{value}" for key, value in labels.items()})
            assert kwargs["validator"](text)
            return type("Response", (), {"text": text})()

    monkeypatch.setattr(ai_router, "get_default_router", lambda: FakeRouter())
    assert ui_copy.llm_translate_labels(["Home", "Saved"], "ur") == ["T:Home", "T:Saved"]
    assert seen["task"] == "short_translation" and seen["user_content"] is False