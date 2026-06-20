"""Data-persistence agent."""

from app.agents._base import build_agent
from app.schemas.report import FinancialReport
from app.tools.finance_tools import write_audit_entry

DATA_PERSISTENCE_INSTRUCTIONS_V1 = """
Record audit metadata for persistence steps only.
Do not write financial data or change document status.
"""

data_persistence_agent = build_agent(
    name="DataPersistenceAgent",
    instructions=DATA_PERSISTENCE_INSTRUCTIONS_V1,
    response_model=FinancialReport,
    tools=[write_audit_entry],
)
