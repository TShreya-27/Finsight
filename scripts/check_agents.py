"""Offline checks for FinSight agents, teams, guardrails, evals, and tools.

This script avoids LLM/provider calls. It verifies the local Agno objects are
configured correctly and that deterministic finance tools behave as expected.

Run from the project root:
    .\\.venv\\Scripts\\python.exe scripts\\check_agents.py
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agno.exceptions import InputCheckError  # noqa: E402

from app import agents  # noqa: E402
from app import teams  # noqa: E402
from app import workflows  # noqa: E402
from app.evals.custom import AnomalyResponseQualityEval, ExtractionAccuracyEval  # noqa: E402
from app.guardrails.custom import AnomalyThroughputGuardrail, FinancialPIIGuardrail, OutputSanityGuardrail  # noqa: E402
from app.services.pdf_analyzer import analyze_pdf_upload  # noqa: E402
from app.tools import finance_tools  # noqa: E402

SAMPLE_PDF = Path(r"D:\agentic_ai\sample_documents\BTPL004_BS_Q3_2024.pdf")


AGENT_EXPORTS = {
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


TEAM_EXPORTS = {
    "financial_analysis_team": teams.financial_analysis_team,
    "anomaly_investigation_team": teams.anomaly_investigation_team,
    "distribution_team": teams.distribution_team,
}


WORKFLOW_EXPORTS = {
    "document_processing_workflow": workflows.document_processing_workflow,
    "anomaly_resolution_workflow": workflows.anomaly_resolution_workflow,
    "reporting_distribution_workflow": workflows.reporting_distribution_workflow,
}


def ok(message: str) -> None:
    """Print a passing check."""
    print(f"OK {message}")


def fail(message: str) -> None:
    """Raise a consistent assertion failure."""
    raise AssertionError(message)


def expect_raises(name: str, func: Any, error_type: type[Exception]) -> None:
    """Assert a callable raises the expected error."""
    try:
        func()
    except error_type:
        ok(name)
        return
    fail(f"{name} did not raise {error_type.__name__}")


def check_agents() -> None:
    """Validate agent object configuration without calling an LLM."""
    print("\nAgents")
    print("------")
    if len(AGENT_EXPORTS) < 10:
        fail(f"Expected at least 10 agents, found {len(AGENT_EXPORTS)}")

    for export_name, agent in AGENT_EXPORTS.items():
        agent_name = getattr(agent, "name", "")
        instructions = str(getattr(agent, "instructions", "") or "").strip()
        output_schema = getattr(agent, "output_schema", None)
        tools = list(getattr(agent, "tools", []) or [])
        memory_manager = getattr(agent, "memory_manager", None)
        db = getattr(agent, "db", None)

        if not agent_name:
            fail(f"{export_name} missing name")
        if len(instructions) < 20:
            fail(f"{export_name} has empty or weak instructions")
        if output_schema is None:
            fail(f"{export_name} missing output_schema")
        if memory_manager is None:
            fail(f"{export_name} missing shared memory_manager")
        if db is None:
            fail(f"{export_name} missing shared db")
        if not hasattr(output_schema, "model_fields"):
            fail(f"{export_name} output_schema is not a Pydantic model")

        tool_names = [getattr(tool, "__name__", str(tool)) for tool in tools]
        ok(f"{export_name}: {agent_name}, schema={output_schema.__name__}, tools={tool_names}")


def check_teams_and_workflows() -> None:
    """Validate team and workflow objects load and expose core metadata."""
    print("\nTeams")
    print("-----")
    for export_name, team in TEAM_EXPORTS.items():
        members = list(getattr(team, "members", []) or [])
        output_schema = getattr(team, "output_schema", None)
        if not getattr(team, "name", ""):
            fail(f"{export_name} missing name")
        if not members:
            fail(f"{export_name} missing members")
        if output_schema is None:
            fail(f"{export_name} missing output_schema")
        if getattr(team, "memory_manager", None) is None:
            fail(f"{export_name} missing memory_manager")
        ok(f"{export_name}: {team.name}, members={len(members)}, schema={output_schema.__name__}")

    print("\nWorkflows")
    print("---------")
    for export_name, workflow in WORKFLOW_EXPORTS.items():
        if not getattr(workflow, "name", ""):
            fail(f"{export_name} missing name")
        steps = getattr(workflow, "steps", None)
        if not steps:
            fail(f"{export_name} missing steps")
        ok(f"{export_name}: {workflow.name}, steps={len(steps)}")


def check_tools() -> None:
    """Exercise deterministic finance tools with known inputs."""
    print("\nTools")
    print("-----")
    balance_sheet_text = "BALANCE SHEET\nTOTAL ASSETS 14,70,00,000\nTOTAL LIABILITIES & EQUITY 14,70,00,000"
    if finance_tools.detect_document_type(balance_sheet_text) != "BALANCE_SHEET":
        fail("detect_document_type did not detect balance sheet")
    ok("detect_document_type detects BALANCE_SHEET")

    if finance_tools.parse_indian_number("3,08,00,000") != 30_800_000:
        fail("parse_indian_number failed for Indian format")
    if finance_tools.parse_indian_number("(1,20,000)") != -120_000:
        fail("parse_indian_number failed for bracket negative")
    ok("parse_indian_number parses Indian numbers and negatives")

    mandatory = finance_tools.validate_mandatory_fields("BlueStar", "2024-07-01", "2024-09-30", "INR")
    if not mandatory["valid"]:
        fail(f"validate_mandatory_fields marked valid data invalid: {mandatory}")
    missing = finance_tools.validate_mandatory_fields("UNKNOWN", "UNKNOWN", "2024-09-30", "")
    if missing["valid"] or set(missing["missing"]) != {"company_name", "period_start", "currency"}:
        fail(f"validate_mandatory_fields did not detect missing fields: {missing}")
    ok("validate_mandatory_fields detects present and missing fields")

    if finance_tools.map_label_to_canonical("Trade Receivables (Net)") != "trade_receivables_(net)":
        fail("map_label_to_canonical fallback changed unexpectedly")
    if finance_tools.map_label_to_canonical("TOTAL ASSETS") != "total_assets":
        fail("map_label_to_canonical did not map total assets")
    ok("map_label_to_canonical maps known labels and stable fallbacks")

    deviation = finance_tools.compute_deviation_pct(150, 100)
    if deviation != 50:
        fail(f"compute_deviation_pct expected 50, got {deviation}")
    if finance_tools.classify_severity(deviation) != "CRITICAL":
        fail("classify_severity expected CRITICAL for 50 percent deviation")
    ok("compute_deviation_pct and classify_severity work")

    block = finance_tools.format_anomaly_slack_block(
        {"id": "A1", "metric_name": "TOTAL EQUITY", "severity": "HIGH", "deviation_pct": 31.0, "actual_value": 5},
        "workflow-1",
        "http://127.0.0.1:8001",
    )
    values = [button["value"] for button in block["blocks"][-1]["elements"]]
    if not all("/api/v1/hitl/respond" in json.loads(value)["callback_url"] for value in values):
        fail("Slack HITL callback URL is not wired to /api/v1/hitl/respond")
    ok("format_anomaly_slack_block includes HITL callback payloads")

    html = finance_tools.format_report_html({"executive_summary": "Summary", "anomalies": [{"metric_name": "X", "severity": "HIGH", "deviation_pct": 25}]})
    if "FinSight Financial Report" not in html or "Summary" not in html:
        fail("format_report_html missing expected report content")
    ok("format_report_html renders report content")


def check_guardrails_and_evals() -> None:
    """Verify guardrails reject bad examples and evals score examples."""
    print("\nGuardrails")
    print("----------")
    expect_raises(
        "FinancialPIIGuardrail blocks PAN-like identifiers",
        lambda: FinancialPIIGuardrail().check(SimpleNamespace(input_content="Customer PAN ABCDE1234F")),
        InputCheckError,
    )
    expect_raises(
        "OutputSanityGuardrail blocks impossible net income",
        lambda: OutputSanityGuardrail().check(SimpleNamespace(input_content=json.dumps({"revenue": 100, "net_income": 2000}))),
        InputCheckError,
    )
    expect_raises(
        "AnomalyThroughputGuardrail blocks more than 20 anomalies",
        lambda: AnomalyThroughputGuardrail().check(SimpleNamespace(input_content=json.dumps({"anomalies": list(range(21))}))),
        InputCheckError,
    )

    async def async_guardrail_checks() -> None:
        await FinancialPIIGuardrail().async_check(SimpleNamespace(input_content="No sensitive ID here"))
        await OutputSanityGuardrail().async_check(SimpleNamespace(input_content=json.dumps({"revenue": 100, "net_income": 50})))
        await AnomalyThroughputGuardrail().async_check(SimpleNamespace(input_content=json.dumps({"anomalies": [1, 2]})))

    asyncio.run(async_guardrail_checks())
    ok("async guardrail checks accept safe inputs")

    print("\nEvals")
    print("-----")
    extraction_score = ExtractionAccuracyEval().evaluate_balance_sheet(
        {"total_assets": 14_700_000, "total_liabilities": 9_700_000, "equity": 5_000_000}
    )
    if extraction_score != 1.0:
        fail(f"ExtractionAccuracyEval expected 1.0, got {extraction_score}")
    ok("ExtractionAccuracyEval scores a balanced balance sheet")

    quality = AnomalyResponseQualityEval().score_text(
        "Revenue variance creates liquidity risk. Recommend CFO investigate receivable aging and supporting schedules."
    )
    if not quality.passed:
        fail(f"AnomalyResponseQualityEval expected pass, got {quality}")
    ok(f"AnomalyResponseQualityEval passed with score={quality.score:.2f}")


def check_pdf_detection() -> None:
    """Verify the local PDF anomaly path produces bbox-backed flags."""
    print("\nPDF Anomaly Path")
    print("----------------")
    if not SAMPLE_PDF.exists():
        ok(f"sample PDF not found at {SAMPLE_PDF}; skipping local PDF path")
        return

    result = analyze_pdf_upload(
        document_id="agent-check",
        filename=SAMPLE_PDF.name,
        file_bytes=SAMPLE_PDF.read_bytes(),
    )
    if len(result.anomalies) < 1:
        fail("Expected at least one anomaly from the sample balance sheet")
    for anomaly in result.anomalies:
        if not anomaly.bbox:
            fail(f"Anomaly {anomaly.metric_name} missing bbox")
        if not anomaly.reason:
            fail(f"Anomaly {anomaly.metric_name} missing reason")
    ok(f"sample PDF produced {len(result.anomalies)} bbox-backed anomalies")


def pdf_from_lines(lines: list[str]) -> bytes:
    """Create a selectable-text PDF for rule checks."""
    document = fitz.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((72, 72 + index * 18), line)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def require_metrics(result: Any, expected_metrics: set[str], label: str) -> None:
    """Assert expected metrics were flagged and every flag has coordinates."""
    found = {anomaly.metric_name for anomaly in result.anomalies}
    missing = expected_metrics - found
    if missing:
        details = "\n".join(f"- {anomaly.metric_name}: {anomaly.reason}" for anomaly in result.anomalies)
        fail(f"{label} missing expected metrics {sorted(missing)}. Found {sorted(found)}\n{details}")
    for anomaly in result.anomalies:
        if not anomaly.bbox:
            fail(f"{label} anomaly {anomaly.metric_name} missing bbox")


def check_pdf_parameter_rules() -> None:
    """Verify PDF content is flagged using the requested Balance Sheet and P&L parameters."""
    print("\nPDF Parameter Rules")
    print("-------------------")
    balance_sheet_pdf = pdf_from_lines(
        [
            "Example Company Pvt Ltd",
            "BALANCE SHEET",
            "As at September 30, 2024",
            "ASSETS",
            "CURRENT ASSETS",
            "Cash & Cash Equivalents 1,00,000",
            "Trade Receivables (Net) 2,00,000",
            "Inventories 50,000",
            "Other Current Assets 50,000",
            "TOTAL CURRENT ASSETS 5,00,000",
            "NON-CURRENT ASSETS",
            "Property, Plant & Equipment (Net) 3,00,000",
            "Intangible Assets & Goodwill 1,00,000",
            "Other Non-Current Assets 1,00,000",
            "TOTAL NON-CURRENT ASSETS 6,00,000",
            "TOTAL ASSETS 10,00,000",
            "EQUITY & LIABILITIES",
            "CURRENT LIABILITIES",
            "Trade Payables 1,00,000",
            "Short-Term Borrowings 1,50,000",
            "Other Current Liabilities & Provisions 50,000",
            "TOTAL CURRENT LIABILITIES 2,50,000",
            "NON-CURRENT LIABILITIES",
            "Long-Term Borrowings 7,00,000",
            "Deferred Tax Liabilities (Net) 50,000",
            "Other Non-Current Liabilities 50,000",
            "TOTAL NON-CURRENT LIABILITIES 9,00,000",
            "TOTAL LIABILITIES 12,00,000",
            "TOTAL EQUITY 2,00,000",
            "TOTAL LIABILITIES & EQUITY 13,00,000",
        ]
    )
    bs_result = analyze_pdf_upload(
        document_id="agent-check-bs-rules",
        filename="bs_rules.pdf",
        file_bytes=balance_sheet_pdf,
    )
    require_metrics(
        bs_result,
        {
            "Current Assets Subtotal",
            "Non-Current Assets Subtotal",
            "Total Assets Subtotal",
            "Current Liabilities Subtotal",
            "Non-Current Liabilities Subtotal",
            "Total Liabilities Subtotal",
            "Total Liabilities & Equity",
            "Accounting Equation",
            "Balance Sheet Identity",
            "Long-Term Borrowings Leverage",
        },
        "balance sheet rule check",
    )
    ok("Balance Sheet Agent rules flag accounting consistency, subtotals, equity, and borrowings")

    pl_pdf = pdf_from_lines(
        [
            "Example Company Pvt Ltd",
            "STATEMENT OF PROFIT & LOSS",
            "For the Quarter: Jul 01, 2024 to Sep 30, 2024",
            "Revenue from Operations 1,00,000",
            "TOTAL INCOME (A) 1,00,000",
            "Cost of Goods Sold (COGS) 0",
            "GROSS PROFIT (A - COGS) 1,20,000",
            "Gross Margin 120.00%",
            "EARNINGS BEFORE INTEREST, TAX, D&A (EBITDA) 1,10,000",
            "NET PROFIT / (LOSS) AFTER TAX 1,50,000",
        ]
    )
    pl_result = analyze_pdf_upload(
        document_id="agent-check-pl-rules",
        filename="pl_rules.pdf",
        file_bytes=pl_pdf,
    )
    require_metrics(
        pl_result,
        {
            "GROSS PROFIT (A - COGS)",
            "Gross Margin",
            "EARNINGS BEFORE INTEREST, TAX, D&A (EBITDA)",
            "NET PROFIT / (LOSS) AFTER TAX",
            "Margin Spike",
        },
        "P&L profit and margin rule check",
    )
    ok("P&L Agent rules flag profit greater than revenue and margin spikes")

    negative_revenue_pdf = pdf_from_lines(
        [
            "Example Company Pvt Ltd",
            "STATEMENT OF PROFIT & LOSS",
            "Revenue from Operations (1,00,000)",
            "TOTAL INCOME (A) (1,00,000)",
            "NET PROFIT / (LOSS) AFTER TAX (50,000)",
        ]
    )
    negative_result = analyze_pdf_upload(
        document_id="agent-check-negative-revenue",
        filename="negative_revenue.pdf",
        file_bytes=negative_revenue_pdf,
    )
    require_metrics(negative_result, {"Revenue from Operations"}, "P&L negative revenue rule check")
    ok("P&L Agent rules flag negative revenue")


def check_async_tool_signatures() -> None:
    """Make sure DB/network tools are async so they can be safely awaited by agents."""
    print("\nAsync Tool Signatures")
    print("---------------------")
    async_tools = [
        finance_tools.fetch_historical_data,
        finance_tools.save_anomaly_to_db,
        finance_tools.fetch_pending_anomalies,
        finance_tools.apply_hitl_decision,
        finance_tools.check_all_resolved,
        finance_tools.upsert_pl_statement,
        finance_tools.upsert_balance_sheet,
        finance_tools.update_document_status,
        finance_tools.rollback_and_record,
        finance_tools.post_slack_message,
        finance_tools.verify_slack_delivery,
        finance_tools.send_email_report,
        finance_tools.write_audit_entry,
    ]
    for tool in async_tools:
        if not inspect.iscoroutinefunction(tool):
            fail(f"{tool.__name__} should be async")
    ok(f"{len(async_tools)} database/network tools are async")


def main() -> int:
    """Run all offline checks."""
    check_agents()
    check_teams_and_workflows()
    check_tools()
    check_guardrails_and_evals()
    check_pdf_detection()
    check_pdf_parameter_rules()
    check_async_tool_signatures()
    print("\nAll offline agent checks passed.")
    print("Note: this does not call the LLM provider. Run a live agent execution only after confirming API keys/network are configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
