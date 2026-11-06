from pydantic import BaseModel, Field


class DocumentExtractionRequest(BaseModel):
    source_url: str | None = None
    raw_text: str | None = None
    raw_bytes_base64: str | None = None
    title: str | None = None


class ExtractedFigure(BaseModel):
    figure_id: str
    caption: str
    chart_type: str
    description: str
    data_insights: list[str] = Field(default_factory=list)
    alt_text: str = ""
    numeric_points: list[float] = Field(default_factory=list)
    diagram_type: str = "figure"
    cross_references: list[str] = Field(default_factory=list)
    suspicious_design_flags: list[str] = Field(default_factory=list)
    library_index_terms: list[str] = Field(default_factory=list)


class ExtractedTable(BaseModel):
    table_id: str
    caption: str
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    csv_export: str = ""


class EquationExplanation(BaseModel):
    raw: str
    latex: str
    explanation: str
    derivation_steps: list[str] = Field(default_factory=list)
    interactive_variables: list[dict[str, str]] = Field(default_factory=list)


class DocumentExtractionResponse(BaseModel):
    status: str
    extracted_text: str
    extraction_method: str
    scanned_pdf_detected: bool = False
    ocr_confidence: float | None = None
    normalized_source_url: str | None = None
    blocked_reason: str | None = None
    detected_equations: list[str] = Field(default_factory=list)
    equation_explanations: list[EquationExplanation] = Field(default_factory=list)
    figures: list[ExtractedFigure] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    image_search_index: list[str] = Field(default_factory=list)
    processing_notes: list[str] = Field(default_factory=list)
    table_csv_exports: dict[str, str] = Field(default_factory=dict)
    figure_caption_cross_references: dict[str, list[str]] = Field(default_factory=dict)
    suspicious_chart_design_flags: list[str] = Field(default_factory=list)
    layout_reconstruction: dict[str, str | int | bool] = Field(default_factory=dict)
    handwritten_annotations: list[str] = Field(default_factory=list)
    table_of_contents: list[dict[str, str | int]] = Field(default_factory=list)
    supplementary_material_links: list[str] = Field(default_factory=list)
    accessibility_alt_text: dict[str, str] = Field(default_factory=dict)
    dependency_diagnostics: dict[str, str | bool] = Field(default_factory=dict)
    manual_verification_required: bool = False
    editable_extracted_text: str = ""
    extraction_quality_flags: list[str] = Field(default_factory=list)


class FigureImageAnalysisResponse(BaseModel):
    filename: str
    content_type: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    perceptual_hash: str
    dominant_tone: str
    diagram_type: str
    search_caption: str
    alt_text: str
    confidence_score: float


class FigureQuestionRequest(BaseModel):
    question: str
    figures: list[ExtractedFigure] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    equations: list[EquationExplanation] = Field(default_factory=list)


class FigureQuestionResponse(BaseModel):
    answer: str
    confidence_score: float
    cited_visual_ids: list[str] = Field(default_factory=list)
    source_spans: list[str] = Field(default_factory=list)


class FigureComparisonRequest(BaseModel):
    figures: list[ExtractedFigure] = Field(default_factory=list)


class FigureComparisonResponse(BaseModel):
    comparison_matrix: list[dict[str, str | int | float | list[str]]] = Field(default_factory=list)
    summary: str
    suspicious_flags: list[str] = Field(default_factory=list)


class LibraryImageSearchRequest(BaseModel):
    query: str
    figures: list[ExtractedFigure] = Field(default_factory=list)


class LibraryImageSearchResponse(BaseModel):
    matches: list[dict[str, str | float | list[str]]] = Field(default_factory=list)
    query: str
