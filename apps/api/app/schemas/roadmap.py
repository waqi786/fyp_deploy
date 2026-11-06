from pydantic import BaseModel, Field


class RoadmapPhase(BaseModel):
    order: int
    title: str
    objective: str
    status: str
    dependencies: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    verification_gate: str
    notes: str = ""


class RoadmapResponse(BaseModel):
    project: str
    current_focus: str
    phases: list[RoadmapPhase] = Field(default_factory=list)
    completed_count: int = 0
    in_progress_count: int = 0
    pending_count: int = 0

