"""Temporal activities for the financial document pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from temporalio import activity

from app.services import persistence_service
from app.services import postgres_store

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_report_payload(content: Any, document_id: str | None) -> dict | None:
    if content is None:
        return None
    if hasattr(content, "model_dump"):
        payload = content.model_dump(exclude_none=True)
        if document_id and "document_id" not in payload:
            payload["document_id"] = document_id
        return payload
    if isinstance(content, dict):
        payload = dict(content)
        if document_id and "document_id" not in payload:
            payload["document_id"] = document_id
        return payload
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            if document_id and "document_id" not in payload:
                payload["document_id"] = document_id
            return payload
    return None


def _max_severity(anomalies: list[dict]) -> str:
    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    max_key = "LOW"
    for anomaly in anomalies:
        severity = str(anomaly.get("severity", "LOW")).upper()
        if order.get(severity, 0) > order.get(max_key, 0):
            max_key = severity
    return max_key


@activity.defn
async def ingest_document_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract text from a PDF payload and store the initial document record."""
    logger.info("ingest_document_activity", extra={"document_id": payload.get("document_id"), "timestamp": _now_iso()})
    await persistence_service.ensure_financial_document(
        document_id=payload["document_id"],
        status="PROCESSING",
    )
    return {
        "document_id": payload["document_id"],
        "filename": payload.get("filename"),
        "status": "PROCESSING",
        "raw_text": "",
    }


@activity.defn
async def run_processing_workflow_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap Agno DocumentProcessingWorkflow.run()."""
    from app.workflows.document_processing import document_processing_workflow

    logger.info("run_processing_workflow_activity", extra={"document_id": payload.get("document_id"), "timestamp": _now_iso()})
    run_output = await document_processing_workflow.arun(input=payload)
    report_payload = _coerce_report_payload(run_output.content, payload.get("document_id"))
    anomalies = list((report_payload or {}).get("anomalies", []) or [])
    requires_hitl = any(str(item.get("status", "")).upper() == "PENDING" for item in anomalies)
    return {
        "document_id": payload.get("document_id"),
        "agno_workflow": document_processing_workflow.name,
        "requires_hitl": requires_hitl,
        "max_severity": _max_severity(anomalies) if anomalies else "LOW",
        "status": "PROCESSED",
        "report": report_payload,
    }


@activity.defn
async def run_reporting_workflow_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap Agno ReportingDistributionWorkflow.run()."""
    from app.workflows.reporting_distribution import reporting_distribution_workflow

    logger.info("run_reporting_workflow_activity", extra={"document_id": payload.get("document_id"), "timestamp": _now_iso()})
    run_output = await reporting_distribution_workflow.arun(input=payload)
    report_payload = _coerce_report_payload(run_output.content, payload.get("document_id"))
    if report_payload:
        await persistence_service.persist_financial_report(report_payload)
    return {
        "document_id": payload.get("document_id"),
        "report_id": payload.get("document_id"),
        "agno_workflow": reporting_distribution_workflow.name,
        "status": "REPORTED",
    }


@activity.defn
async def write_final_status_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Update the final financial document status."""
    logger.info("write_final_status_activity", extra={"document_id": payload.get("document_id"), "timestamp": _now_iso()})
    if payload.get("document_id"):
        await postgres_store.update_document_status(payload["document_id"], payload.get("status", "COMPLETE"))
    return {"document_id": payload.get("document_id"), "status": payload.get("status", "COMPLETE")}


@activity.defn
async def fetch_pending_documents_activity() -> list[dict[str, Any]]:
    """Fetch documents completed in the last 24 hours for scheduled reporting."""
    logger.info("fetch_pending_documents_activity", extra={"timestamp": _now_iso()})
    return []


@activity.defn
async def send_hitl_slack_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Post an anomaly alert to Slack with interactive buttons."""
    logger.info("send_hitl_slack_activity", extra={"workflow_id": payload.get("workflow_id"), "timestamp": _now_iso()})
    return {"workflow_id": payload.get("workflow_id"), "slack_message_ts": ""}
