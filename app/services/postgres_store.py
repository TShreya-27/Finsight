"""Postgres-backed document state and report storage."""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from app.core.settings import settings

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return settings.PG_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def _ensure_document_meta_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_meta (
            document_id UUID PRIMARY KEY,
            user_id TEXT,
            workflow_id TEXT,
            filename TEXT,
            status TEXT NOT NULL,
            source_pdf_path TEXT,
            highlighted_pdf_path TEXT,
            source_storage_path TEXT,
            highlighted_storage_path TEXT,
            anomalies JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    await conn.execute("ALTER TABLE document_meta ADD COLUMN IF NOT EXISTS user_id TEXT")


async def _ensure_document_files_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_files (
            document_id UUID NOT NULL,
            file_kind TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            file_data BYTEA NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (document_id, file_kind)
        )
        """
    )


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


async def upsert_document_file(
    *,
    document_id: str,
    file_kind: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> str:
    """Store a PDF file in Postgres and return its logical storage path."""
    conn = await _connect()
    try:
        await _ensure_document_files_table(conn)
        await conn.execute(
            """
            INSERT INTO document_files
                (document_id, file_kind, filename, content_type, file_data, updated_at)
            VALUES ($1::uuid, $2, $3, $4, $5, NOW())
            ON CONFLICT (document_id, file_kind) DO UPDATE SET
                filename = EXCLUDED.filename,
                content_type = EXCLUDED.content_type,
                file_data = EXCLUDED.file_data,
                updated_at = NOW()
            """,
            document_id,
            file_kind,
            filename,
            content_type,
            file_bytes,
        )
    finally:
        await conn.close()
    return f"postgres://document_files/{document_id}/{file_kind}"


async def fetch_document_file(document_id: str, file_kind: str) -> dict[str, Any] | None:
    """Fetch a stored PDF file from Postgres."""
    conn = await _connect()
    try:
        await _ensure_document_files_table(conn)
        row = await conn.fetchrow(
            """
            SELECT filename, content_type, file_data
            FROM document_files
            WHERE document_id = $1::uuid AND file_kind = $2
            """,
            document_id,
            file_kind,
        )
    finally:
        await conn.close()
    return dict(row) if row else None


async def upsert_document_meta(payload: dict[str, Any]) -> None:
    """Insert or update the document_meta row."""
    conn = await _connect()
    try:
        await _ensure_document_meta_table(conn)
        await conn.execute(
            """
            INSERT INTO document_meta
                (document_id, user_id, workflow_id, filename, status, source_pdf_path, highlighted_pdf_path,
                 source_storage_path, highlighted_storage_path, anomalies, updated_at)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,NOW())
            ON CONFLICT (document_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                workflow_id = EXCLUDED.workflow_id,
                filename = EXCLUDED.filename,
                status = EXCLUDED.status,
                source_pdf_path = EXCLUDED.source_pdf_path,
                highlighted_pdf_path = EXCLUDED.highlighted_pdf_path,
                source_storage_path = EXCLUDED.source_storage_path,
                highlighted_storage_path = EXCLUDED.highlighted_storage_path,
                anomalies = EXCLUDED.anomalies,
                updated_at = NOW()
            """,
            payload.get("document_id"),
            payload.get("user_id"),
            payload.get("workflow_id"),
            payload.get("filename"),
            payload.get("status"),
            payload.get("source_pdf_path"),
            payload.get("highlighted_pdf_path"),
            payload.get("source_storage_path"),
            payload.get("highlighted_storage_path"),
            json.dumps(payload.get("anomalies", [])),
        )
    finally:
        await conn.close()


async def fetch_document_meta(document_id: str) -> dict[str, Any] | None:
    """Fetch a document_meta row by document_id."""
    conn = await _connect()
    try:
        await _ensure_document_meta_table(conn)
        row = await conn.fetchrow(
            """
            SELECT document_id, user_id, workflow_id, filename, status, source_pdf_path, highlighted_pdf_path,
                   source_storage_path, highlighted_storage_path, anomalies
            FROM document_meta
            WHERE document_id = $1::uuid
            """,
            document_id,
        )
    finally:
        await conn.close()
    if not row:
        return None
    payload = dict(row)
    payload["document_id"] = str(payload["document_id"])
    payload["anomalies"] = _decode_json(payload.get("anomalies"), [])
    return payload


async def list_document_meta_for_user(user_id: str) -> list[dict[str, Any]]:
    """List document metadata rows for a user."""
    conn = await _connect()
    try:
        await _ensure_document_meta_table(conn)
        rows = await conn.fetch(
            """
            SELECT document_id, workflow_id, filename, status, highlighted_storage_path,
                   anomalies, created_at, updated_at
            FROM document_meta
            WHERE user_id = $1
            ORDER BY updated_at DESC
            """,
            user_id,
        )
    finally:
        await conn.close()

    documents: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["document_id"] = str(payload["document_id"])
        payload["anomalies"] = _decode_json(payload.get("anomalies"), [])
        documents.append(payload)
    return documents


async def update_document_status(document_id: str, status: str) -> None:
    """Update document_meta status."""
    conn = await _connect()
    try:
        await _ensure_document_meta_table(conn)
        await conn.execute(
            """
            UPDATE document_meta
            SET status = $1, updated_at = NOW()
            WHERE document_id = $2::uuid
            """,
            status,
            document_id,
        )
    finally:
        await conn.close()


async def update_anomaly_status(anomaly_id: str, status: str, notes: str | None = None) -> bool:
    """Update anomaly status inside document_meta.anomalies."""
    conn = await _connect()
    try:
        await _ensure_document_meta_table(conn)
        row = await conn.fetchrow(
            """
            SELECT document_id, anomalies
            FROM document_meta
            WHERE jsonb_path_exists(anomalies, '$[*] ? (@.anomaly_id == "' || $1 || '")')
            LIMIT 1
            """,
            anomaly_id,
        )
        if not row:
            return False

        anomalies = list(_decode_json(row["anomalies"], []))
        updated = False
        for anomaly in anomalies:
            if anomaly.get("anomaly_id") == anomaly_id:
                anomaly["status"] = status
                anomaly["reviewer_comment"] = notes
                updated = True
        if not updated:
            return False

        new_status = "REVIEW_COMPLETE"
        if any(str(item.get("status", "")).upper() == "PENDING" for item in anomalies):
            new_status = "PAUSED_HITL"

        await conn.execute(
            """
            UPDATE document_meta
            SET anomalies = $1::jsonb, status = $2, updated_at = NOW()
            WHERE document_id = $3
            """,
            json.dumps(anomalies),
            new_status,
            row["document_id"],
        )
        return True
    finally:
        await conn.close()


async def fetch_report(report_id: str) -> dict[str, Any] | None:
    """Fetch a persisted report by document_id."""
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT document_id, report_data, executive_summary
            FROM financial_reports
            WHERE document_id = $1::uuid
            """,
            report_id,
        )
    except asyncpg.UndefinedTableError:
        logger.warning("financial_reports table is missing")
        return None
    finally:
        await conn.close()
    if not row:
        return None
    payload = dict(row)
    payload["document_id"] = str(payload["document_id"])
    return payload
