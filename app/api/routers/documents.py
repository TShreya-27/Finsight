import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.routers.auth import get_current_user
from app.services.document_store import StoredDocument, get_document, save_document
from app.services.pdf_analyzer import _sync_fast_prescan, _sync_generate_highlighted_pdf
from app.services.postgres_store import fetch_document_file, list_document_meta_for_user, upsert_document_file
from app.services.temporal_client import start_full_analysis_saga

router = APIRouter()


class DocumentUploadResponse(BaseModel):
    workflow_id: str = Field(..., description="Temporal workflow ID")
    document_id: str = Field(..., description="Financial document ID")
    status: str = Field(..., description="Initial processing status")
    anomaly_count: int = Field(..., description="Number of flagged anomaly lines")
    highlighted_pdf_url: str = Field(..., description="URL for the highlighted HITL PDF")


class DocumentStatusResponse(BaseModel):
    document_id: str = Field(..., description="Financial document ID")
    status: str = Field(..., description="Current document processing status")
    workflow_id: str | None = Field(None, description="Temporal workflow ID")
    workflow_state: str = Field(..., description="Current workflow state")
    anomaly_count: int = Field(0, description="Number of flagged anomaly lines")
    highlighted_pdf_url: str | None = Field(None, description="URL for the highlighted HITL PDF")


class DocumentListItem(BaseModel):
    document_id: str = Field(..., description="Financial document ID")
    filename: str = Field(..., description="Uploaded filename")
    status: str = Field(..., description="Current document processing status")
    workflow_id: str | None = Field(None, description="Temporal workflow ID")
    anomaly_count: int = Field(0, description="Number of flagged anomaly lines")
    source_pdf_url: str = Field(..., description="URL for the original uploaded PDF")
    highlighted_pdf_url: str | None = Field(None, description="URL for the highlighted HITL PDF")
    updated_at: str = Field(..., description="Last update timestamp")


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem] = Field(default_factory=list)


class AnomalyItem(BaseModel):
    anomaly_id: str = Field(..., description="Anomaly ID")
    metric_name: str = Field(..., description="Metric name")
    line_text: str = Field(..., description="Exact PDF text span or table row that was flagged")
    actual_value: float | None = Field(None, description="Actual metric value")
    expected_range: dict[str, float] = Field(default_factory=dict, description="Expected min/max range")
    severity: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    status: str = Field(..., description="PENDING | CORRECT | INCORRECT | MODIFIED")
    description: str | None = Field(None, description="Human-readable anomaly description")
    page: int = Field(..., description="One-based PDF page number")
    bbox: list[float] = Field(default_factory=list, description="Exact PDF-space bbox [x1, y1, x2, y2]")
    score: float = Field(..., description="Anomaly score from 0.0 to 1.0")
    reason: str = Field(..., description="Plain-language reason the line was flagged")
    reviewer_comment: str | None = Field(None, description="Reviewer notes saved as feedback")


class DocumentAnomaliesResponse(BaseModel):
    document_id: str = Field(..., description="Financial document ID")
    anomalies: list[AnomalyItem] = Field(default_factory=list, description="Anomalies for this document")


