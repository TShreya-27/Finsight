"""Plain Python tools used by the Agno agents.

Keeping these as standalone functions makes them easy to test and reuse later
inside FastAPI endpoints or Temporal activities.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

import asyncpg

from app.core.settings import settings

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return settings.PG_URL


def hash_data(data: Any) -> str:
    """Stable SHA-256 hash for any JSON-serializable object."""
    serialized = json.dumps(data, default=str, sort_keys=True).encode()
    return hashlib.sha256(serialized).hexdigest()


def detect_document_type(raw_text: str) -> str:
    """Heuristic doc-type detector for financial PDFs."""
    text = raw_text.lower()
    if any(k in text for k in ["profit and loss", "income statement", "revenue from operations"]):
        return "PL"
    if any(k in text for k in ["total assets", "shareholders equity", "balance sheet"]):
        return "BALANCE_SHEET"
    if any(k in text for k in ["quarterly", "q1", "q2", "q3", "q4"]):
        return "QUARTERLY_REPORT"
    return "UNKNOWN"


def parse_indian_number(value_str: str) -> float:
    """Convert Indian-formatted numbers into a float."""
    value_str = value_str.strip()
    negative = value_str.startswith("(") and value_str.endswith(")")
    value_str = value_str.strip("()").replace(",", "")
    try:
        value = float(value_str)
        return -value if negative else value
    except ValueError:
        logger.warning("Could not parse number: %s", value_str)
        return 0.0


def validate_mandatory_fields(company_name: str, period_start: str, period_end: str, currency: str) -> dict:
    """Check whether the mandatory extraction fields exist."""
    missing = []
    if not company_name or company_name == "UNKNOWN":
        missing.append("company_name")
    if not period_start or period_start == "UNKNOWN":
        missing.append("period_start")
    if not period_end or period_end == "UNKNOWN":
        missing.append("period_end")
    if not currency:
        missing.append("currency")
    return {"valid": not missing, "missing": missing}


def map_label_to_canonical(raw_label: str) -> str:
    """Map messy PDF labels to canonical schema keys."""
    label = raw_label.lower().strip()
    mapping = {
        "revenue from operations": "revenue",
        "net revenue": "revenue",
        "total income": "revenue",
        "cost of goods sold": "cogs",
        "cost of materials consumed": "cogs",
        "cost of sales": "cogs",
        "gross profit": "gross_profit",
        "operating expenses": "operating_expenses",
        "selling general administrative": "operating_expenses",
        "ebitda": "ebitda",
        "profit before tax": "ebitda",
        "net profit": "net_income",
        "profit after tax": "net_income",
        "total assets": "total_assets",
        "current assets": "current_assets",
        "non-current assets": "non_current_assets",
        "total liabilities": "total_liabilities",
        "current liabilities": "current_liabilities",
        "non-current liabilities": "non_current_liabilities",
        "shareholders equity": "equity",
        "total equity": "equity",
    }
    for needle, canonical in mapping.items():
        if needle in label:
            return canonical
    return label.replace(" ", "_")

ALLOWED_METRICS = {
    "revenue",
    "gross_profit",
    "operating_expenses",
    "ebitda",
    "net_income",
}

async def fetch_historical_data(
    company_id: str,
    metric_name: str,
    periods: int = 4
) -> dict:
    """Fetch the most recent metric values for a company."""

    if metric_name not in ALLOWED_METRICS:
        raise ValueError(f"Invalid metric_name: {metric_name}")
    
    # Prevent absurd or malicious LIMIT values
    periods = min(max(periods, 1), 12)

    try:
        conn = await asyncpg.connect(_pg_url())

        query = f"""
        SELECT {metric_name}::float AS val
        FROM pl_statements
        WHERE document_id IN (
            SELECT id
            FROM financial_documents
            WHERE company_id = $1
            AND status = 'COMPLETE'
        )
        ORDER BY period_end DESC
        LIMIT $2
        """

        rows = await conn.fetch(
            query,
            company_id,
            periods,
        )

        await conn.close()

        values = [
            float(r["val"])
            for r in rows
            if r["val"] is not None
        ]

        if not values:
            return {
                "values": [],
                "mean": 0.0,
                "std_dev": 0.0,
                "periods": 0,
            }

        mean = sum(values) / len(values)

        std_dev = (
            sum((v - mean) ** 2 for v in values)
            / len(values)
        ) ** 0.5

        return {
            "values": values,
            "mean": mean,
            "std_dev": std_dev,
            "periods": len(values),
        }

    except Exception as exc:
        logger.error(
            "fetch_historical_data failed: %s",
            exc
        )

        return {
            "values": [],
            "mean": 0.0,
            "std_dev": 0.0,
            "periods": 0,
        }

def compute_deviation_pct(actual: float, historical_mean: float) -> float:
    """Compute absolute percentage deviation from the historical mean."""
    if historical_mean == 0:
        return 100.0 if actual != 0 else 0.0
    return abs((actual - historical_mean) / historical_mean) * 100


def classify_severity(deviation_pct: float) -> str:
    """Bucket deviation into LOW / MEDIUM / HIGH / CRITICAL."""
    if deviation_pct >= 50:
        return "CRITICAL"
    if deviation_pct >= 25:
        return "HIGH"
    if deviation_pct >= 10:
        return "MEDIUM"
    return "LOW"


async def save_anomaly_to_db(
    document_id: str,
    metric_name: str,
    expected_min: float,
    expected_max: float,
    actual_value: float,
    deviation_pct: float,
    severity: str,
    description: str,
) -> str:
    """Persist an anomaly record to PostgreSQL."""
    conn = await asyncpg.connect(_pg_url())
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO anomalies
                (document_id, metric_name, expected_range, actual_value, deviation_pct, severity, description, status)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, 'PENDING')
            RETURNING id::text
            """,
            document_id,
            metric_name,
            json.dumps({"min": expected_min, "max": expected_max}),
            actual_value,
            deviation_pct,
            severity,
            description,
        )
        return row["id"] if row else "UNKNOWN"
    finally:
        await conn.close()


