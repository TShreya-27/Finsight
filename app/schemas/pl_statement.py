"""P&L schema with simple reconciliation validation."""

from datetime import date

from pydantic import BaseModel, Field, model_validator


class PLStatement(BaseModel):
    revenue: float = Field(..., description="Revenue from operations")
    cogs: float = Field(..., description="Cost of goods sold")
    gross_profit: float = Field(..., description="Revenue minus COGS")
    operating_expenses: float = Field(..., description="Operating expenses")
    ebitda: float = Field(..., description="EBITDA")
    net_income: float = Field(..., description="Net income")
    gross_margin_pct: float = Field(..., description="Gross margin percentage")
    ebitda_margin_pct: float = Field(..., description="EBITDA margin percentage")
    period_start: date | None = Field(None, description="Period start")
    period_end: date | None = Field(None, description="Period end")
    currency: str = Field("INR", description="Currency code")

    @model_validator(mode="after")
    def reconcile_gross_profit(self) -> "PLStatement":
        expected = self.revenue - self.cogs
        if abs(self.gross_profit - expected) > 0.01:
            raise ValueError(f"gross_profit ({self.gross_profit}) != revenue - cogs ({expected})")
        return self
