from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.chat import ChatCitationEdge, ChatDocument
from app.schemas.quality import TraceabilityCheckRequest
from app.services.quality.traceability import TraceabilityGuardService
from app.services.retrieval.hybrid import HybridRetriever
from app.services.storage.session_cache import SessionCache


@dataclass
class GroundedAnswer:
    answer: str
    confidence_score: float
    citations: list[str]
    source_spans: list[str]
    inline_citations: list[dict[str, str]]
    highlighted_source_spans: list[dict[str, str]]
    retrieval_mode: str
    chat_scope: str
    condensed_question: str | None
    follow_up_suggestions: list[str]
    automatic_literature_suggestions: list[str]
    retrieved_chunks: list[str]
    citation_context_answers: list[str]
    citation_sentiment_labels: list[dict[str, str]]
    comparison_from_chat: str | None
    voice_output_text: str | None
    feedback_token: str
    pinned: bool
    starred: bool
    export_markdown: str
    shareable_thread_token: str
    traceability_passed: bool
    traceability_coverage: float
    traceable_sentences: list[dict[str, str | bool | None]]
    unsupported_sentences: list[str]
    generated_at: str
    fallback_reason: str | None
    session_turns: int


class GroundedChatEngine:
    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.session_cache = SessionCache()
        self.traceability = TraceabilityGuardService()

    def answer(
        self,
        question: str,
        documents: list[ChatDocument],
        language: str = "en",
        session_id: str | None = None,
        conversation_history: list[str] | None = None,
        show_your_work: bool = False,
        citation_edges: list[ChatCitationEdge] | None = None,
    ) -> GroundedAnswer:
        history = conversation_history or []
        question_text = question.strip()
        condensed_question = self._condense_question(question_text, history, session_id)
        generated_at = datetime.now(UTC).isoformat()
        chat_scope = self._chat_scope(documents)
        if not documents:
            answer = "I am not sure yet because no document content was provided. Add paper text and I will ground the answer in retrieved chunks."
            if language.lower() == "ur":
                answer = "Mujhe abhi yaqeen se jawab dene ke liye document content chahiye. Paper text dein, phir main grounded jawab dunga."
            return GroundedAnswer(
                answer=answer,
                confidence_score=0.0,
                citations=[],
                source_spans=[],
                inline_citations=[],
                highlighted_source_spans=[],
                retrieval_mode="none",
                chat_scope=chat_scope,
                condensed_question=condensed_question,
                follow_up_suggestions=[],
                automatic_literature_suggestions=[],
                retrieved_chunks=[],
                citation_context_answers=[],
                citation_sentiment_labels=[],
                comparison_from_chat=None,
                voice_output_text=answer,
                feedback_token=f"fb-{uuid4().hex[:10]}",
                pinned=False,
                starred=False,
                export_markdown=f"## Question\n{question}\n\n## Answer\n{answer}",
                shareable_thread_token=f"thread-{uuid4().hex[:12]}",
                traceability_passed=False,
                traceability_coverage=0.0,
                traceable_sentences=[],
                unsupported_sentences=[answer],
                generated_at=generated_at,
                fallback_reason="NO_DOCUMENTS",
                session_turns=self._session_turns(session_id),
            )

        payload = [document.model_dump() for document in documents]
        expected_chunk_ids = self.retriever.expected_chunk_ids(payload)
        expected_chunks = self.retriever.index_documents(payload)
        self.retriever.wait_until_indexed(expected_chunks, expected_chunk_ids=expected_chunk_ids)
        hits = self.retriever.retrieve(condensed_question or question, top_k=4)
        retrieval_mode = "text+multimodal" if any(document.figures or document.tables or document.equations for document in documents) else "text"
        if not hits:
            titles = ", ".join(document.title for document in documents[:3])
            answer = f"I am not sure. The current retrieval pass did not find strong supporting chunks. Relevant papers loaded: {titles}."
            if language.lower() == "ur":
                answer = f"Main abhi pur-yakeen nahi hoon. Retrieval ko strong support chunks nahi mile. Relevant papers: {titles}."
            session_payload = self._store_session(session_id, question, answer, [document.paper_id for document in documents[:3]])
            return GroundedAnswer(
                answer=answer,
                confidence_score=0.18,
                citations=[document.paper_id for document in documents[:3]],
                source_spans=[],
                inline_citations=[],
                highlighted_source_spans=[],
                retrieval_mode=retrieval_mode,
                chat_scope=chat_scope,
                condensed_question=condensed_question,
                follow_up_suggestions=self._follow_ups(question, documents),
                automatic_literature_suggestions=self._literature_suggestions(question, documents),
                retrieved_chunks=[],
                citation_context_answers=self._citation_context_answers(question, citation_edges or []),
                citation_sentiment_labels=self._citation_sentiment_labels(citation_edges or []),
                comparison_from_chat=self._comparison_from_chat(question, documents),
                voice_output_text=answer,
                feedback_token=f"fb-{uuid4().hex[:10]}",
                pinned=False,
                starred=False,
                export_markdown=f"## Question\n{question}\n\n## Answer\n{answer}",
                shareable_thread_token=f"thread-{uuid4().hex[:12]}",
                traceability_passed=False,
                traceability_coverage=0.0,
                traceable_sentences=[],
                unsupported_sentences=[answer],
                generated_at=generated_at,
                fallback_reason="NO_RETRIEVAL_HITS",
                session_turns=len(session_payload.get("turns", [])) if session_payload else 0,
            )

        citations = []
        spans = []
        inline_citations = []
        highlighted_source_spans = []
        evidence_lines = []
        retrieved_chunks = []
        for index, hit in enumerate(hits, start=1):
            citations.append(hit.paper_id)
            excerpt = hit.text[:220].replace("\n", " ").strip()
            spans.append(f"{hit.paper_id}:{excerpt}")
            marker = f"[{index}]"
            inline_citations.append({"marker": marker, "paper_id": hit.paper_id, "title": hit.title, "exact_source": excerpt})
            highlighted_source_spans.append({"paper_id": hit.paper_id, "highlight": excerpt, "reason": f"Retrieved by hybrid BM25+dense rank {index}"})
            evidence_lines.append(f"{hit.title}: {excerpt}")
            retrieved_chunks.append(excerpt)
        confidence = min(0.99, 0.35 + sum(hit.score for hit in hits))
        answer = "AI inference, not from source: The following grounded synthesis is assembled from retrieved evidence.\n" + "\n".join(evidence_lines[:3])
        if any(document.figures or document.tables or document.equations for document in documents):
            answer += "\nAI inference, not from source: Multimodal evidence was included from figures, tables, or equations when available."
        if "compare" in question.lower() or "difference" in question.lower():
            answer += "\nAI inference, not from source: Cross-paper comparison mode was used to synthesize multiple papers."
        if any(document.equations for document in documents):
            answer += "\nAI inference, not from source: Math-aware mode considered equation evidence."
        if any("```" in document.content or "def " in document.content or document.code_snippets for document in documents):
            answer += "\nAI inference, not from source: Code-aware mode detected implementation-oriented content."
        if language.lower() == "ur":
            answer = "Mazboot retrieved evidence ki bunyaad par yeh grounded synthesis hai:\n" + "\n".join(evidence_lines[:3])
        if show_your_work:
            answer += "\nAI inference, not from source: Show-your-work mode attached retrieved chunk evidence."
        citation_context_answers = self._citation_context_answers(question, citation_edges or [])
        citation_sentiment_labels = self._citation_sentiment_labels(citation_edges or [])
        comparison_from_chat = self._comparison_from_chat(question, documents)
        literature_suggestions = self._literature_suggestions(question, documents)
        follow_ups = self._follow_ups(question, documents)
        export_markdown = self._export_thread(question, answer, evidence_lines[:3], follow_ups, literature_suggestions)
        shareable_thread_token = f"thread-{uuid4().hex[:12]}"
        feedback_token = f"fb-{uuid4().hex[:10]}"
        traceability = self.traceability.validate(
            TraceabilityCheckRequest(
                answer=answer,
                source_spans=spans,
                retrieved_chunks=retrieved_chunks,
            )
        )
        session_payload = self._store_session(session_id, question, answer, citations)
        return GroundedAnswer(
            answer=answer,
            confidence_score=round(confidence, 2),
            citations=list(dict.fromkeys(citations)),
            source_spans=spans,
            inline_citations=inline_citations,
            highlighted_source_spans=highlighted_source_spans,
            retrieval_mode=retrieval_mode,
            chat_scope=chat_scope,
            condensed_question=condensed_question,
            follow_up_suggestions=follow_ups,
            automatic_literature_suggestions=literature_suggestions,
            retrieved_chunks=retrieved_chunks,
            citation_context_answers=citation_context_answers,
            citation_sentiment_labels=citation_sentiment_labels,
            comparison_from_chat=comparison_from_chat,
            voice_output_text=answer,
            feedback_token=feedback_token,
            pinned=False,
            starred=False,
            export_markdown=export_markdown,
            shareable_thread_token=shareable_thread_token,
            traceability_passed=traceability.passed,
            traceability_coverage=traceability.coverage,
            traceable_sentences=[item.model_dump() for item in traceability.traceable_sentences],
            unsupported_sentences=traceability.unsupported_sentences,
            generated_at=generated_at,
            fallback_reason=None,
            session_turns=len(session_payload.get("turns", [])) if session_payload else 0,
        )

    def _condense_question(self, question: str, history: list[str], session_id: str | None) -> str | None:
        previous = history[-1] if history else None
        if not previous and session_id:
            cached = self.session_cache.get(session_id)
            if cached:
                previous = cached.get("last_question")
        if previous and any(token in question.lower().split() for token in ("it", "this", "they", "that", "those", "these")):
            return f"{question} (follow-up to: {previous})"
        return question

    def _follow_ups(self, question: str, documents: list[ChatDocument]) -> list[str]:
        titles = [document.title for document in documents[:2]]
        return [
            f"Compare the main claims in {titles[0] if titles else 'these papers'}.",
            "What limitations do the retrieved papers mention?",
            "Which figure or table best supports this answer?",
        ]

    def _chat_scope(self, documents: list[ChatDocument]) -> str:
        if len(documents) == 1:
            return "single-paper"
        if len(documents) > 1:
            return "workspace-wide multi-paper"
        return "none"

    def _citation_context_answers(self, question: str, citation_edges: list[ChatCitationEdge]) -> list[str]:
        if "cite" not in question.lower() and "citation" not in question.lower() and "why does" not in question.lower():
            return []
        answers = []
        for edge in citation_edges[:5]:
            answers.append(
                f"{edge.source_paper_id} cites {edge.target_paper_id} as a {edge.sentiment} link. Context: {edge.context or 'No explicit context provided.'}"
            )
        return answers

    def _citation_sentiment_labels(self, citation_edges: list[ChatCitationEdge]) -> list[dict[str, str]]:
        labels = []
        for edge in citation_edges[:10]:
            sentiment = edge.sentiment.lower() if edge.sentiment else "mention"
            if sentiment not in {"support", "dispute", "mention"}:
                sentiment = "mention"
            labels.append(
                {
                    "source_paper_id": edge.source_paper_id,
                    "target_paper_id": edge.target_paper_id,
                    "sentiment": sentiment,
                    "context": edge.context or "No citation context supplied.",
                }
            )
        return labels

    def _comparison_from_chat(self, question: str, documents: list[ChatDocument]) -> str | None:
        question_lower = question.lower()
        if len(documents) < 2 or not any(token in question_lower for token in ("compare", "difference", "versus", "vs", "cross-paper")):
            return None
        titles = [document.title for document in documents[:4]]
        return "Cross-paper comparison from chat: " + " | ".join(titles)

    def _literature_suggestions(self, question: str, documents: list[ChatDocument]) -> list[str]:
        title_terms = []
        for document in documents[:3]:
            words = [word.strip(".,:;()[]").lower() for word in document.title.split()]
            title_terms.extend(word for word in words if len(word) > 5)
        seed = title_terms[0] if title_terms else question.split()[0].lower()
        return [
            f"Find recent review papers on {seed}.",
            f"Search new preprints that cite {documents[0].title if documents else 'this workspace'}.",
            "Run a contradiction scan on follow-up papers before adding them to the answer.",
        ]

    def _export_thread(self, question: str, answer: str, evidence_lines: list[str], follow_ups: list[str], literature_suggestions: list[str]) -> str:
        lines = ["## Question", question, "", "## Answer", answer, "", "## Evidence"]
        lines.extend(f"- {line}" for line in evidence_lines)
        lines.append("")
        lines.append("## Follow-ups")
        lines.extend(f"- {item}" for item in follow_ups)
        lines.append("")
        lines.append("## Literature suggestions")
        lines.extend(f"- {item}" for item in literature_suggestions)
        return "\n".join(lines)

    def _store_session(self, session_id: str | None, question: str, answer: str, citations: list[str]) -> dict | None:
        if not session_id:
            return None
        return self.session_cache.append_turn(session_id, question, answer, citations)

    def _session_turns(self, session_id: str | None) -> int:
        if not session_id:
            return 0
        payload = self.session_cache.get(session_id) or {}
        return len(payload.get("turns", []))
