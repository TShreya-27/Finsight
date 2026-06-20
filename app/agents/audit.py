"""Audit-trail agent."""

from app.agents._base import build_agent
from app.schemas.audit import AuditEntry
from app.tools.finance_tools import hash_data, write_audit_entry

AUDIT_TRAIL_INSTRUCTIONS_V1 = """
Write immutable audit entries for every significant agent action.
"""

audit_trail_agent = build_agent(
    name="AuditTrailAgent",
    instructions=AUDIT_TRAIL_INSTRUCTIONS_V1,
    response_model=AuditEntry,
    tools=[hash_data, write_audit_entry],
)