@router.get("", response_model=DocumentListResponse)
async def list_documents(user: dict = Depends(get_current_user)) -> DocumentListResponse:
    """List documents previously uploaded by the current user."""
    documents = await list_document_meta_for_user(user.get("id", ""))
    return DocumentListResponse(
        documents=[
            DocumentListItem(
                document_id=document["document_id"],
                filename=document.get("filename") or "uploaded.pdf",
                status=document.get("status") or "PENDING",
                workflow_id=document.get("workflow_id"),
                anomaly_count=len(document.get("anomalies", []) or []),
                source_pdf_url=f"/api/v1/documents/{document['document_id']}/source-pdf",
                highlighted_pdf_url=(
                    f"/api/v1/documents/{document['document_id']}/highlighted-pdf"
                    if document.get("highlighted_storage_path")
                    else None
                ),
                updated_at=document["updated_at"].isoformat() if document.get("updated_at") else "",
            )
            for document in documents
        ]
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Accept a PDF upload and start the document-processing workflow."""
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Only PDF uploads are supported")

    document_id = str(uuid4())
    file_bytes = await file.read()
    try:
        source_path, anomalies = await asyncio.to_thread(
            _sync_fast_prescan,
            document_id=document_id,
            filename=file.filename or "uploaded.pdf",
            file_bytes=file_bytes,
        )
        highlighted_path = None
        if anomalies:
            highlighted_path = await asyncio.to_thread(
                _sync_generate_highlighted_pdf,
                document_id=document_id,
                source_pdf_path=source_path,
                anomalies=anomalies,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = file.filename or "uploaded.pdf"
    source_storage_path = await upsert_document_file(
        document_id=document_id,
        file_kind="source",
        filename=filename,
        content_type=file.content_type or "application/pdf",
        file_bytes=file_bytes,
    )
    highlighted_storage_path = None
    if highlighted_path:
        highlighted_bytes = await asyncio.to_thread(highlighted_path.read_bytes)
        highlighted_storage_path = await upsert_document_file(
            document_id=document_id,
            file_kind="highlighted",
            filename=f"{document_id}_highlighted.pdf",
            content_type="application/pdf",
            file_bytes=highlighted_bytes,
        )
    workflow_id = await start_full_analysis_saga(
        document_id=document_id,
        filename=filename,
        content_type=file.content_type or "application/pdf",
        file_bytes=file_bytes,
    )
    await save_document(
        StoredDocument(
            document_id=document_id,
            user_id=user.get("id"),
            workflow_id=workflow_id,
            filename=filename,
            status="PAUSED_HITL" if anomalies else "PROCESSING",
            source_pdf_path=str(source_path),
            highlighted_pdf_path=str(highlighted_path) if highlighted_path else None,
            source_storage_path=source_storage_path,
            highlighted_storage_path=highlighted_storage_path,
            anomalies=anomalies,
        )
    )
    return DocumentUploadResponse(
        workflow_id=workflow_id,
        document_id=document_id,
        status="PAUSED_HITL" if anomalies else "PROCESSING",
        anomaly_count=len(anomalies),
        highlighted_pdf_url=f"/api/v1/documents/{document_id}/highlighted-pdf",
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: str) -> DocumentStatusResponse:
    """Return document processing status and current workflow state."""
    document = await get_document(document_id)
    if document:
        return DocumentStatusResponse(
            document_id=document.document_id,
            status=document.status,
            workflow_id=document.workflow_id,
            workflow_state=document.status,
            anomaly_count=len(document.anomalies),
            highlighted_pdf_url=(
                f"/api/v1/documents/{document_id}/highlighted-pdf"
                if document.highlighted_storage_path
                else None
            ),
        )
    return DocumentStatusResponse(
        document_id=document_id,
        status="PENDING",
        workflow_id=None,
        workflow_state="NOT_STARTED",
        anomaly_count=0,
        highlighted_pdf_url=None,
    )


@router.get("/{document_id}/anomalies", response_model=DocumentAnomaliesResponse)
async def get_document_anomalies(document_id: str) -> DocumentAnomaliesResponse:
    """Return all anomalies associated with a document."""
    document = await get_document(document_id)
    if not document:
        return DocumentAnomaliesResponse(document_id=document_id, anomalies=[])
    return DocumentAnomaliesResponse(
        document_id=document_id,
        anomalies=[
            AnomalyItem(
                anomaly_id=anomaly.anomaly_id,
                metric_name=anomaly.metric_name,
                line_text=anomaly.source_text,
                actual_value=anomaly.actual_value,
                expected_range=anomaly.expected_range,
                severity=anomaly.severity,
                status=anomaly.status,
                description=anomaly.description,
                page=anomaly.page,
                bbox=anomaly.bbox,
                score=anomaly.score,
                reason=anomaly.reason,
                reviewer_comment=anomaly.reviewer_comment,
            )
            for anomaly in document.anomalies
        ],
    )


@router.get("/{document_id}/highlighted-pdf")
async def get_highlighted_pdf(document_id: str) -> Response:
    """Return the PDF copy with anomaly lines highlighted for HITL review."""
    stored_file = await fetch_document_file(document_id, "highlighted")
    if not stored_file:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=bytes(stored_file["file_data"]),
        media_type=stored_file["content_type"],
        headers={"Content-Disposition": f'inline; filename="{stored_file["filename"]}"'},
    )


@router.get("/{document_id}/source-pdf")
async def get_source_pdf(document_id: str) -> Response:
    """Return the originally uploaded PDF from Postgres."""
    stored_file = await fetch_document_file(document_id, "source")
    if not stored_file:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=bytes(stored_file["file_data"]),
        media_type=stored_file["content_type"],
        headers={"Content-Disposition": f'inline; filename="{stored_file["filename"]}"'},
    )
