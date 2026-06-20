"""Financial-analysis team: extraction + analysis + ratios."""

from agno.team import Team

from app.agents.extraction import extraction_agent
from app.agents.pl_analysis import pl_analysis_agent
from app.agents.balance_sheet import balance_sheet_agent
from app.agents.ratios import ratio_calculation_agent
from app.core.infrastructure import shared_db, shared_memory
from app.core.settings import settings
from app.guardrails.custom import OutputSanityGuardrail
from app.schemas.report import FinancialReport

financial_analysis_team = Team(
    name="FinancialAnalysisTeam",
    model=settings.AGNO_MODEL,
    members=[extraction_agent, pl_analysis_agent, balance_sheet_agent, ratio_calculation_agent],
    output_schema=FinancialReport,
    memory_manager=shared_memory,
    pre_hooks=[OutputSanityGuardrail()],
    db=shared_db,
)
