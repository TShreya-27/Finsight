"""Anomaly-investigation team: anomalies + compliance + audit."""

from agno.team import Team

from app.agents.anomaly import anomaly_detection_agent
from app.agents.compliance import compliance_agent
from app.agents.audit import audit_trail_agent
from app.core.infrastructure import shared_db, shared_memory
from app.core.settings import settings
from app.guardrails.custom import AnomalyThroughputGuardrail
from app.schemas.anomaly import AnomalyReport

anomaly_investigation_team = Team(
    name="AnomalyInvestigationTeam",
    model=settings.AGNO_MODEL,
    members=[anomaly_detection_agent, compliance_agent, audit_trail_agent],
    output_schema=AnomalyReport,
    memory_manager=shared_memory,
    pre_hooks=[AnomalyThroughputGuardrail()],
    db=shared_db,
)
