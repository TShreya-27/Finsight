"""Temporal saga definitions for FinSight AI."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_app.activities import (
        fetch_pending_documents_activity,
        ingest_document_activity,
        run_processing_workflow_activity,
        run_reporting_workflow_activity,
        send_hitl_slack_activity,
        write_final_status_activity,
    )


ACTIVITY_TIMEOUT = timedelta(minutes=5)
SAGA_TIMEOUT = timedelta(hours=24)


def retry_policy() -> RetryPolicy:
    """Return the standard activity retry policy."""
    return RetryPolicy(
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(seconds=30),
        maximum_attempts=3,
        non_retryable_error_types=["ValidationError", "ValueError"],
    )


@workflow.defn
class FinancialDocumentSaga:
    """Simple no-HITL document processing saga."""

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        document = await workflow.execute_activity(
            ingest_document_activity,
            payload,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )
        processed = await workflow.execute_activity(
            run_processing_workflow_activity,
            document,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )
        return await workflow.execute_activity(
            write_final_status_activity,
            {"document_id": processed["document_id"], "status": "COMPLETE"},
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )


@workflow.defn
class FullAnalysisSaga:
    """Full pipeline saga with HITL signal support."""

    def __init__(self) -> None:
        self.hitl_decisions: list[dict[str, Any]] = []

    @workflow.signal
    async def submit_hitl_decision(self, decision: dict[str, Any]) -> None:
        """Receive HITL decisions from FastAPI."""
        self.hitl_decisions.append(decision)

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        document = await workflow.execute_activity(
            ingest_document_activity,
            payload,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )
        processed = await workflow.execute_activity(
            run_processing_workflow_activity,
            document,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )

        if processed.get("requires_hitl"):
            await workflow.execute_activity(
                send_hitl_slack_activity,
                {"workflow_id": workflow.info().workflow_id, **processed},
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=retry_policy(),
            )
            await workflow.wait_condition(lambda: len(self.hitl_decisions) > 0, timeout=SAGA_TIMEOUT)

        report = await workflow.execute_activity(
            run_reporting_workflow_activity,
            processed,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )
        return await workflow.execute_activity(
            write_final_status_activity,
            {"document_id": report["document_id"], "status": "COMPLETE"},
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )


@workflow.defn
class ScheduledReportSaga:
    """Daily digest saga for recently completed documents."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        documents = await workflow.execute_activity(
            fetch_pending_documents_activity,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=retry_policy(),
        )
        reports = []
        for document in documents:
            reports.append(
                await workflow.execute_activity(
                    run_reporting_workflow_activity,
                    document,
                    start_to_close_timeout=ACTIVITY_TIMEOUT,
                    retry_policy=retry_policy(),
                )
            )
        return {"documents": len(documents), "reports": reports}
