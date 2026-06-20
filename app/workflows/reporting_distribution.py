"""Workflow that compiles the report and pushes it through the distribution team."""

from agno.workflow import Workflow, Step, Parallel, Router

from app.agents.report import report_compilation_agent
from app.agents.summary import executive_summary_agent
from app.teams.distribution import distribution_team


def route_by_severity(step_input, step_choices=None):
    """Choose the delivery path based on severity text."""
    text = str(getattr(step_input, "input", "")).lower()
    if "critical" in text:
        return "critical_delivery"
    if "high" in text:
        return "high_delivery"
    return "standard_delivery"


reporting_distribution_workflow = Workflow(
    name="ReportingDistributionWorkflow",
    steps=[
        Parallel(
            Step(name="compile_report", agent=report_compilation_agent),
            Step(name="generate_summary", agent=executive_summary_agent),
        ),
        Router(
            name="severity_router",
            selector=route_by_severity,
            choices=[
                Step(name="standard_delivery", team=distribution_team),
                Step(name="high_delivery", team=distribution_team),
                Step(name="critical_delivery", team=distribution_team),
            ],
        ),
    ],
)
