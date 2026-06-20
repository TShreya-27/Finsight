"""Compliance-check output schema."""

from typing import List

from pydantic import BaseModel, Field


class ComplianceResult(BaseModel):
    passed: bool = Field(..., description="True if all checks passed")
    critical_failure: bool = Field(False, description="True if a critical violation exists")
    violations: List[str] = Field(default_factory=list, description="Violation descriptions")
    negative_revenue: bool = Field(False, description="True if revenue is negative")
    period_inconsistent: bool = Field(False, description="True if dates are inconsistent")
