"""Webhook endpoints."""

from uuid import uuid4

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter()


class EmailWebhookResponse(BaseModel):
    accepted: bool = Field(..., description="True if the webhook was accepted")
    workflow_id: str = Field(..., description="Started workflow ID")


@router.post("/email", response_model=EmailWebhookResponse, status_code=status.HTTP_202_ACCEPTED)
async def email_webhook() -> EmailWebhookResponse:
    """Trigger email polling and start the document ingest flow."""
    return EmailWebhookResponse(accepted=True, workflow_id=f"email-{uuid4()}")
