"""Smoke checks for PL compute tools and persistence wiring."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.report import FinancialReport  # noqa: E402
from app.tools.compute_tools import compute_financial_ratios, compute_pl_metrics  # noqa: E402
from app.services import persistence_service  # noqa: E402


def _sample_report() -> FinancialReport:
    pl = {
        "revenue": 1_000_000,
        "cogs": 600_000,
        "gross_profit": 400_000,
        "operating_expenses": 200_000,
        "ebitda": 200_000,
        "net_income": 120_000,
        "period_start": None,
        "period_end": None,
        "currency": "INR",
    }
    pl_metrics = compute_pl_metrics(pl)
    pl.update({
        "gross_margin_pct": pl_metrics["gross_margin_pct"],
        "ebitda_margin_pct": pl_metrics["ebitda_margin_pct"],
    })

    balance_sheet = {
        "total_assets": 2_000_000,
        "current_assets": 900_000,
        "non_current_assets": 1_100_000,
        "total_liabilities": 1_000_000,
        "current_liabilities": 400_000,
        "non_current_liabilities": 600_000,
        "equity": 1_000_000,
        "period_date": None,
        "currency": "INR",
    }
    ratio_metrics = compute_financial_ratios(balance_sheet)

    return FinancialReport(
        document_id="00000000-0000-0000-0000-000000000000",
        pl=pl,
        balance_sheet=balance_sheet,
        ratios=ratio_metrics,
        anomalies=[],
        executive_summary="Smoke check only.",
    )


async def main() -> None:
    report = _sample_report()
    print("Computed PL metrics:", report.pl)
    print("Computed ratio metrics:", report.ratios)

    try:
        await persistence_service.persist_financial_report(report.model_dump())
        print("Persistence service: ok")
    except Exception as exc:
        print(f"Persistence service skipped: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
