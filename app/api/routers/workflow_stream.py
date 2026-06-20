"""Workflow status WebSocket endpoint."""

from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws/workflow/{workflow_id}")
async def workflow_status_stream(websocket: WebSocket, workflow_id: str) -> None:
    """Stream workflow status updates to the browser."""
    await websocket.accept()
    await websocket.send_json(
        {
            "workflow_id": workflow_id,
            "status": "CONNECTED",
            "stage": "WAITING_FOR_TEMPORAL",
            "agent": None,
        }
    )
    await websocket.close()