async def fetch_pending_anomalies(document_id: str) -> list[dict]:
    """Fetch pending anomalies for a document."""
    conn = await asyncpg.connect(_pg_url())
    try:
        rows = await conn.fetch(
            """
            SELECT id::text, metric_name, severity, status, description
            FROM anomalies
            WHERE document_id = $1 AND status = 'PENDING'
            ORDER BY severity DESC
            """,
            document_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def apply_hitl_decision(
    anomaly_id: str,
    decision: str,
    reviewer_slack_id: str,
    notes: Optional[str] = None,
) -> bool:
    """Update anomaly status after human approval/rejection/modification."""
    status_map = {"approve": "APPROVED", "reject": "REJECTED", "modify": "MODIFIED"}
    new_status = status_map.get(decision, "PENDING")
    conn = await asyncpg.connect(_pg_url())
    try:
        async with conn.transaction():
            await conn.execute(
                "UPDATE anomalies SET status = $1, resolution_note = $2 WHERE id = $3",
                new_status,
                notes,
                anomaly_id,
            )
            await conn.execute(
                """
                UPDATE hitl_approvals
                SET decision = $1, reviewer_slack_id = $2, reviewed_at = NOW(), notes = $3
                WHERE anomaly_id = $4
                """,
                decision,
                reviewer_slack_id,
                notes,
                anomaly_id,
            )
        return True
    except Exception as exc:
        logger.error("apply_hitl_decision failed: %s", exc)
        return False
    finally:
        await conn.close()


async def check_all_resolved(document_id: str) -> bool:
    """True if the document has no remaining pending anomalies."""
    return len(await fetch_pending_anomalies(document_id)) == 0


async def upsert_pl_statement(document_id: str, pl: dict) -> bool:
    """Persist a validated P&L row."""
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO pl_statements
                (document_id, revenue, cogs, gross_profit, operating_expenses, ebitda, net_income, period_start, period_end, currency)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (document_id) DO UPDATE SET
                revenue = EXCLUDED.revenue,
                cogs = EXCLUDED.cogs,
                gross_profit = EXCLUDED.gross_profit,
                net_income = EXCLUDED.net_income
            """,
            document_id,
            pl.get("revenue"),
            pl.get("cogs"),
            pl.get("gross_profit"),
            pl.get("operating_expenses"),
            pl.get("ebitda"),
            pl.get("net_income"),
            pl.get("period_start"),
            pl.get("period_end"),
            pl.get("currency", "INR"),
        )
        return True
    finally:
        await conn.close()


async def upsert_balance_sheet(document_id: str, bs: dict) -> bool:
    """Persist a validated balance-sheet row."""
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO balance_sheets
                (document_id, total_assets, current_assets, non_current_assets, total_liabilities, current_liabilities, non_current_liabilities, equity, period_date, currency)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (document_id) DO UPDATE SET
                total_assets = EXCLUDED.total_assets,
                equity = EXCLUDED.equity
            """,
            document_id,
            bs.get("total_assets"),
            bs.get("current_assets"),
            bs.get("non_current_assets"),
            bs.get("total_liabilities"),
            bs.get("current_liabilities"),
            bs.get("non_current_liabilities"),
            bs.get("equity"),
            bs.get("period_date"),
            bs.get("currency", "INR"),
        )
        return True
    finally:
        await conn.close()


async def update_document_status(document_id: str, status: str) -> bool:
    """Update document lifecycle state."""
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute("UPDATE financial_documents SET status = $1 WHERE id = $2", status, document_id)
        return True
    finally:
        await conn.close()


async def rollback_and_record(document_id: str, reason: str) -> None:
    """Mark a document failed and add an audit row."""
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute("UPDATE financial_documents SET status = 'FAILED' WHERE id = $1", document_id)
        await conn.execute(
            "INSERT INTO audit_logs (workflow_run_id, agent_name, action) VALUES ('UNKNOWN', 'DataPersistenceAgent', $1)",
            f"ROLLBACK: {reason}",
        )
    finally:
        await conn.close()


