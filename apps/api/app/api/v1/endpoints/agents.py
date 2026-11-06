from fastapi import APIRouter

from app.schemas.agents import MultiAgentWorkflowRequest, MultiAgentWorkflowResponse
from app.services.agents.orchestrator import AgentOrchestrator


router = APIRouter()
service = AgentOrchestrator()


@router.post("/workflow", response_model=MultiAgentWorkflowResponse)
async def run_multi_agent_workflow(payload: MultiAgentWorkflowRequest) -> MultiAgentWorkflowResponse:
    return service.run_workflow(payload)

