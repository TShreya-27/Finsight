"""Nested workflow that handles anomaly resolution with human-in-the-loop control."""

from agno.workflow import Workflow, Step, Loop
from agno.workflow.types import HumanReview

from app.agents.hitl import hitl_resolution_agent
from app.teams.anomaly import anomaly_investigation_team


def anomalies_resolved(outputs) -> bool:
    """Loop exits when no pending anomaly remains in the team output."""
    text = " ".join(str(o) for o in outputs)
    return "PENDING" not in text.upper()


anomaly_resolution_workflow = Workflow(
    name="AnomalyResolutionWorkflow",
    steps=[
        Loop(
            name="hitl_loop",
            steps=[
                Step(name="anomaly_investigation_team", team=anomaly_investigation_team),
                Step(
                    name="human_review",
                    agent=hitl_resolution_agent,
                    human_review=HumanReview(requires_confirmation=True, timeout=300),
                ),
            ],
            end_condition=anomalies_resolved,
            max_iterations=3,
        ),
    ],
)
