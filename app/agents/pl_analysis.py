"""P&L analysis agent."""

from app.agents._base import build_agent
from app.guardrails.custom import OutputSanityGuardrail
from app.schemas.pl_statement import PLStatement
from app.tools.compute_tools import compute_pl_metrics
from app.tools.finance_tools import fetch_historical_data, write_audit_entry

PL_ANALYSIS_INSTRUCTIONS_V1 = """
Call compute_pl_metrics() to calculate margins and surface any flags.
Only interpret the returned flags in words; do not do arithmetic in the LLM.
"""

pl_analysis_agent = build_agent(
    name="PLAnalysisAgent",
    instructions=PL_ANALYSIS_INSTRUCTIONS_V1,
    response_model=PLStatement,
    tools=[compute_pl_metrics, fetch_historical_data, write_audit_entry],
    pre_hooks=[OutputSanityGuardrail()],
)
