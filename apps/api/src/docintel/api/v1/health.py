from fastapi import APIRouter, Request, Response, status

from docintel.core.config import Settings
from docintel.schemas.health import LivenessResponse, ReadinessResponse
from docintel.services.readiness import run_readiness_checks

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def liveness(request: Request) -> LivenessResponse:
    settings: Settings = request.app.state.settings
    return LivenessResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    report = await run_readiness_checks(
        settings=request.app.state.settings,
        engine=request.app.state.engine,
    )
    if report.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
