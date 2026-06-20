"""Postgres-backed document state for the review UI."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services import postgres_store


@dataclass
class StoredAnomaly:
    anomaly_id: str
    metric_name: str
    actual_value: float | None
    expected_range: dict[str, float]
    severity: str
    status: str
    description: str
    source_text: str
    page: int
    bbox: list[float] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""
    reviewer_comment: str | None = None


@dataclass
class StoredDocument:
    document_id: str
    user_id: str | None
    workflow_id: str
    filename: str
    status: str
    source_pdf_path: str
    highlighted_pdf_path: str | None
    source_storage_path: str | None = None
    highlighted_storage_path: str | None = None
    anomalies: list[StoredAnomaly] = field(default_factory=list)

async def save_document(document: StoredDocument) -> None:
    """Store document state for API reads."""
    await postgres_store.upsert_document_meta(
        {
            "document_id": document.document_id,
            "user_id": document.user_id,
            "workflow_id": document.workflow_id,
            "filename": document.filename,
            "status": document.status,
            "source_pdf_path": document.source_pdf_path,
            "highlighted_pdf_path": document.highlighted_pdf_path,
            "source_storage_path": document.source_storage_path,
            "highlighted_storage_path": document.highlighted_storage_path,
            "anomalies": [
                {
                    "anomaly_id": item.anomaly_id,
                    "metric_name": item.metric_name,
                    "actual_value": item.actual_value,
                    "expected_range": item.expected_range,
                    "severity": item.severity,
                    "status": item.status,
                    "description": item.description,
                    "source_text": item.source_text,
                    "page": item.page,
                    "bbox": item.bbox,
                    "score": item.score,
                    "reason": item.reason,
                    "reviewer_comment": item.reviewer_comment,
                }
                for item in document.anomalies
            ],
        }
    )


async def get_document(document_id: str) -> StoredDocument | None:
    """Return stored document state."""
    payload = await postgres_store.fetch_document_meta(document_id)
    if not payload:
        return None
    return StoredDocument(
        document_id=payload["document_id"],
        user_id=payload.get("user_id"),
        workflow_id=payload.get("workflow_id") or "",
        filename=payload.get("filename") or "",
        status=payload.get("status") or "PENDING",
        source_pdf_path=payload.get("source_pdf_path") or "",
        highlighted_pdf_path=payload.get("highlighted_pdf_path"),
        source_storage_path=payload.get("source_storage_path"),
        highlighted_storage_path=payload.get("highlighted_storage_path"),
        anomalies=[
            StoredAnomaly(
                anomaly_id=item.get("anomaly_id", ""),
                metric_name=item.get("metric_name", ""),
                actual_value=item.get("actual_value"),
                expected_range=item.get("expected_range", {}),
                severity=item.get("severity", "LOW"),
                status=item.get("status", "PENDING"),
                description=item.get("description", ""),
                source_text=item.get("source_text", ""),
                page=item.get("page", 1),
                bbox=item.get("bbox", []),
                score=item.get("score", 0.0),
                reason=item.get("reason", item.get("description", "")),
                reviewer_comment=item.get("reviewer_comment"),
            )
            for item in payload.get("anomalies", []) or []
        ],
    )


async def update_anomaly_status(anomaly_id: str, status: str, notes: str | None = None) -> bool:
    """Update an anomaly status across stored documents."""
    return await postgres_store.update_anomaly_status(anomaly_id, status, notes)
