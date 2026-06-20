"""Audit trail schema used for immutable logging."""

from typing import Optional

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    workflow_run_id: str = Field(..., description="Temporal workflow run ID")
    agent_name: str = Field(..., description="Agent name")
    action: str = Field(..., description="Action description")
    input_hash: str = Field(..., description="Input SHA-256 hash")
    output_hash: str = Field(..., description="Output SHA-256 hash")
    eval_score: Optional[float] = Field(None, description="Eval score if any")
    duration_ms: int = Field(..., description="Duration in milliseconds")
