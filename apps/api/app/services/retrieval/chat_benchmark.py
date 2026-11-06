"""Benchmark helpers for RAG chat behavior."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chat import ChatDocument
from app.services.retrieval.chat_engine import GroundedChatEngine


@dataclass
class ChatBenchmarkCase:
    question: str
    expected_substrings: list[str]
    documents: list[ChatDocument]


@dataclass
class ChatBenchmarkResult:
    mode: str
    accuracy: float
    hits: int
    total: int


class ChatBenchmarkService:
    """Compares text-only versus multimodal chat grounding on a fixed set of cases."""

    def evaluate(self, cases: list[ChatBenchmarkCase]) -> list[ChatBenchmarkResult]:
        text_only = self._score("text_only", cases, multimodal=False)
        multimodal = self._score("multimodal", cases, multimodal=True)
        return [text_only, multimodal]

    def _score(self, mode: str, cases: list[ChatBenchmarkCase], *, multimodal: bool) -> ChatBenchmarkResult:
        engine = GroundedChatEngine()
        hits = 0
        for case in cases:
            documents = case.documents if multimodal else [self._strip_multimodal(document) for document in case.documents]
            response = engine.answer(case.question, documents, show_your_work=True)
            answer_lower = response.answer.lower()
            if all(expected.lower() in answer_lower for expected in case.expected_substrings):
                hits += 1
        total = len(cases)
        return ChatBenchmarkResult(mode=mode, accuracy=(hits / total if total else 0.0), hits=hits, total=total)

    def _strip_multimodal(self, document: ChatDocument) -> ChatDocument:
        return ChatDocument(
            paper_id=document.paper_id,
            title=document.title,
            content=document.content,
            figures=[],
            tables=[],
            equations=[],
        )
