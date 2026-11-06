from fastapi import APIRouter

from app.schemas.collaboration import CollaborationRequest, CollaborationResponse
from app.services.workspace.collaboration import CollaborationService

router = APIRouter()
service = CollaborationService()


@router.post("/workspace", response_model=CollaborationResponse)
async def workspace_collaboration(payload: CollaborationRequest) -> CollaborationResponse:
    return service.summarize(payload)
