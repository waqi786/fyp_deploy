from fastapi import APIRouter

from app.schemas.developer import (
    BrowserExtensionIntakeRequest,
    BrowserExtensionIntakeResponse,
    DeveloperPlatformRequest,
    DeveloperPlatformResponse,
    GraphQLQueryRequest,
    GraphQLQueryResponse,
)
from app.services.developer.platform import DeveloperPlatformService


router = APIRouter()
service = DeveloperPlatformService()


@router.post("/", response_model=DeveloperPlatformResponse)
async def developer_portal(payload: DeveloperPlatformRequest) -> DeveloperPlatformResponse:
    return service.build(payload)


@router.post("/graphql", response_model=GraphQLQueryResponse)
async def graphql_query(payload: GraphQLQueryRequest) -> GraphQLQueryResponse:
    return service.graphql(payload)


@router.post("/extension/intake", response_model=BrowserExtensionIntakeResponse)
async def browser_extension_intake(payload: BrowserExtensionIntakeRequest) -> BrowserExtensionIntakeResponse:
    return service.extension_intake(payload)

