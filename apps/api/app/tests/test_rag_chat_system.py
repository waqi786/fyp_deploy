from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def chat_payload() -> dict:
    return {
        "session_id": "rag-chat-test",
        "question": "Compare these papers and explain why p1 cites p2.",
        "show_your_work": True,
        "voice_output": True,
        "documents": [
            {
                "paper_id": "p1",
                "title": "Hybrid Retrieval Paper",
                "content": "Hybrid BM25 and dense retrieval improves grounded chat accuracy. Figure 1 shows gains. def rank(): return 1",
                "figures": [{"figure_id": "fig-1", "caption": "Figure 1: hybrid retrieval gains", "description": "Accuracy rises"}],
                "tables": [{"table_id": "tab-1", "caption": "Table 1: benchmark results", "summary": "Hybrid wins"}],
                "equations": ["score = bm25 + dense"],
            },
            {
                "paper_id": "p2",
                "title": "Dense Retrieval Baseline",
                "content": "Dense retrieval is a semantic baseline for academic chat systems.",
            },
        ],
        "citation_edges": [
            {
                "source_paper_id": "p1",
                "target_paper_id": "p2",
                "context": "supports the dense retrieval baseline comparison",
                "sentiment": "support",
            }
        ],
    }


def test_rag_chat_section_seven_contract() -> None:
    response = client.post("/api/v1/chat/", json=chat_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["chat_scope"] == "workspace-wide multi-paper"
    assert data["retrieval_mode"] == "text+multimodal"
    assert data["confidence_score"] > 0
    assert data["inline_citations"]
    assert data["highlighted_source_spans"]
    assert data["citation_context_answers"]
    assert data["citation_sentiment_labels"][0]["sentiment"] == "support"
    assert data["comparison_from_chat"]
    assert data["voice_output_text"]
    assert data["retrieved_chunks"]
    assert data["automatic_literature_suggestions"]
    assert data["export_markdown"]
    assert data["feedback_token"]
    assert data["shareable_thread_token"]


def test_chat_feedback_and_pin_are_stored() -> None:
    answer = client.post("/api/v1/chat/", json=chat_payload()).json()
    feedback = client.post(
        "/api/v1/chat/feedback",
        json={"feedback_token": answer["feedback_token"], "rating": 5, "helpful": True, "note": "grounded"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "stored"

    pin = client.post(
        "/api/v1/chat/pin",
        json={
            "feedback_token": answer["feedback_token"],
            "shareable_thread_token": answer["shareable_thread_token"],
            "answer": answer["answer"],
            "starred": True,
        },
    )
    assert pin.status_code == 200
    assert pin.json()["pinned"] is True
    assert pin.json()["starred"] is True


def test_chat_stream_returns_answer_tokens() -> None:
    response = client.post("/api/v1/chat/stream", json=chat_payload())
    assert response.status_code == 200
    assert "Hybrid" in response.text or "grounded" in response.text
