from fastapi import APIRouter, File, UploadFile

from app.schemas.document import (
    DocumentExtractionRequest,
    DocumentExtractionResponse,
    FigureComparisonRequest,
    FigureComparisonResponse,
    FigureImageAnalysisResponse,
    FigureQuestionRequest,
    FigureQuestionResponse,
    LibraryImageSearchRequest,
    LibraryImageSearchResponse,
)
from app.services.documents.image_analysis import FigureImageAnalysisService
from app.services.documents.multimodal_workbench import MultimodalWorkbenchService
from app.services.documents.pdf_extraction import DocumentExtractionService


router = APIRouter()
service = DocumentExtractionService()
image_service = FigureImageAnalysisService()
workbench_service = MultimodalWorkbenchService()


@router.post("/extract", response_model=DocumentExtractionResponse)
async def extract_document(payload: DocumentExtractionRequest) -> DocumentExtractionResponse:
    return await service.extract(payload.source_url, payload.raw_text, payload.raw_bytes_base64)


@router.post("/figure-query", response_model=FigureImageAnalysisResponse)
async def analyze_figure_query(file: UploadFile = File(...)) -> FigureImageAnalysisResponse:
    data = await file.read()
    return image_service.analyze(
        filename=file.filename or "uploaded-figure",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )


@router.post("/visual-qa", response_model=FigureQuestionResponse)
async def answer_visual_question(payload: FigureQuestionRequest) -> FigureQuestionResponse:
    return workbench_service.answer_visual_question(payload)


@router.post("/figures/compare", response_model=FigureComparisonResponse)
async def compare_figures(payload: FigureComparisonRequest) -> FigureComparisonResponse:
    return workbench_service.compare_figures(payload)


@router.post("/images/search", response_model=LibraryImageSearchResponse)
async def search_library_images(payload: LibraryImageSearchRequest) -> LibraryImageSearchResponse:
    return workbench_service.search_library_images(payload)
