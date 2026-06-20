"""Structured extraction output for PDF text."""

from datetime import date
from typing import List

from pydantic import BaseModel, Field, field_validator

from .common import DocumentType


class ExtractedLineItem(BaseModel):
    label: str = Field(..., description="Canonical metric label")
    raw_label: str = Field(..., description="Original label from the document")
    value: float = Field(..., description="Numeric value in INR")
    currency: str = Field("INR", description="Currency code")


class ExtractedDocument(BaseModel):
    company_name: str = Field(..., description="Legal entity name")
    document_type: DocumentType = Field(..., description="Financial document type")
    period_start: date = Field(..., description="Period start date")
    period_end: date = Field(..., description="Period end date")
    currency: str = Field("INR", description="Currency code")
    line_items: List[ExtractedLineItem] = Field(default_factory=list, description="Extracted line items")

    @field_validator("company_name")
    @classmethod
    def company_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("company_name cannot be empty")
        return value.strip()
