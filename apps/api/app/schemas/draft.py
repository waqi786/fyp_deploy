from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import ExtractedFigure


class DraftGenerationRequest(BaseModel):
    title: str
    extracted_text: str
    figures: list[ExtractedFigure] = Field(default_factory=list)
    target_style: str = "ieee"
    language: str = "en"


class DraftGenerationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    sections: dict[str, str]
    self_critique: dict[str, list[str]]
    figure_analysis_count: int
    confidence_score: float
    source_spans: list[str] = Field(default_factory=list)
    model_used: str
    generated_at: str
