"""Anomaly detection agent."""

from app.agents._base import build_agent
from app.evals.custom import AnomalyResponseQualityEval
from app.guardrails.custom import AnomalyThroughputGuardrail
from app.schemas.anomaly import AnomalyReport
from app.tools.finance_tools import classify_severity, compute_deviation_pct, fetch_historical_data, save_anomaly_to_db

ANOMALY_DETECTION_INSTRUCTIONS_V1 = """
Compare current values against historical values, classify severity, persist anomalies,
and return a ranked AnomalyReport.
"""

anomaly_detection_agent = build_agent(
    name="AnomalyDetectionAgent",
    instructions=ANOMALY_DETECTION_INSTRUCTIONS_V1,
    response_model=AnomalyReport,
    tools=[fetch_historical_data, compute_deviation_pct, classify_severity, save_anomaly_to_db],
    pre_hooks=[AnomalyThroughputGuardrail()],
    post_hooks=[AnomalyResponseQualityEval()],
)
