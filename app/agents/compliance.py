"""Compliance-check agent."""

from app.agents._base import build_agent
from app.schemas.compliance import ComplianceResult
from app.tools.finance_tools import write_audit_entry

COMPLIANCE_CHECK_INSTRUCTIONS_V1 = """
Validate accounting identities, date consistency, and negative revenue issues.
"""

compliance_agent = build_agent(
    name="ComplianceCheckAgent",
    instructions=COMPLIANCE_CHECK_INSTRUCTIONS_V1,
    response_model=ComplianceResult,
    tools=[write_audit_entry],
)
