"""Distribution team: notifications + persistence + report + summary."""

from agno.team import Team

from app.agents.notification import notification_agent
from app.agents.persistence import data_persistence_agent
from app.agents.report import report_compilation_agent
from app.agents.summary import executive_summary_agent
from app.core.infrastructure import shared_db, shared_memory
from app.core.settings import settings
from app.guardrails.custom import OutputSanityGuardrail
from app.schemas.report import FinancialReport

distribution_team = Team(
    name="DistributionTeam",
    model=settings.AGNO_MODEL,
    members=[notification_agent, data_persistence_agent, report_compilation_agent, executive_summary_agent],
    output_schema=FinancialReport,
    memory_manager=shared_memory,
    pre_hooks=[OutputSanityGuardrail()],
    db=shared_db,
)
