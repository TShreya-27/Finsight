"""Cross-statement ratios computed by the ratio agent."""

from pydantic import BaseModel, Field


class FinancialRatios(BaseModel):
    current_ratio: float = Field(..., description="current_assets / current_liabilities")
    debt_to_equity: float = Field(..., description="total_liabilities / equity")
    working_capital: float = Field(..., description="current_assets - current_liabilities")
    health_score: int = Field(..., ge=0, le=100, description="0-100 overall financial health")
