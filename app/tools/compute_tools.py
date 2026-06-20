"""Deterministic arithmetic helpers for financial metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComputedPLMetrics:
    gross_profit: float
    gross_margin_pct: float
    ebitda_margin_pct: float
    flags: list[str]


@dataclass(frozen=True)
class ComputedRatioMetrics:
    current_ratio: float
    debt_to_equity: float
    working_capital: float
    health_score: int
    flags: list[str]


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def compute_pl_metrics(pl: dict) -> dict:
    """Compute P&L percentages and return flags for narrative interpretation."""
    revenue = _safe_float(pl.get("revenue"))
    cogs = _safe_float(pl.get("cogs"))
    gross_profit = _safe_float(pl.get("gross_profit"))
    ebitda = _safe_float(pl.get("ebitda"))

    if gross_profit == 0.0 and (revenue != 0.0 or cogs != 0.0):
        gross_profit = revenue - cogs

    gross_margin_pct = (gross_profit / revenue * 100) if revenue else 0.0
    ebitda_margin_pct = (ebitda / revenue * 100) if revenue else 0.0

    flags: list[str] = []
    if revenue <= 0:
        flags.append("revenue_zero")
    if gross_margin_pct < 0:
        flags.append("gross_margin_negative")
    if revenue > 0 and not 10 <= gross_margin_pct <= 75:
        flags.append("gross_margin_out_of_range")
    if ebitda_margin_pct < 0:
        flags.append("ebitda_margin_negative")

    metrics = ComputedPLMetrics(
        gross_profit=round(gross_profit, 2),
        gross_margin_pct=round(gross_margin_pct, 2),
        ebitda_margin_pct=round(ebitda_margin_pct, 2),
        flags=flags,
    )
    return {
        "gross_profit": metrics.gross_profit,
        "gross_margin_pct": metrics.gross_margin_pct,
        "ebitda_margin_pct": metrics.ebitda_margin_pct,
        "flags": metrics.flags,
    }


def compute_financial_ratios(balance_sheet: dict) -> dict:
    """Compute balance-sheet ratios and a deterministic 0-100 health score."""
    current_assets = _safe_float(balance_sheet.get("current_assets"))
    current_liabilities = _safe_float(balance_sheet.get("current_liabilities"))
    total_liabilities = _safe_float(balance_sheet.get("total_liabilities"))
    equity = _safe_float(balance_sheet.get("equity"))

    current_ratio = current_assets / current_liabilities if current_liabilities else 0.0
    debt_to_equity = total_liabilities / equity if equity else 0.0
    working_capital = current_assets - current_liabilities

    score = 50
    if current_ratio >= 2:
        score += 20
    elif current_ratio >= 1:
        score += 10
    else:
        score -= 10

    if debt_to_equity <= 1:
        score += 20
    elif debt_to_equity <= 2:
        score += 10
    else:
        score -= 10

    if working_capital >= 0:
        score += 10
    else:
        score -= 10

    flags: list[str] = []
    if current_ratio < 1:
        flags.append("low_liquidity")
    if debt_to_equity > 2:
        flags.append("high_leverage")
    if working_capital < 0:
        flags.append("negative_working_capital")

    metrics = ComputedRatioMetrics(
        current_ratio=round(current_ratio, 3),
        debt_to_equity=round(debt_to_equity, 3),
        working_capital=round(working_capital, 2),
        health_score=int(_clamp(score, 0, 100)),
        flags=flags,
    )
    return {
        "current_ratio": metrics.current_ratio,
        "debt_to_equity": metrics.debt_to_equity,
        "working_capital": metrics.working_capital,
        "health_score": metrics.health_score,
        "flags": metrics.flags,
    }
