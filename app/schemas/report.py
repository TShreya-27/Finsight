"""Final financial report schema assembled by the workflow."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .anomaly import AnomalyRecord
from .balance_sheet import BalanceSheet
from .compliance import ComplianceResult
from .financial_ratios import FinancialRatios
from .pl_statement import PLStatement


class FinancialReport(BaseModel):
    document_id: str = Field(..., description="Source document UUID")
    pl: Optional[PLStatement] = Field(None, description="P&L analysis")
    balance_sheet: Optional[BalanceSheet] = Field(None, description="Balance-sheet analysis")
    ratios: Optional[FinancialRatios] = Field(None, description="Computed ratios")
    anomalies: List[AnomalyRecord] = Field(default_factory=list, description="Detected anomalies")
    compliance: Optional[ComplianceResult] = Field(None, description="Compliance verdict")
    executive_summary: Optional[str] = Field(None, description="CFO summary")
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="UTC timestamp")
