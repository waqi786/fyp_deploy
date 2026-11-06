from fastapi import APIRouter

from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceDetail,
    WorkspaceSummary,
)
from app.services.workspace.rbac import WorkspaceService

router = APIRouter()
service = WorkspaceService()


@router.get("/", response_model=list[WorkspaceSummary])
async def list_workspaces() -> list[WorkspaceSummary]:
    return service.list_workspaces()


@router.post("/", response_model=WorkspaceDetail)
async def create_workspace(payload: WorkspaceCreateRequest) -> WorkspaceDetail:
    return service.create_workspace(payload)


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
async def get_workspace(workspace_id: str) -> WorkspaceDetail:
    return service.get_workspace(workspace_id)
