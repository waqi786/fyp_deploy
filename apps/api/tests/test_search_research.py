"""Tests for Research with Resora, Ask, identifier detection and "why this result" terms. Fake AI router only."""

import asyncio
import json
from types import SimpleNamespace

import pytest

import app.services.ai_router as ai_router
from app.schemas.paper import PaperRecord
from app.services.search.research import ResearchService, ResearchUnavailable, detect_identifier, paper_matches_identifier
from app.services.search.service import matched_query_terms


def _paper(index: int, abstract: str) -> PaperRecord:
    return PaperRecord(
        paper_id=f"p{index}",
        title=f"Paper {index} on hallucination in vision-language models",
        abstract=abstract,
        year=2024,
        venue="CVPR",
        source="research",
    )


PAPERS = [
    _paper(1, "A training-free decoding method raises POPE F1 from 83.9 to 86.9."),
    _paper(2, "Preference optimization on 5.7k human-labelled pairs improves faithfulness."),
    _paper(3, "A benchmark shows hallucination grows with image resolution."),
]


class FakeRouter:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def complete(self, task, prompt, **kwargs):
        self.calls.append({"task": task, "prompt": json.loads(prompt), **kwargs})
        validator = kwargs.get("validator")
        # Like the real router: try outputs until one passes the validator.
        while self.outputs:
            text = self.outputs.pop(0)
            if validator is None or validator(text):
                return SimpleNamespace(text=text, provider="fake")
        raise ai_router.RouterUnavailable("no valid output")


@pytest.fixture
def fake_router(monkeypatch):
    def install(outputs: list[str]) -> FakeRouter:
        router = FakeRouter(outputs)
        monkeypatch.setattr(ai_router, "get_default_router", lambda: router)
        return router

    return install


def test_research_answer_maps_citations_to_papers(fake_router):
    router = fake_router([
        json.dumps({
            "answer": "Decoding changes raise POPE F1 to 86.9 [1], and preference data helps [2].",
            "approaches": [{"label": "Decoding", "refs": [1]}, {"label": "Preference tuning", "refs": [2]}],
            "emerging": [{"text": "Resolution-aware evaluation", "refs": [3]}],
            "conflicting": [],
            "gaps": [{"text": "No study tests video", "refs": [], "evidence": "hypothesis"}],
            "insufficient_evidence": False,
        })
    ])
    result = asyncio.run(ResearchService().answer("How to reduce hallucination?", PAPERS, language="en", user_id="u1"))
    assert result.evidence_ids == ["p1", "p2", "p3"]
    assert result.approaches[1].paper_ids == ["p2"]
    assert result.gaps[0].evidence_level == "hypothesis"
    assert result.credits_used == 5
    assert router.calls[0]["user_content"] is True  # the question is private user text


def test_invented_numbers_and_bad_citations_are_rejected(fake_router):
    fake_router([
        json.dumps({"answer": "F1 reaches 99.1 [1].", "insufficient_evidence": False}),  # number not in evidence
        json.dumps({"answer": "See [7].", "insufficient_evidence": False}),  # citation out of range
        json.dumps({"answer": "Accuracy improves.", "insufficient_evidence": False}),  # no citation
    ])
    with pytest.raises(ResearchUnavailable):
        asyncio.run(ResearchService().answer("q?", PAPERS, language="en", user_id="u1", kind="ask"))


def test_cached_answers_cost_nothing(fake_router):
    output = json.dumps({"answer": "Decoding helps [1].", "insufficient_evidence": False})
    fake_router([output])
    service = ResearchService()
    first = asyncio.run(service.answer("Does decoding help?", PAPERS, language="en", user_id="u1", kind="ask"))
    second = asyncio.run(service.answer("does  decoding help?", PAPERS, language="en", user_id="u1", kind="ask"))
    assert first.credits_used == 1 and second.credits_used == 0


def test_native_digits_are_accepted(fake_router):
    fake_router([json.dumps({"answer": "ڈیکوڈنگ سے F1 ٨٦٫٩ تک پہنچتا ہے [1]۔", "insufficient_evidence": False})])
    result = asyncio.run(ResearchService().answer("سوال", PAPERS, language="ur", user_id="u1", kind="ask"))
    assert result.answer.endswith("[1]۔")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("10.1038/s41586-020-2649-2", ("doi", "10.1038/s41586-020-2649-2")),
        ("https://doi.org/10.1145/3292500.3330701", ("doi", "10.1145/3292500.3330701")),
        ("arXiv:2401.12345v2", ("arxiv", "2401.12345")),
        ("https://arxiv.org/abs/2305.10403", ("arxiv", "2305.10403")),
        ("machine learning", None),
        ("2024 survey", None),
    ],
)
def test_detect_identifier(value, expected):
    assert detect_identifier(value) == expected


def test_paper_matches_identifier():
    paper = PaperRecord(paper_id="x", title="T", doi="10.1038/S41586-020-2649-2", source="research")
    assert paper_matches_identifier(paper, "doi", "10.1038/s41586-020-2649-2")


def test_matched_query_terms_prefers_title():
    paper = PaperRecord(paper_id="x", title="Grounded decoding for hallucination", abstract="Vision-language models", source="research")
    assert matched_query_terms("hallucination in vision-language models", paper)[0] == "hallucination"


def test_only_configured_router_tasks_are_tried(fake_router):
    router = fake_router([json.dumps({"answer": "Decoding helps [1].", "insufficient_evidence": False})])
    router.routes = {"chat": (), "short_translation": ()}  # no "summary" task configured
    asyncio.run(ResearchService().answer("Does decoding help?", PAPERS, language="en", user_id="u1", kind="ask"))
    assert [call["task"] for call in router.calls] == ["chat"]
