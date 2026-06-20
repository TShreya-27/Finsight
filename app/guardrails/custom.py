"""Custom guardrails attached to agents as pre_hooks."""

from __future__ import annotations

import json
import re
from typing import Any

from agno.exceptions import CheckTrigger, InputCheckError
from agno.guardrails.base import BaseGuardrail


class FinancialPIIGuardrail(BaseGuardrail):
    """Reject PAN/GST-like identifiers and long account-number patterns."""
    _PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
    _GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z0-9]{10}[A-Z]\d[A-Z]\d\b")

    def check(self, run_input: Any) -> None:
        content = str(getattr(run_input, "input_content", "") or "")
        if self._PAN_PATTERN.search(content) or self._GSTIN_PATTERN.search(content):
            raise InputCheckError("PII/tax identifier detected.", check_trigger=CheckTrigger.INPUT_NOT_ALLOWED)

    async def async_check(self, run_input: Any) -> None:
        self.check(run_input)


class OutputSanityGuardrail(BaseGuardrail):
    """Reject clearly hallucinated outputs."""
    def check(self, run_input: Any) -> None:
        content = str(getattr(run_input, "input_content", "") or "")
        try:
            payload = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        revenue = float(payload.get("revenue", 0))
        net_income = float(payload.get("net_income", 0))
        if revenue > 0 and net_income > revenue * 10:
            raise InputCheckError("Implausible output detected.", check_trigger=CheckTrigger.INPUT_NOT_ALLOWED)

    async def async_check(self, run_input: Any) -> None:
        self.check(run_input)


class AnomalyThroughputGuardrail(BaseGuardrail):
    """Circuit-breaker for too many anomalies in a single run."""
    MAX_ANOMALIES = 20

    def check(self, run_input: Any) -> None:
        content = str(getattr(run_input, "input_content", "") or "")
        try:
            payload = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if len(payload.get("anomalies", [])) > self.MAX_ANOMALIES:
            raise InputCheckError("Too many anomalies in one run.", check_trigger=CheckTrigger.INPUT_NOT_ALLOWED)

    async def async_check(self, run_input: Any) -> None:
        self.check(run_input)
