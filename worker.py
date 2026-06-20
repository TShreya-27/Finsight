"""Temporal worker entrypoint."""

from __future__ import annotations

import asyncio
import logging

from temporalio.worker import Worker

from app.core.settings import settings
from app.services.temporal_client import get_temporal_client
from temporal_app.activities import (
    fetch_pending_documents_activity,
    ingest_document_activity,
    run_processing_workflow_activity,
    run_reporting_workflow_activity,
    send_hitl_slack_activity,
    write_final_status_activity,
)
from temporal_app.workflows import FinancialDocumentSaga, FullAnalysisSaga, ScheduledReportSaga

logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Temporal worker."""
    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[FinancialDocumentSaga, FullAnalysisSaga, ScheduledReportSaga],
        activities=[
            ingest_document_activity,
            run_processing_workflow_activity,
            run_reporting_workflow_activity,
            write_final_status_activity,
            fetch_pending_documents_activity,
            send_hitl_slack_activity,
        ],
    )
    logger.info("Starting Temporal worker on task queue %s", settings.TEMPORAL_TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
