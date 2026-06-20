"""Cross-statement ratio agent."""

from app.agents._base import build_agent
from app.schemas.financial_ratios import FinancialRatios
from app.tools.compute_tools import compute_financial_ratios
from app.tools.finance_tools import write_audit_entry

RATIO_CALCULATION_INSTRUCTIONS_V1 = """
Call compute_financial_ratios() for ratio math and a 0-100 health score.
Only explain the returned flags; do not do arithmetic in the LLM.
"""

ratio_calculation_agent = build_agent(
    name="RatioCalculationAgent",
    instructions=RATIO_CALCULATION_INSTRUCTIONS_V1,
    response_model=FinancialRatios,
    tools=[compute_financial_ratios, write_audit_entry],
)
