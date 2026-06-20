"""Shared enums used throughout the pipeline."""

from enum import Enum


class DocumentType(str, Enum):
    PL = "PL"
    BALANCE_SHEET = "BALANCE_SHEET"
    QUARTERLY_REPORT = "QUARTERLY_REPORT"


class AnomalySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
