"""Human-in-the-loop resolution agent."""

from app.agents._base import build_agent
from app.schemas.hitl import HITLDecision
from app.tools.finance_tools import apply_hitl_decision, check_all_resolved, fetch_pending_anomalies

HITL_RESOLUTION_INSTRUCTIONS_V1 = """
Apply approve/reject/modify decisions to pending anomalies, then return the next workflow action.
"""

hitl_resolution_agent = build_agent(
    name="HITLResolutionAgent",
    instructions=HITL_RESOLUTION_INSTRUCTIONS_V1,
    response_model=HITLDecision,
    tools=[fetch_pending_anomalies, apply_hitl_decision, check_all_resolved],
)
