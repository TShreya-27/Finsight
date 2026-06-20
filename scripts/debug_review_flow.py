"""Debug the FinSight upload, anomaly review, HITL, and agent wiring flow.

Run from the project root:
    .\\.venv\\Scripts\\python.exe scripts\\debug_review_flow.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import fitz
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import agents  # noqa: E402
from app.main import app  # noqa: E402

SAMPLE_PDF = Path(r"D:\agentic_ai\sample_documents\BTPL004_BS_Q3_2024.pdf")


def assert_status(name: str, actual: int, expected: int, body: Any | None = None) -> None:
    """Raise a useful failure with the response body included."""
    if actual != expected:
        raise AssertionError(f"{name} returned {actual}, expected {expected}. Body: {body}")


def make_fallback_pdf() -> bytes:
    """Create a tiny balance-sheet PDF when the assignment sample is unavailable."""
    document = fitz.open()
    page = document.new_page()
    lines = [
        "BlueStar Technologies Pvt Ltd",
        "BALANCE SHEET",
        "As at September 30, 2024",
        "CURRENT ASSETS",
        "Trade Receivables (Net) 3,08,00,000",
        "TOTAL CURRENT ASSETS 8,80,00,000",
        "TOTAL ASSETS 14,70,00,000",
        "TOTAL LIABILITIES 9,70,00,000",
        "Retained Earnings / (Accumulated Loss) 2,50,00,000",
        "TOTAL EQUITY 5,00,00,000",
        "TOTAL LIABILITIES & EQUITY 14,70,00,000",
    ]
    for index, line in enumerate(lines):
        page.insert_text((72, 72 + index * 20), line)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def load_pdf_bytes() -> tuple[str, bytes]:
    """Load the provided sample PDF, or generate a deterministic fallback."""
    if SAMPLE_PDF.exists():
        return SAMPLE_PDF.name, SAMPLE_PDF.read_bytes()
    return "debug_balance_sheet.pdf", make_fallback_pdf()


def check_agents() -> None:
    """Verify the expected agent objects import and expose basic Agno metadata."""
    expected_agents = {
        "extraction_agent": agents.extraction_agent,
        "anomaly_detection_agent": agents.anomaly_detection_agent,
        "hitl_resolution_agent": agents.hitl_resolution_agent,
        "data_persistence_agent": agents.data_persistence_agent,
        "notification_agent": agents.notification_agent,
        "pl_analysis_agent": agents.pl_analysis_agent,
        "balance_sheet_agent": agents.balance_sheet_agent,
        "ratio_calculation_agent": agents.ratio_calculation_agent,
        "compliance_agent": agents.compliance_agent,
        "audit_trail_agent": agents.audit_trail_agent,
        "report_compilation_agent": agents.report_compilation_agent,
        "executive_summary_agent": agents.executive_summary_agent,
    }
    print("\nAgent import check")
    print("------------------")
    for export_name, agent in expected_agents.items():
        agent_name = getattr(agent, "name", "<missing name>")
        output_schema = getattr(agent, "output_schema", None)
        if output_schema is None:
            raise AssertionError(f"{export_name} ({agent_name}) is missing output_schema")
        print(f"OK {export_name}: {agent_name} -> {output_schema}")


def check_review_flow() -> None:
    """Exercise the exact browser-facing review flow with TestClient."""
    client = TestClient(app)
    filename, pdf_bytes = load_pdf_bytes()

    print("\nFrontend route check")
    print("--------------------")
    home = client.get("/")
    assert_status("GET /", home.status_code, 200, home.text[:200])
    if "Welcome to Finsight" not in home.text or "Upload Pdf" not in home.text:
        raise AssertionError("Upload page did not contain the new Finsight landing UI")
    print("OK GET / returned the upload page")

    print("\nUpload and anomaly check")
    print("------------------------")
    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )
    upload_body = upload.json()
    assert_status("POST /api/v1/documents/upload", upload.status_code, 202, upload_body)
    document_id = upload_body["document_id"]
    workflow_id = upload_body["workflow_id"]
    print(f"OK uploaded {filename}")
    print(f"document_id={document_id}")
    print(f"workflow_id={workflow_id}")
    print(f"anomaly_count={upload_body['anomaly_count']}")

    review = client.get(f"/static/review.html?document_id={document_id}")
    assert_status("GET /static/review.html", review.status_code, 200, review.text[:200])
    if "Human Check" not in review.text:
        raise AssertionError("Review page did not contain the Human Check UI")
    print("OK review page renders Human Check")

    status = client.get(f"/api/v1/documents/{document_id}/status")
    status_body = status.json()
    assert_status("GET document status", status.status_code, 200, status_body)
    print(f"OK status={status_body['status']}")

    anomalies = client.get(f"/api/v1/documents/{document_id}/anomalies")
    anomalies_body = anomalies.json()
    assert_status("GET document anomalies", anomalies.status_code, 200, anomalies_body)
    items = anomalies_body["anomalies"]
    if not items:
        raise AssertionError("No anomalies were returned; check pdf_analyzer rules")
    print(f"OK anomalies returned: {len(items)}")
    for index, anomaly in enumerate(items, start=1):
        print(
            f"{index}. {anomaly['metric_name']} | score={anomaly['score']} "
            f"| page={anomaly['page']} | bbox={anomaly['bbox']}"
        )

    highlighted = client.get(f"/api/v1/documents/{document_id}/highlighted-pdf")
    assert_status("GET highlighted PDF", highlighted.status_code, 200, highlighted.text[:100])
    print(f"OK highlighted PDF content-type={highlighted.headers.get('content-type')}")

    first = items[0]
    override = client.post(
        f"/api/v1/hitl/{first['anomaly_id']}/override",
        json={
            "workflow_id": workflow_id,
            "anomaly_id": first["anomaly_id"],
            "action": "correct",
            "notes": "Debug script verification",
        },
    )
    override_body = override.json()
    assert_status("POST HITL override", override.status_code, 202, override_body)
    if override_body["status"] != "CORRECT":
        raise AssertionError(f"Expected CORRECT after override, got {override_body}")
    print(f"OK override saved for anomaly_id={first['anomaly_id']}")

    refreshed = client.get(f"/api/v1/documents/{document_id}/anomalies").json()["anomalies"]
    refreshed_first = next(item for item in refreshed if item["anomaly_id"] == first["anomaly_id"])
    if refreshed_first["status"] != "CORRECT":
        raise AssertionError(f"Stored anomaly status was not updated: {refreshed_first}")
    print("OK stored anomaly status changed to CORRECT")


def main() -> int:
    """Run all debug checks."""
    check_agents()
    check_review_flow()
    print("\nAll debug checks passed.")
    print("If the browser still shows {'detail': 'Not Found'}, open the app at the active FastAPI port and refresh cached JS/CSS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
