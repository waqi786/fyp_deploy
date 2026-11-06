from app.schemas.paper import PaperRecord
from app.services.graph.knowledge import KnowledgeGraphService
from app.services.models.adapters import build_llm_adapter
from app.services.retrieval.vector_store import FaissLiteStore
from app.services.storage.object_storage import ObjectStorageService
from app.services.storage.session_cache import SessionCache


def make_paper() -> PaperRecord:
    return PaperRecord(
        paper_id="paper-arch",
        title="RAG Benchmark with Transformer Method",
        abstract="This paper introduces a benchmark dataset for retrieval evaluation using transformer methods.",
        year=2025,
        venue="AI Systems",
        url="https://example.org",
        citation_count=14,
        is_open_access=True,
        authors=[{"name": "Alice Author"}],
        source="openalex",
    )


def test_llm_adapter_registry_defaults_to_known_provider() -> None:
    adapter = build_llm_adapter("groq")
    response = adapter.complete("Summarize this")
    assert response.provider == "groq"
    assert response.text


def test_faiss_lite_store_returns_ranked_hits() -> None:
    store = FaissLiteStore()
    store.add("c1", "hybrid retrieval benchmark")
    store.add("c2", "protein folding methods")
    hits = store.search("hybrid retrieval", top_k=2)
    assert hits
    assert hits[0].chunk_id == "c1"


def test_knowledge_graph_links_papers_authors_and_concepts() -> None:
    graph = KnowledgeGraphService().build([make_paper()])
    node_ids = {node["node_id"] for node in graph["nodes"]}
    relations = {edge["relation"] for edge in graph["edges"]}
    assert "paper:paper-arch" in node_ids
    assert any(node_id.startswith("author:") for node_id in node_ids)
    assert "written_by" in relations


def test_session_cache_respects_set_and_get() -> None:
    cache = SessionCache(ttl_seconds=60)
    cache.set("session-1", {"message": "hello"})
    assert cache.get("session-1") == {"message": "hello"}


def test_object_storage_round_trip() -> None:
    storage = ObjectStorageService()
    path = storage.put_bytes("figure-1.png", b"abc", content_type="image/png")
    assert path.endswith("/figure-1.png")
    assert storage.get_bytes("figure-1.png") == b"abc"
