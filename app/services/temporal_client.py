"""Temporal client helpers used by the FastAPI layer."""

from __future__ import annotations

import base64

from temporalio.client import Client

from app.core.settings import settings
from temporal_app.workflows import FullAnalysisSaga


async def get_temporal_client() -> Client:
    """Create a Temporal client."""
    return await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)


async def start_full_analysis_saga(*, document_id: str, filename: str, content_type: str, file_bytes: bytes) -> str:
    """Start the full analysis saga, or return an ID when Temporal is disabled."""
    workflow_id = f"finsight-{document_id}"
    if not settings.TEMPORAL_ENABLED:
        return workflow_id

    client = await get_temporal_client()
    payload = {
        "document_id": document_id,
        "filename": filename,
        "content_type": content_type,
        "file_bytes_b64": base64.b64encode(file_bytes).decode("ascii"),
    }
    await client.start_workflow(
        FullAnalysisSaga.run,
        payload,
        id=workflow_id,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    return workflow_id


async def signal_hitl_decision(*, workflow_id: str, decision: dict) -> None:
    """Signal a running Temporal workflow with a HITL decision."""
    if not settings.TEMPORAL_ENABLED:
        return

    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(FullAnalysisSaga.submit_hitl_decision, decision)
