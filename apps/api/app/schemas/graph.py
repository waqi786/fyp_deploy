from pydantic import BaseModel, Field


class CitationNode(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    citation_count: int = 0


class CitationEdge(BaseModel):
    source: str
    target: str
    sentiment: str = "mention"


class CitationGraphRequest(BaseModel):
    roots: list[str] = Field(default_factory=list)
    nodes: list[CitationNode]
    edges: list[CitationEdge]


class CitationGraphResponse(BaseModel):
    influence_scores: dict[str, float]
    pagerank_scores: dict[str, float]
    citation_velocity: dict[str, float]
    bridge_nodes: list[str]
