"""Outer workflow that orchestrates extraction, analysis, anomaly handling, and reporting."""

from agno.workflow import Workflow, Step, Condition, Parallel

from app.agents.compliance import compliance_agent
from app.agents.extraction import extraction_agent
from app.agents.notification import notification_agent
from app.teams.financial import financial_analysis_team
from app.workflows.anomaly_resolution import anomaly_resolution_workflow
from app.workflows.reporting_distribution import reporting_distribution_workflow


def critical_compliance_failure(step_input) -> bool:
    """Simple predicate used by the Condition node."""
    text = str(getattr(step_input, "input", "")).upper()
    return "CRITICAL" in text and "COMPLIANCE" in text


document_processing_workflow = Workflow(
    name="DocumentProcessingWorkflow",
    steps=[
        Step(name="extract", agent=extraction_agent),
        Parallel(
            Step(name="financial_analysis_team", team=financial_analysis_team),
            Step(name="compliance_precheck", agent=compliance_agent),
        ),
        Condition(
            name="critical_compliance_check",
            evaluator=critical_compliance_failure,
            steps=[Step(name="abort_and_notify", agent=notification_agent)],
            else_steps=[
                Step(name="anomaly_resolution", workflow=anomaly_resolution_workflow),
                Step(name="reporting_distribution", workflow=reporting_distribution_workflow),
            ],
        ),
    ],
)
