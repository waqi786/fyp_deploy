from fastapi import APIRouter

from app.schemas.evaluation import EvaluationRequest, EvaluationResponse
from app.services.evaluation.benchmark import BaselineEvaluator


router = APIRouter()
service = BaselineEvaluator()


@router.post("/benchmark", response_model=EvaluationResponse)
async def run_benchmark(payload: EvaluationRequest) -> EvaluationResponse:
    return service.evaluate(payload)
