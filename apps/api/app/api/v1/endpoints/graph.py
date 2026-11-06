from fastapi import APIRouter

from app.schemas.graph import CitationGraphRequest, CitationGraphResponse
from app.services.graph.metrics import CitationGraphService


router = APIRouter()
service = CitationGraphService()


@router.post("/analyze", response_model=CitationGraphResponse)
async def analyze_graph(payload: CitationGraphRequest) -> CitationGraphResponse:
    return service.analyze(payload)
