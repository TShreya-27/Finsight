"""Persistence helpers called by Temporal activities."""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg
from pydantic import ValidationError

from app.core.settings import settings
from app.schemas.report import FinancialReport
from app.tools import finance_tools

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return settings.PG_URL


async def ensure_financial_document(*, document_id: str, status: str = "PENDING") -> None:
    """Ensure a financial_documents row exists for foreign-keyed inserts."""
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO financial_documents (id, status)
            VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status
            """,
            document_id,
            status,
        )
    finally:
        await conn.close()


async def _upsert_financial_report(*, document_id: str, report_data: dict, executive_summary: str | None) -> None:
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO financial_reports (document_id, report_data, executive_summary)
            VALUES ($1, $2::jsonb, $3)
            ON CONFLICT (document_id) DO UPDATE SET
                report_data = EXCLUDED.report_data,
                executive_summary = EXCLUDED.executive_summary,
                generated_at = NOW()
            """,
            document_id,
            json.dumps(report_data),
            executive_summary,
        )
    finally:
        await conn.close()


def _coerce_report(payload: Any) -> FinancialReport | None:
    if payload is None:
        return None
    if isinstance(payload, FinancialReport):
        return payload
    if isinstance(payload, dict):
        try:
            return FinancialReport.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Failed to validate FinancialReport: %s", exc)
            return None
    return None


async def persist_financial_report(report_payload: Any) -> None:
    """Persist report data and supporting financial statements to PostgreSQL."""
    report = _coerce_report(report_payload)
    if report is None:
        logger.warning("persist_financial_report received invalid payload")
        return

    await ensure_financial_document(document_id=report.document_id, status="PROCESSED")

    if report.pl:
        await finance_tools.upsert_pl_statement(report.document_id, report.pl.model_dump())
    if report.balance_sheet:
        await finance_tools.upsert_balance_sheet(report.document_id, report.balance_sheet.model_dump())

    await _upsert_financial_report(
        document_id=report.document_id,
        report_data=report.model_dump(exclude_none=True),
        executive_summary=report.executive_summary,
    )
