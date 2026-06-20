"""Report compilation agent."""

from app.agents._base import build_agent
from app.schemas.report import FinancialReport
from app.tools.finance_tools import write_audit_entry

REPORT_COMPILATION_INSTRUCTIONS_V1 = """
Assemble the final FinancialReport from all prior outputs, without re-running analysis.
"""

report_compilation_agent = build_agent(
    name="ReportCompilationAgent",
    instructions=REPORT_COMPILATION_INSTRUCTIONS_V1,
    response_model=FinancialReport,
    tools=[write_audit_entry],
)
