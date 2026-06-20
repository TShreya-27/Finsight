"""Health-check endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall service status")
    db: str = Field(..., description="PostgreSQL connectivity status")
    redis: str = Field(..., description="Redis connectivity status")
    temporal: str = Field(..., description="Temporal connectivity status")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return service health for API, DB, Redis, and Temporal."""
    return HealthResponse(status="ok", db="not_checked", redis="not_checked", temporal="not_checked")
