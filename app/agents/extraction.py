"""Document extraction agent."""

from app.agents._base import build_agent
from app.guardrails.custom import FinancialPIIGuardrail
from app.schemas.extracted_document import ExtractedDocument
from app.tools.finance_tools import detect_document_type, parse_indian_number, validate_mandatory_fields, map_label_to_canonical

EXTRACTION_AGENT_INSTRUCTIONS_V1 = """
Read a financial PDF and return a structured ExtractedDocument.
Detect the document type, normalize Indian numbers, map line labels to canonical names,
and never invent missing values.
"""

extraction_agent = build_agent(
    name="DocumentExtractionAgent",
    instructions=EXTRACTION_AGENT_INSTRUCTIONS_V1,
    response_model=ExtractedDocument,
    tools=[detect_document_type, parse_indian_number, validate_mandatory_fields, map_label_to_canonical],
    pre_hooks=[FinancialPIIGuardrail()],
)
