"""Financial report endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas.report import FinancialReport
from app.services.postgres_store import fetch_report

router = APIRouter()


class ReportSummaryResponse(BaseModel):
    report_id: str = Field(..., description="Financial report ID")
    executive_summary: str = Field(..., description="Executive summary text")


@router.get("/{report_id}", response_model=FinancialReport)
async def get_report(report_id: str) -> FinancialReport:
    """Return a compiled financial report."""
    payload = await fetch_report(report_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Report not found")
    report_data = payload.get("report_data") or {}
    return FinancialReport.model_validate(report_data)


@router.get("/{report_id}/summary", response_model=ReportSummaryResponse)
async def get_report_summary(report_id: str) -> ReportSummaryResponse:
    """Return only the executive summary for a compiled report."""
    payload = await fetch_report(report_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Report not found")
    executive_summary = payload.get("executive_summary") or ""
    return ReportSummaryResponse(report_id=report_id, executive_summary=executive_summary)
