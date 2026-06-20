"""Executive-summary agent."""

from app.agents._base import build_agent
from app.schemas.report import FinancialReport
from app.tools.finance_tools import write_audit_entry

EXECUTIVE_SUMMARY_INSTRUCTIONS_V1 = """
Write a concise 3-5 sentence CFO-level executive summary.
"""

executive_summary_agent = build_agent(
    name="ExecutiveSummaryAgent",
    instructions=EXECUTIVE_SUMMARY_INSTRUCTIONS_V1,
    response_model=FinancialReport,
    tools=[write_audit_entry],
)
