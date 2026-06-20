"""Anomaly records and anomaly reports."""

from typing import Dict, List

from pydantic import BaseModel, Field

from .common import AnomalySeverity


class AnomalyRecord(BaseModel):
    metric_name: str = Field(..., description="Metric name")
    actual_value: float = Field(..., description="Actual value")
    expected_range: Dict[str, float] = Field(..., description="Expected min/max range")
    deviation_pct: float = Field(..., description="Deviation percentage")
    severity: AnomalySeverity = Field(..., description="Severity level")
    description: str = Field(..., description="CFO-readable explanation")


class AnomalyReport(BaseModel):
    document_id: str = Field(..., description="Document UUID")
    anomalies: List[AnomalyRecord] = Field(default_factory=list, description="All anomalies")
    max_severity: AnomalySeverity = Field(AnomalySeverity.LOW, description="Highest severity found")
    clean_pass: bool = Field(..., description="True when no anomalies are found")
