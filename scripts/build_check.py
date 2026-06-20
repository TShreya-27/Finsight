"""Local build smoke checks for FinSight AI."""

from __future__ import annotations

import compileall
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import fitz

from app.main import app
from temporal_app.workflows import FinancialDocumentSaga, FullAnalysisSaga, ScheduledReportSaga

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def assert_status(name: str, actual: int, expected: int) -> None:
    """Raise when an HTTP smoke check returns an unexpected status."""
    if actual != expected:
        raise AssertionError(f"{name} returned {actual}, expected {expected}")


def main() -> int:
    """Run local compile and API smoke checks."""
    compiled = compileall.compile_dir("app", quiet=1) and compileall.compile_dir("temporal_app", quiet=1)
    if not compiled:
        raise AssertionError("Python bytecode compilation failed")

    logger.info(
        "Temporal workflows import: %s, %s, %s",
        FinancialDocumentSaga.__name__,
        FullAnalysisSaga.__name__,
        ScheduledReportSaga.__name__,
    )

    client = TestClient(app)
    health = client.get("/api/v1/health")
    assert_status("GET /api/v1/health", health.status_code, 200)

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Revenue from Operations 1,00,00,000")
    page.insert_text((72, 96), "TOTAL OPERATING EXPENSES 95,00,000")
    pdf_bytes = document.tobytes()
    document.close()

    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )
    assert_status("POST /api/v1/documents/upload", upload.status_code, 202)
    body = upload.json()
    if not body.get("workflow_id") or not body.get("document_id"):
        raise AssertionError("Upload response missing workflow_id or document_id")

    logger.info("Build smoke checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception("Build smoke checks failed: %s", exc)
        raise SystemExit(1) from exc
