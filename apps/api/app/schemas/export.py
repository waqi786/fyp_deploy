from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord


class CitationExportRequest(BaseModel):
    papers: list[PaperRecord] = Field(min_length=1, max_length=100)
    format: str = Field(pattern="^(bibtex|ris|csljson)$")


class CitationExportResponse(BaseModel):
    format: str
    content: str
    item_count: int
