from fastapi import APIRouter

from app.schemas.export import CitationExportRequest, CitationExportResponse
from app.services.exports.citations import CitationExportService


router = APIRouter()
service = CitationExportService()


@router.post("/citations", response_model=CitationExportResponse)
async def export_citations(payload: CitationExportRequest) -> CitationExportResponse:
    return service.export(payload)
