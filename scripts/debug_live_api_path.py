"""Debug the browser-facing API path against a live FastAPI server.

Run from the project root:
    .\\.venv\\Scripts\\python.exe scripts\\debug_live_api_path.py --base-url http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import httpx

SAMPLE_PDF = Path(r"D:\agentic_ai\sample_documents\BTPL004_BS_Q3_2024.pdf")


def fail(message: str) -> None:
    raise AssertionError(message)


def check_status(name: str, response: httpx.Response, expected: int) -> None:
    if response.status_code != expected:
        fail(f"{name} returned {response.status_code}, expected {expected}. Body: {response.text[:500]}")


def require_keys(name: str, payload: dict[str, Any], keys: set[str]) -> None:
    missing = keys - payload.keys()
    if missing:
        fail(f"{name} missing keys {sorted(missing)}. Payload was: {payload}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--pdf", default=str(SAMPLE_PDF))
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        fail(f"PDF does not exist: {pdf_path}")

    print(f"Checking live API path: {base_url}")
    print(f"PDF: {pdf_path}")

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{base_url}/api/v1/health")
        check_status("GET /api/v1/health", health, 200)
        print(f"OK health: {health.json()}")

        with pdf_path.open("rb") as file_obj:
            upload = client.post(
                f"{base_url}/api/v1/documents/upload",
                files={"file": (pdf_path.name, file_obj, "application/pdf")},
            )
        check_status("POST /api/v1/documents/upload", upload, 202)
        upload_payload = upload.json()
        require_keys(
            "upload response",
            upload_payload,
            {"workflow_id", "document_id", "status", "anomaly_count", "highlighted_pdf_url"},
        )
        print(f"OK upload payload: {upload_payload}")
        if upload_payload["anomaly_count"] <= 0:
            fail("Upload succeeded but anomaly_count is 0. The analyzer did not flag this PDF.")

        document_id = upload_payload["document_id"]
        status = client.get(f"{base_url}/api/v1/documents/{document_id}/status")
        check_status("GET document status", status, 200)
        status_payload = status.json()
        print(f"OK status payload: {status_payload}")
        if status_payload.get("anomaly_count", 0) <= 0:
            fail(f"Status endpoint returned zero flags: {status_payload}")

        anomalies = client.get(f"{base_url}/api/v1/documents/{document_id}/anomalies")
        check_status("GET document anomalies", anomalies, 200)
        anomaly_payload = anomalies.json()
        items = anomaly_payload.get("anomalies", [])
        if not items:
            fail(f"Anomalies endpoint returned no rows: {anomaly_payload}")
        print(f"OK anomalies returned: {len(items)}")
        for index, item in enumerate(items, start=1):
            require_keys(
                f"anomaly {index}",
                item,
                {"metric_name", "line_text", "bbox", "score", "reason", "page", "status"},
            )
            print(f"  {index}. {item['metric_name']} | score={item['score']} | page={item['page']}")

        pdf_response = client.get(
            f"{base_url}{upload_payload['highlighted_pdf_url']}",
            follow_redirects=True,
        )
        check_status("GET highlighted PDF", pdf_response, 200)
        content_type = pdf_response.headers.get("content-type", "")
        if "application/pdf" not in content_type:
            fail(f"Highlighted endpoint did not return PDF. content-type={content_type}, body={pdf_response.text[:200]}")
        print(f"OK highlighted PDF content-type: {content_type}")

        review_url = f"{base_url}/static/review.html?document_id={document_id}"
        review = client.get(review_url)
        check_status("GET static review page", review, 200)
        if "Human Check" not in review.text:
            fail("Static review page did not contain Human Check UI")
        print(f"OK review page: {review_url}")

    print("\nLive API path is healthy.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
