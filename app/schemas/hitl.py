"""Human-in-the-loop decision schema."""

from typing import Optional

from pydantic import BaseModel, Field


class HITLDecision(BaseModel):
    action: str = Field(..., description="approve | reject | modify")
    anomaly_id: str = Field(..., description="Anomaly UUID")
    notes: Optional[str] = Field(None, description="Reviewer notes")
    all_resolved: bool = Field(..., description="True if all anomalies are resolved")
    next_action: str = Field(..., description="proceed | retry | escalate")
