from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.chat import (
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatPinRequest,
    ChatPinResponse,
)
from app.services.agents.orchestrator import AgentOrchestrator
from app.services.retrieval.chat_engine import GroundedChatEngine
from app.services.retrieval.chat_interactions import ChatInteractionStore

router = APIRouter()
orchestrator = AgentOrchestrator()
chat_engine = GroundedChatEngine()
interaction_store = ChatInteractionStore()


@router.post("/", response_model=ChatMessageResponse)
async def chat(payload: ChatMessageRequest) -> ChatMessageResponse:
    if payload.documents or payload.show_your_work or payload.voice_output or payload.paper_ids:
        question = payload.voice_transcript or payload.question
        grounded = chat_engine.answer(
            question,
            payload.documents,
            payload.language,
            payload.session_id,
            payload.conversation_history,
            payload.show_your_work,
            payload.citation_edges,
        )
        return ChatMessageResponse(
            answer=grounded.answer,
            confidence_score=grounded.confidence_score,
            citations=grounded.citations,
            source_spans=grounded.source_spans,
            inline_citations=grounded.inline_citations,
            highlighted_source_spans=grounded.highlighted_source_spans,
            retrieval_mode=grounded.retrieval_mode,
            chat_scope=grounded.chat_scope,
            condensed_question=grounded.condensed_question,
            follow_up_suggestions=grounded.follow_up_suggestions,
            automatic_literature_suggestions=grounded.automatic_literature_suggestions,
            retrieved_chunks=grounded.retrieved_chunks,
            citation_context_answers=grounded.citation_context_answers,
            citation_sentiment_labels=grounded.citation_sentiment_labels,
            comparison_from_chat=grounded.comparison_from_chat,
            voice_output_text=grounded.voice_output_text if payload.voice_output else None,
            feedback_token=grounded.feedback_token,
            pinned=grounded.pinned,
            starred=grounded.starred,
            export_markdown=grounded.export_markdown,
            shareable_thread_token=grounded.shareable_thread_token,
            traceability_passed=grounded.traceability_passed,
            traceability_coverage=grounded.traceability_coverage,
            traceable_sentences=grounded.traceable_sentences,
            unsupported_sentences=grounded.unsupported_sentences,
            model_used="hybrid-grounded-chat",
            generated_at=grounded.generated_at,
            fallback_reason=grounded.fallback_reason,
            session_turns=grounded.session_turns,
        )

    result = orchestrator.handle(payload.question)
    return ChatMessageResponse(
        answer=result.summary,
        confidence_score=result.confidence_score,
        citations=result.citations,
        source_spans=[],
        inline_citations=[],
        highlighted_source_spans=[],
        retrieval_mode="agent-routing",
        chat_scope="planner",
        condensed_question=payload.question,
        follow_up_suggestions=["Add paper text for fully grounded RAG chat.", "Open workspace-wide chat after selecting papers."],
        automatic_literature_suggestions=["Search fresh papers related to this planner task."],
        citation_sentiment_labels=[],
        comparison_from_chat=None,
        voice_output_text=result.summary if payload.voice_output else None,
        pinned=False,
        starred=False,
        traceability_passed=False,
        traceability_coverage=0.0,
        model_used="planner+specialist",
        generated_at=None,
        fallback_reason=None,
        session_turns=0,
    )


@router.post("/stream")
async def chat_stream(payload: ChatMessageRequest) -> StreamingResponse:
    response = await chat(payload)

    async def token_stream() -> AsyncIterator[str]:
        for token in response.answer.split():
            yield f"{token} "

    return StreamingResponse(token_stream(), media_type="text/plain")


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def log_chat_feedback(payload: ChatFeedbackRequest) -> ChatFeedbackResponse:
    stored = interaction_store.log_feedback(payload.feedback_token, payload.rating, payload.helpful, payload.note, payload.user_id)
    return ChatFeedbackResponse(
        feedback_id=stored["feedback_id"],
        feedback_token=stored["feedback_token"],
        status="stored",
        stored_at=stored["stored_at"],
    )


@router.post("/pin", response_model=ChatPinResponse)
async def pin_chat_answer(payload: ChatPinRequest) -> ChatPinResponse:
    stored = interaction_store.pin_answer(
        payload.feedback_token,
        payload.shareable_thread_token,
        payload.answer,
        payload.starred,
        payload.user_id,
    )
    return ChatPinResponse(
        pin_id=stored["pin_id"],
        feedback_token=stored["feedback_token"],
        shareable_thread_token=stored["shareable_thread_token"],
        pinned=stored["pinned"],
        starred=stored["starred"],
        stored_at=stored["stored_at"],
    )
