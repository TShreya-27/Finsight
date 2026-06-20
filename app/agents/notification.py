"""Slack/email notification agent."""

from app.agents._base import build_agent
from app.schemas.report import FinancialReport
from app.tools.finance_tools import format_anomaly_slack_block, format_report_html, post_slack_message, send_email_report, verify_slack_delivery

NOTIFICATION_INSTRUCTIONS_V1 = """
Format and send Slack anomaly alerts, verify delivery, and send HTML summary emails.
"""

notification_agent = build_agent(
    name="NotificationAgent",
    instructions=NOTIFICATION_INSTRUCTIONS_V1,
    response_model=FinancialReport,
    tools=[format_anomaly_slack_block, post_slack_message, verify_slack_delivery, format_report_html, send_email_report],
)
