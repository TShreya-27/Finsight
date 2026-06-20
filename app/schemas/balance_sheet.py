"""Balance-sheet schema with accounting identity validation."""

from datetime import date

from pydantic import BaseModel, Field, model_validator


class BalanceSheet(BaseModel):
    total_assets: float = Field(..., description="Total assets")
    current_assets: float = Field(..., description="Current assets")
    non_current_assets: float = Field(..., description="Non-current assets")
    total_liabilities: float = Field(..., description="Total liabilities")
    current_liabilities: float = Field(..., description="Current liabilities")
    non_current_liabilities: float = Field(..., description="Non-current liabilities")
    equity: float = Field(..., description="Equity")
    period_date: date | None = Field(None, description="Balance-sheet date")
    currency: str = Field("INR", description="Currency code")

    @model_validator(mode="after")
    def reconcile_assets(self) -> "BalanceSheet":
        rhs = self.total_liabilities + self.equity
        diff_pct = abs(self.total_assets - rhs) / max(abs(self.total_assets), 1) * 100
        if diff_pct > 0.01:
            raise ValueError(f"Assets != liabilities + equity (diff={diff_pct:.4f}%)")
        return self
