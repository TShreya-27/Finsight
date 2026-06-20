"""Custom evals used for quality scoring and audit logging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from agno.evals.accuracy import AccuracyEval
except Exception:
    class AccuracyEval:  # type: ignore
        pass


@dataclass
class EvalResult:
    score: float
    passed: bool
    reason: str


class ExtractionAccuracyEval(AccuracyEval):
    """Heuristic score for accounting identity consistency."""
    def evaluate_balance_sheet(self, output: dict[str, Any]) -> float:
        try:
            assets = float(output.get("total_assets", 0))
            liabilities = float(output.get("total_liabilities", 0))
            equity = float(output.get("equity", 0))
            rhs = liabilities + equity
            diff_pct = abs(assets - rhs) / max(abs(assets), 1) * 100
            return 1.0 if diff_pct <= 0.01 else max(0.0, 1.0 - diff_pct / 100)
        except Exception:
            return 0.0


class AnomalyResponseQualityEval(AccuracyEval):
    """Heuristic judge for CFO-actionable anomaly descriptions."""
    judge_instructions = """
    Score the anomaly description from 0 to 10 for CFO-actionability.
    10 = specific, numeric, and includes next action.
    0 = vague or missing numbers.
    """

    def score_text(self, text: str) -> EvalResult:
        text = text.lower()
        score = 0.0
        score += 0.4 if len(text) > 80 else 0.1
        score += 0.3 if any(k in text for k in ["revenue", "cash", "equity", "liquidity", "cfo"]) else 0.0
        score += 0.3 if any(k in text for k in ["recommend", "investigate", "risk", "variance"]) else 0.0
        return EvalResult(score=score, passed=score >= 0.7, reason="Heuristic CFO-actionability score")
