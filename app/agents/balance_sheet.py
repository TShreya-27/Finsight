"""Balance-sheet analysis agent."""

from app.agents._base import build_agent
from app.guardrails.custom import OutputSanityGuardrail
from app.schemas.balance_sheet import BalanceSheet
from app.tools.finance_tools import fetch_historical_data, write_audit_entry

BALANCE_SHEET_ANALYSIS_INSTRUCTIONS_V1 = """
Compute current ratio, debt-to-equity, working capital, and leverage/liquidity flags.
"""

balance_sheet_agent = build_agent(
    name="BalanceSheetAnalysisAgent",
    instructions=BALANCE_SHEET_ANALYSIS_INSTRUCTIONS_V1,
    response_model=BalanceSheet,
    tools=[fetch_historical_data, write_audit_entry],
    pre_hooks=[OutputSanityGuardrail()],
)
