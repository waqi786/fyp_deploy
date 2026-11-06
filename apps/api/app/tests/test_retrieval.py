from app.schemas.chat import ChatDocument
from app.services.retrieval.chat_engine import GroundedChatEngine
from app.services.retrieval.chunking import make_chunk_id, split_text
from app.services.retrieval.hybrid import HybridRetriever


def test_split_text_preserves_overlap_chunks() -> None:
    text = ("alpha beta gamma delta " * 120).strip()
    chunks = split_text(text, chunk_size=120, overlap=20)
    assert len(chunks) > 1
    assert chunks[0] != chunks[1]


def test_make_chunk_id_is_deterministic() -> None:
    chunk = "retrieval augmented generation for papers"
    assert make_chunk_id("paper-1", chunk) == make_chunk_id("paper-1", chunk)


def test_hybrid_retriever_exposes_single_mode_rankers() -> None:
    retriever = HybridRetriever()
    retriever.index_documents(
        [
            {
                "paper_id": "paper-1",
                "title": "Hybrid Retrieval",
                "content": "Hybrid retrieval combines BM25 and dense retrieval.",
                "figures": [],
                "tables": [],
                "equations": [],
            }
        ]
    )
    assert retriever.retrieve_bm25("BM25 dense", top_k=1)
    assert retriever.retrieve_dense("BM25 dense", top_k=1)


def test_grounded_chat_engine_returns_citations() -> None:
    engine = GroundedChatEngine()
    response = engine.answer(
        "What does the paper say about hybrid retrieval?",
        [
            ChatDocument(
                paper_id="paper-1",
                title="Hybrid Retrieval",
                content="Hybrid retrieval combines BM25 and dense retrieval. The paper reports better grounded answers with fusion.",
            )
        ],
    )
    assert "Hybrid Retrieval" in response.answer
    assert response.citations == ["paper-1"]
    assert response.confidence_score > 0