def format_anomaly_slack_block(anomaly: dict, workflow_id: str, fastapi_base_url: str = "https://your-app.example.com") -> dict:
    """Build a Slack Block Kit payload with HITL buttons."""
    anomaly_id = anomaly.get("id", "unknown")
    callback = f"{fastapi_base_url}/api/v1/hitl/respond"
    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"Anomaly Detected - {anomaly.get('severity', 'UNKNOWN')}"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Metric:* {anomaly.get('metric_name')}"},
                {"type": "mrkdwn", "text": f"*Deviation:* {anomaly.get('deviation_pct', 0):.1f}%"},
                {"type": "mrkdwn", "text": f"*Actual:* {anomaly.get('actual_value')}"},
                {"type": "mrkdwn", "text": f"*Severity:* {anomaly.get('severity')}"},
            ]},
            {"type": "section", "text": {"type": "mrkdwn", "text": anomaly.get("description", "")}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "style": "primary", "action_id": f"hitl_approve_{anomaly_id}", "value": json.dumps({"action": "approve", "anomaly_id": anomaly_id, "workflow_id": workflow_id, "callback_url": callback})},
                {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "style": "danger", "action_id": f"hitl_reject_{anomaly_id}", "value": json.dumps({"action": "reject", "anomaly_id": anomaly_id, "workflow_id": workflow_id, "callback_url": callback})},
                {"type": "button", "text": {"type": "plain_text", "text": "Modify"}, "action_id": f"hitl_modify_{anomaly_id}", "value": json.dumps({"action": "modify", "anomaly_id": anomaly_id, "workflow_id": workflow_id, "callback_url": callback})},
            ]}
        ]
    }


async def post_slack_message(channel: str, payload: dict, slack_token: str) -> str:
    """Send a Slack Block Kit message."""
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {slack_token}"},
            json={"channel": channel, **payload},
            timeout=10.0,
        )
    data = resp.json()
    return data.get("ts", "") if data.get("ok") else ""


async def verify_slack_delivery(channel: str, ts: str, slack_token: str) -> bool:
    """Verify that Slack accepted the message."""
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {slack_token}"},
            params={"channel": channel, "latest": ts, "limit": 1, "inclusive": True},
            timeout=10.0,
        )
    data = resp.json()
    return any(m.get("ts") == ts for m in data.get("messages", []))


def format_report_html(report: dict) -> str:
    """Render a FinancialReport into HTML for email delivery."""
    pl = report.get("pl", {}) or {}
    bs = report.get("balance_sheet", {}) or {}
    anomalies = report.get("anomalies", [])
    summary = report.get("executive_summary", "No summary available.")
    rows = "".join(
        f"<tr><td>{a.get('metric_name')}</td><td>{a.get('severity')}</td><td>{a.get('deviation_pct', 0):.1f}%</td></tr>"
        for a in anomalies
    )
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif">
        <h1>FinSight Financial Report</h1>
        <p><strong>Executive Summary:</strong> {summary}</p>
        <h2>P&L Highlights</h2>
        <table border="1" cellpadding="6">
          <tr><th>Metric</th><th>Value</th></tr>
          <tr><td>Revenue</td><td>{pl.get('revenue', 0):,.0f}</td></tr>
          <tr><td>Gross Profit</td><td>{pl.get('gross_profit', 0):,.0f}</td></tr>
          <tr><td>Net Income</td><td>{pl.get('net_income', 0):,.0f}</td></tr>
        </table>
        <h2>Balance Sheet Snapshot</h2>
        <table border="1" cellpadding="6">
          <tr><th>Metric</th><th>Value</th></tr>
          <tr><td>Total Assets</td><td>{bs.get('total_assets', 0):,.0f}</td></tr>
          <tr><td>Equity</td><td>{bs.get('equity', 0):,.0f}</td></tr>
        </table>
        <h2>Anomalies ({len(anomalies)} detected)</h2>
        <table border="1" cellpadding="6">
          <tr><th>Metric</th><th>Severity</th><th>Deviation</th></tr>
          {rows}
        </table>
      </body>
    </html>
    """


async def send_email_report(to_address: str, subject: str, html_body: str, smtp_host: str = "localhost", smtp_port: int = 587) -> bool:
    """Send HTML email through SMTP."""
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "finsight@yourcompany.com"
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html"))
    try:
        await aiosmtplib.send(msg, hostname=smtp_host, port=smtp_port)
        return True
    except Exception:
        return False


async def write_audit_entry(
    workflow_run_id: str,
    agent_name: str,
    action: str,
    input_data: Any,
    output_data: Any,
    duration_ms: int,
    eval_score: Optional[float] = None,
) -> bool:
    """Write an immutable audit row with input/output hashes."""
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO audit_logs
                (workflow_run_id, agent_name, action, input_hash, output_hash, eval_score, duration_ms)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            workflow_run_id,
            agent_name,
            action,
            hash_data(input_data),
            hash_data(output_data),
            eval_score,
            duration_ms,
        )
        return True
    finally:
        await conn.close()
