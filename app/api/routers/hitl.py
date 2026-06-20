"""Human-in-the-loop approval endpoints."""

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services.document_store import update_anomaly_status
from app.services.temporal_client import signal_hitl_decision

router = APIRouter()


def status_from_action(action: str) -> str:
    """Map HITL actions to anomaly lifecycle statuses."""
    return {
        "approve": "CORRECT",
        "correct": "CORRECT",
        "reject": "INCORRECT",
        "incorrect": "INCORRECT",
        "modify": "MODIFIED",
    }.get(action.lower(), "PENDING")


class HITLDecisionRequest(BaseModel):
    workflow_id: str = Field(..., description="Temporal workflow ID")
    anomaly_id: str = Field(..., description="Anomaly ID")
    action: str = Field(..., description="correct | incorrect | modify")
    notes: str | None = Field(None, description="Reviewer notes")
    reviewer_slack_id: str | None = Field(None, description="Slack reviewer ID")


class HITLDecisionResponse(BaseModel):
    accepted: bool = Field(..., description="True if the decision was accepted")
    anomaly_id: str = Field(..., description="Anomaly ID")
    workflow_id: str = Field(..., description="Temporal workflow ID")
    status: str = Field(..., description="Updated anomaly status")


@router.post("/respond", response_model=HITLDecisionResponse, status_code=status.HTTP_202_ACCEPTED)
async def respond_to_hitl(payload: HITLDecisionRequest) -> HITLDecisionResponse:
    """Receive Slack interactive payloads and signal the Temporal workflow."""
    await signal_hitl_decision(workflow_id=payload.workflow_id, decision=payload.model_dump())
    status_value = status_from_action(payload.action)
    await update_anomaly_status(payload.anomaly_id, status_value, payload.notes)
    return HITLDecisionResponse(
        accepted=True,
        anomaly_id=payload.anomaly_id,
        workflow_id=payload.workflow_id,
        status=status_value,
    )


@router.post("/{anomaly_id}/override", response_model=HITLDecisionResponse, status_code=status.HTTP_202_ACCEPTED)
async def override_anomaly(anomaly_id: str, payload: HITLDecisionRequest) -> HITLDecisionResponse:
    """Manual evaluator override for approving, rejecting, or modifying an anomaly."""
    decision = payload.model_dump()
    decision["anomaly_id"] = anomaly_id
    await signal_hitl_decision(workflow_id=payload.workflow_id, decision=decision)
    status_value = status_from_action(payload.action)
    await update_anomaly_status(anomaly_id, status_value, payload.notes)
    return HITLDecisionResponse(
        accepted=True,
        anomaly_id=anomaly_id,
        workflow_id=payload.workflow_id,
        status=status_value,
    )
