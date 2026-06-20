#!/usr/bin/env python3
"""
FinSight AI — Seed Data Script
=================================
Populates PostgreSQL with historical financial data and generates Q3 2024 PDF
financial statements (with planted anomalies) that your pipeline must detect.

Requirements:
    pip install psycopg2-binary reportlab

Usage:
    POSTGRES_URL=postgresql://user:pass@localhost:5432/finsight python scripts/seed_data.py

What this creates:
  • 5 companies
  • Q1 + Q2 2024 financial records (clean baseline, status=COMPLETE) in PostgreSQL
  • Q3 2024 financial documents (status=PENDING) — PDFs in sample_documents/
  • 5 anomalies pre-planted in Q3 data (one per company)

The Q3 PDFs are what your agents must process. Q1/Q2 data in the DB serves as
the historical baseline the Anomaly Detection Agent compares against.

Disclaimer: Some fields may be null or minimal. Supplement with faker or other
libraries as needed to satisfy your implementation.

Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("ERROR: psycopg2 not installed.  Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("NOTE: reportlab not installed — generating .txt files instead of PDFs.")
    print("      Install with: pip install reportlab\n")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "POSTGRES_URL", "postgresql://postgres:password@localhost:5432/finsight"
)
OUTPUT_DIR = Path("sample_documents")
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class PLData:
    revenue: int
    cogs: int
    gross_profit: int
    operating_expenses: int
    exceptional_items: int
    ebitda: int
    depreciation: int
    ebit: int
    interest: int
    pbt: int
    tax: int
    net_income: int
    opex_breakdown: Dict[str, int] = field(default_factory=dict)
    notes: str = ""


@dataclass
class BSData:
    # Assets
    cash: int
    trade_receivables: int
    inventories: int
    other_current_assets: int
    current_assets: int
    ppe_net: int
    intangibles: int
    other_non_current_assets: int
    non_current_assets: int
    total_assets_stated: int          # may differ from computed for anomaly
    # Liabilities
    trade_payables: int
    short_term_borrowings: int
    other_current_liabilities: int
    current_liabilities: int
    long_term_borrowings: int
    deferred_tax: int
    other_non_current_liabilities: int
    non_current_liabilities: int
    total_liabilities: int
    # Equity
    share_capital: int
    retained_earnings: int
    other_reserves: int
    equity: int
    notes: str = ""


@dataclass
class PeriodData:
    period_start: date
    period_end: date
    pl: PLData
    bs: BSData


@dataclass
class CompanyRecord:
    id: str
    name: str
    erp_code: str
    industry: str
    address: str
    cin: str          # Corporate Identification Number (Indian)
    periods: Dict[str, PeriodData] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Financial data — all values in Indian Rupees (INR)
# ---------------------------------------------------------------------------

def _pl(
    revenue, cogs, opex, exceptional=0, da=0, interest=0, tax=0,
    opex_breakdown=None, notes=""
):
    gross_profit = revenue - cogs
    ebitda = gross_profit - opex - exceptional
    ebit = ebitda - da
    pbt = ebit - interest
    return PLData(
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        operating_expenses=opex,
        exceptional_items=exceptional,
        ebitda=ebitda,
        depreciation=da,
        ebit=ebit,
        interest=interest,
        pbt=pbt,
        tax=tax,
        net_income=pbt - tax,
        opex_breakdown=opex_breakdown or {},
        notes=notes,
    )


def _bs(
    cash, recv, inv, other_ca,
    ppe, intang, other_nca,
    payables, st_borrow, other_cl,
    lt_borrow, def_tax, other_ncl,
    share_cap, retained, other_res,
    stated_ta_override=None,
    notes="",
):
    ca = cash + recv + inv + other_ca
    nca = ppe + intang + other_nca
    ta_computed = ca + nca
    ta_stated = stated_ta_override if stated_ta_override is not None else ta_computed

    cl = payables + st_borrow + other_cl
    ncl = lt_borrow + def_tax + other_ncl
    tl = cl + ncl
    eq = share_cap + retained + other_res

    return BSData(
        cash=cash, trade_receivables=recv, inventories=inv,
        other_current_assets=other_ca, current_assets=ca,
        ppe_net=ppe, intangibles=intang, other_non_current_assets=other_nca,
        non_current_assets=nca, total_assets_stated=ta_stated,
        trade_payables=payables, short_term_borrowings=st_borrow,
        other_current_liabilities=other_cl, current_liabilities=cl,
        long_term_borrowings=lt_borrow, deferred_tax=def_tax,
        other_non_current_liabilities=other_ncl, non_current_liabilities=ncl,
        total_liabilities=tl,
        share_capital=share_cap, retained_earnings=retained,
        other_reserves=other_res, equity=eq,
        notes=notes,
    )


# ── Company 1: Fyntwin Retail Solutions Ltd ─────────────────────────────────
# Anomaly (Q3): Revenue fell 47% quarter-over-quarter (58.5M → 31M)

C1_Q1_PL = _pl(
    revenue=52_000_000, cogs=31_200_000, opex=13_000_000,
    da=1_500_000, interest=800_000, tax=1_650_000,
    opex_breakdown={
        "Selling & Distribution": 5_200_000,
        "Administrative": 4_940_000,
        "Employee Benefits": 2_860_000,
    },
)
C1_Q1_BS = _bs(
    cash=12_300_000, recv=10_400_000, inv=45_200_000, other_ca=14_100_000,
    ppe=33_750_000, intang=6_750_000, other_nca=4_500_000,
    payables=22_950_000, st_borrow=15_300_000, other_cl=12_750_000,
    lt_borrow=30_000_000, def_tax=6_000_000, other_ncl=4_000_000,
    share_cap=11_000_000, retained=20_000_000, other_res=5_000_000,
)

C1_Q2_PL = _pl(
    revenue=58_500_000, cogs=35_100_000, opex=14_625_000,
    da=1_500_000, interest=800_000, tax=1_942_500,
    opex_breakdown={
        "Selling & Distribution": 5_850_000,
        "Administrative": 5_558_000,
        "Employee Benefits": 3_217_000,
    },
)
C1_Q2_BS = _bs(
    cash=14_420_000, recv=12_040_000, inv=49_680_000, other_ca=9_860_000,
    ppe=32_625_000, intang=6_525_000, other_nca=4_350_000,
    payables=23_850_000, st_borrow=15_900_000, other_cl=13_250_000,
    lt_borrow=30_000_000, def_tax=6_000_000, other_ncl=4_000_000,
    share_cap=11_000_000, retained=21_000_000, other_res=4_500_000,
)

C1_Q3_PL = _pl(
    revenue=31_000_000, cogs=21_700_000, opex=15_500_000,
    da=1_500_000, interest=800_000, tax=0,
    opex_breakdown={
        "Selling & Distribution": 5_500_000,
        "Administrative": 6_200_000,
        "Employee Benefits": 3_800_000,
    },
    notes=(
        "NOTICE: Revenue declined significantly in Q3 2024 compared to Q2 2024. "
        "The company experienced a 47% quarter-on-quarter decline in revenue from "
        "operations. Operating expenses remained fixed, resulting in negative EBITDA."
    ),
)
C1_Q3_BS = _bs(
    cash=10_350_000, recv=13_800_000, inv=37_950_000, other_ca=6_900_000,
    ppe=31_500_000, intang=6_300_000, other_nca=4_200_000,
    payables=26_100_000, st_borrow=17_400_000, other_cl=14_500_000,
    lt_borrow=30_000_000, def_tax=6_000_000, other_ncl=4_000_000,
    share_cap=11_000_000, retained=7_000_000, other_res=-5_000_000,
)


# ── Company 2: Meridian Manufacturing Pvt Ltd ───────────────────────────────
# Anomaly (Q3): Total Assets stated as 374,900,000 but sub-items sum to 374,000,000
# Balance sheet mismatch of ₹9,00,000 (9 Lakhs)

C2_Q1_PL = _pl(
    revenue=125_000_000, cogs=87_500_000, opex=20_000_000,
    da=4_500_000, interest=2_500_000, tax=3_150_000,
    opex_breakdown={
        "Raw Material Processing": 8_000_000,
        "Factory Overhead": 6_500_000,
        "Administrative": 3_500_000,
        "Employee Benefits": 2_000_000,
    },
)
C2_Q1_BS = _bs(
    cash=22_000_000, recv=66_000_000, inv=88_000_000, other_ca=44_000_000,
    ppe=101_250_000, intang=20_250_000, other_nca=13_500_000,
    payables=54_000_000, st_borrow=36_000_000, other_cl=30_000_000,
    lt_borrow=76_500_000, def_tax=15_300_000, other_ncl=10_200_000,
    share_cap=46_550_000, retained=71_200_000, other_res=15_250_000,
)

C2_Q2_PL = _pl(
    revenue=131_000_000, cogs=91_700_000, opex=20_960_000,
    da=4_500_000, interest=2_500_000, tax=3_402_000,
    opex_breakdown={
        "Raw Material Processing": 8_384_000,
        "Factory Overhead": 6_815_000,
        "Administrative": 3_668_000,
        "Employee Benefits": 2_093_000,
    },
)
C2_Q2_BS = _bs(
    cash=23_200_000, recv=69_600_000, inv=92_800_000, other_ca=46_400_000,
    ppe=98_250_000, intang=19_650_000, other_nca=13_100_000,
    payables=55_350_000, st_borrow=36_900_000, other_cl=30_750_000,
    lt_borrow=76_500_000, def_tax=15_300_000, other_ncl=10_200_000,
    share_cap=46_550_000, retained=77_950_000, other_res=13_500_000,
)

C2_Q3_PL = _pl(
    revenue=138_000_000, cogs=96_600_000, opex=22_080_000,
    da=4_500_000, interest=2_500_000, tax=3_696_000,
    opex_breakdown={
        "Raw Material Processing": 8_832_000,
        "Factory Overhead": 7_176_000,
        "Administrative": 3_865_000,
        "Employee Benefits": 2_207_000,
    },
)
C2_Q3_BS = _bs(
    # Sub-items sum correctly to 374,000,000
    cash=24_800_000, recv=74_400_000, inv=99_200_000, other_ca=49_600_000,
    ppe=94_500_000, intang=18_900_000, other_nca=12_600_000,
    payables=59_400_000, st_borrow=39_600_000, other_cl=33_000_000,
    lt_borrow=76_500_000, def_tax=15_300_000, other_ncl=10_200_000,
    share_cap=46_550_000, retained=84_950_000, other_res=8_500_000,
    # Override stated Total Assets to create the mismatch anomaly
    stated_ta_override=374_900_000,
    notes=(
        "AUDITOR NOTE: Total Assets as per trial balance: ₹37,49,00,000. "
        "Total Assets per schedule: ₹37,40,00,000. Difference of ₹9,00,000 "
        "is under review. Possible posting error in Fixed Assets register."
    ),
)


# ── Company 3: Apex Financial Services Ltd ──────────────────────────────────
# Anomaly (Q3): Operating expenses = 180% of revenue (normally ~30%)
# Results in negative equity

C3_Q1_PL = _pl(
    revenue=32_000_000, cogs=6_400_000, opex=9_600_000,
    da=1_800_000, interest=1_200_000, tax=3_900_000,
    opex_breakdown={
        "Employee Compensation": 4_480_000,
        "Administrative": 3_200_000,
        "Technology & Infrastructure": 1_920_000,
    },
)
C3_Q1_BS = _bs(
    cash=9_000_000, recv=11_250_000, inv=0, other_ca=6_750_000,
    ppe=21_000_000, intang=4_200_000, other_nca=2_800_000,
    payables=9_900_000, st_borrow=6_600_000, other_cl=5_500_000,
    lt_borrow=13_500_000, def_tax=2_700_000, other_ncl=1_800_000,
    share_cap=10_000_000, retained=19_000_000, other_res=4_000_000,
)

C3_Q2_PL = _pl(
    revenue=35_000_000, cogs=7_000_000, opex=10_500_000,
    da=1_800_000, interest=1_200_000, tax=4_350_000,
    opex_breakdown={
        "Employee Compensation": 4_900_000,
        "Administrative": 3_500_000,
        "Technology & Infrastructure": 2_100_000,
    },
)
C3_Q2_BS = _bs(
    cash=10_400_000, recv=13_000_000, inv=0, other_ca=7_800_000,
    ppe=20_400_000, intang=4_050_000, other_nca=2_700_000,
    payables=11_250_000, st_borrow=7_500_000, other_cl=6_250_000,
    lt_borrow=13_500_000, def_tax=2_700_000, other_ncl=1_800_000,
    share_cap=10_000_000, retained=25_850_000, other_res=0,
)

C3_Q3_PL = _pl(
    revenue=37_200_000, cogs=7_440_000, opex=66_960_000,   # 180% of revenue
    da=1_800_000, interest=1_200_000, tax=0,
    opex_breakdown={
        "Employee Compensation": 18_600_000,
        "Administrative Expenses": 25_000_000,
        "Legal & Compliance Fees": 11_960_000,
        "Technology & Infrastructure": 11_400_000,
    },
    notes=(
        "MANAGEMENT NOTE: Operating expenses for Q3 2024 include one-time charges "
        "related to regulatory compliance requirements and restructuring costs. "
        "Legal fees include settlement provisions of ₹1,19,60,000. "
        "Administrative expenses include consultant fees for system overhaul of ₹2,50,00,000."
    ),
)
C3_Q3_BS = _bs(
    cash=3_900_000, recv=19_500_000, inv=0, other_ca=15_600_000,
    ppe=18_600_000, intang=3_720_000, other_nca=2_480_000,
    payables=17_100_000, st_borrow=11_400_000, other_cl=9_500_000,
    lt_borrow=22_500_000, def_tax=4_500_000, other_ncl=3_000_000,
    share_cap=10_000_000, retained=0, other_res=-14_200_000,   # negative retained: accumulated loss
)


# ── Company 4: BlueStar Technologies Pvt Ltd ────────────────────────────────
# Anomaly (Q3): Exceptional write-offs of ₹4.5 Cr (normal: ~₹20 Lakhs)

C4_Q1_PL = _pl(
    revenue=81_000_000, cogs=36_450_000, opex=20_250_000, exceptional=2_000_000,
    da=3_500_000, interest=1_500_000, tax=5_190_000,
    opex_breakdown={
        "Engineering & Development": 10_530_000,
        "Sales & Marketing": 6_075_000,
        "General & Administrative": 3_645_000,
    },
)
C4_Q1_BS = _bs(
    cash=23_750_000, recv=33_250_000, inv=0, other_ca=38_000_000,
    ppe=46_500_000, intang=9_300_000, other_nca=6_200_000,
    payables=21_600_000, st_borrow=14_400_000, other_cl=12_000_000,
    lt_borrow=31_500_000, def_tax=6_300_000, other_ncl=4_200_000,
    share_cap=20_000_000, retained=42_500_000, other_res=4_500_000,
)

C4_Q2_PL = _pl(
    revenue=86_000_000, cogs=38_700_000, opex=21_500_000, exceptional=2_000_000,
    da=3_500_000, interest=1_500_000, tax=5_640_000,
    opex_breakdown={
        "Engineering & Development": 11_180_000,
        "Sales & Marketing": 6_450_000,
        "General & Administrative": 3_870_000,
    },
)
C4_Q2_BS = _bs(
    cash=25_500_000, recv=35_700_000, inv=0, other_ca=40_800_000,
    ppe=45_375_000, intang=9_075_000, other_nca=6_050_000,
    payables=23_400_000, st_borrow=15_600_000, other_cl=13_000_000,
    lt_borrow=31_500_000, def_tax=6_300_000, other_ncl=4_200_000,
    share_cap=20_000_000, retained=52_800_000, other_res=0,
)

C4_Q3_PL = _pl(
    revenue=83_000_000, cogs=37_350_000, opex=20_750_000,
    exceptional=45_000_000,       # ← ANOMALY: 2150% spike vs normal ₹20L
    da=3_500_000, interest=1_500_000, tax=0,
    opex_breakdown={
        "Engineering & Development": 10_790_000,
        "Sales & Marketing": 6_225_000,
        "General & Administrative": 3_735_000,
    },
    notes=(
        "EXCEPTIONAL ITEMS (₹4,50,00,000):\n"
        "1. Write-off of investment in BlueStar SEA Pte. Ltd. (wholly owned subsidiary): "
        "₹3,50,00,000 — subsidiary wound up due to market exit.\n"
        "2. Settlement of employment dispute — Class action by ex-employees: ₹1,00,00,000.\n"
        "These are non-recurring items and should be excluded from normalised EBITDA."
    ),
)
C4_Q3_BS = _bs(
    cash=22_000_000, recv=30_800_000, inv=0, other_ca=35_200_000,
    ppe=44_250_000, intang=8_850_000, other_nca=5_900_000,
    payables=24_750_000, st_borrow=16_500_000, other_cl=13_750_000,
    lt_borrow=31_500_000, def_tax=6_300_000, other_ncl=4_200_000,
    share_cap=20_000_000, retained=25_000_000, other_res=5_000_000,
)


# ── Company 5: IndoAgro Commodities Ltd ─────────────────────────────────────
# Anomaly (Q3): COGS = 0 (data entry error — commodity costs missing)

C5_Q1_PL = _pl(
    revenue=68_000_000, cogs=57_800_000, opex=5_100_000,
    da=1_200_000, interest=800_000, tax=930_000,
    opex_breakdown={
        "Logistics & Warehousing": 2_040_000,
        "Administrative": 1_700_000,
        "Employee Costs": 1_360_000,
    },
)
C5_Q1_BS = _bs(
    cash=5_040_000, recv=6_300_000, inv=25_200_000, other_ca=5_460_000,
    ppe=21_000_000, intang=4_200_000, other_nca=2_800_000,
    payables=9_000_000, st_borrow=6_000_000, other_cl=5_000_000,
    lt_borrow=13_500_000, def_tax=2_700_000, other_ncl=1_800_000,
    share_cap=15_000_000, retained=14_000_000, other_res=3_000_000,
)

C5_Q2_PL = _pl(
    revenue=72_000_000, cogs=61_200_000, opex=5_400_000,
    da=1_200_000, interest=800_000, tax=1_020_000,
    opex_breakdown={
        "Logistics & Warehousing": 2_160_000,
        "Administrative": 1_800_000,
        "Employee Costs": 1_440_000,
    },
)
C5_Q2_BS = _bs(
    cash=5_760_000, recv=7_200_000, inv=28_800_000, other_ca=6_240_000,
    ppe=20_250_000, intang=4_050_000, other_nca=2_700_000,
    payables=9_900_000, st_borrow=6_600_000, other_cl=5_500_000,
    lt_borrow=13_500_000, def_tax=2_700_000, other_ncl=1_800_000,
    share_cap=15_000_000, retained=15_800_000, other_res=4_200_000,
)

C5_Q3_PL = _pl(
    revenue=75_000_000, cogs=0,             # ← ANOMALY: COGS missing (data error)
    opex=5_625_000,
    da=1_200_000, interest=800_000, tax=20_212_500,
    opex_breakdown={
        "Logistics & Warehousing": 2_250_000,
        "Administrative": 1_875_000,
        "Employee Costs": 1_500_000,
    },
    notes=(
        "DATA NOTE: Cost of Goods Sold for Q3 2024 shows NIL. "
        "This may be a data extraction error from the ERP system. "
        "Q1 2024 COGS was 85.0% of revenue; Q2 2024 COGS was 85.0% of revenue. "
        "Expected Q3 COGS at 85% would be approximately ₹6,37,50,000."
    ),
)
C5_Q3_BS = _bs(
    cash=6_000_000, recv=7_500_000, inv=30_000_000, other_ca=6_500_000,
    ppe=19_500_000, intang=3_900_000, other_nca=2_600_000,
    payables=10_350_000, st_borrow=6_900_000, other_cl=5_750_000,
    lt_borrow=13_500_000, def_tax=2_700_000, other_ncl=1_800_000,
    share_cap=15_000_000, retained=16_000_000, other_res=4_000_000,
)


# ---------------------------------------------------------------------------
# Company registry
# ---------------------------------------------------------------------------
COMPANIES: List[CompanyRecord] = [
    CompanyRecord(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "FRSL-001")),
        name="Fyntwin Retail Solutions Ltd",
        erp_code="FRSL-001",
        industry="Retail",
        address="Plot 14, Sector 18, Noida, Uttar Pradesh - 201301",
        cin="U52100UP2016PLC082341",
        periods={
            "Q1": PeriodData(date(2024, 1, 1), date(2024, 3, 31), C1_Q1_PL, C1_Q1_BS),
            "Q2": PeriodData(date(2024, 4, 1), date(2024, 6, 30), C1_Q2_PL, C1_Q2_BS),
            "Q3": PeriodData(date(2024, 7, 1), date(2024, 9, 30), C1_Q3_PL, C1_Q3_BS),
        },
    ),
    CompanyRecord(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "MMPL-002")),
        name="Meridian Manufacturing Pvt Ltd",
        erp_code="MMPL-002",
        industry="Manufacturing",
        address="Survey No. 47/B, MIDC Industrial Area, Pune, Maharashtra - 411019",
        cin="U27100MH2010PTC203456",
        periods={
            "Q1": PeriodData(date(2024, 1, 1), date(2024, 3, 31), C2_Q1_PL, C2_Q1_BS),
            "Q2": PeriodData(date(2024, 4, 1), date(2024, 6, 30), C2_Q2_PL, C2_Q2_BS),
            "Q3": PeriodData(date(2024, 7, 1), date(2024, 9, 30), C2_Q3_PL, C2_Q3_BS),
        },
    ),
    CompanyRecord(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "AFSL-003")),
        name="Apex Financial Services Ltd",
        erp_code="AFSL-003",
        industry="Financial Services",
        address="Level 8, Prestige Trade Tower, MG Road, Bengaluru, Karnataka - 560001",
        cin="U65100KA2012PLC063210",
        periods={
            "Q1": PeriodData(date(2024, 1, 1), date(2024, 3, 31), C3_Q1_PL, C3_Q1_BS),
            "Q2": PeriodData(date(2024, 4, 1), date(2024, 6, 30), C3_Q2_PL, C3_Q2_BS),
            "Q3": PeriodData(date(2024, 7, 1), date(2024, 9, 30), C3_Q3_PL, C3_Q3_BS),
        },
    ),
    CompanyRecord(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "BTPL-004")),
        name="BlueStar Technologies Pvt Ltd",
        erp_code="BTPL-004",
        industry="Technology",
        address="Tower C, 6th Floor, Cyber City, DLF Phase 2, Gurugram, Haryana - 122002",
        cin="U72200HR2015PTC058743",
        periods={
            "Q1": PeriodData(date(2024, 1, 1), date(2024, 3, 31), C4_Q1_PL, C4_Q1_BS),
            "Q2": PeriodData(date(2024, 4, 1), date(2024, 6, 30), C4_Q2_PL, C4_Q2_BS),
            "Q3": PeriodData(date(2024, 7, 1), date(2024, 9, 30), C4_Q3_PL, C4_Q3_BS),
        },
    ),
    CompanyRecord(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, "IACL-005")),
        name="IndoAgro Commodities Ltd",
        erp_code="IACL-005",
        industry="Agricultural Commodities",
        address="Grain Market Complex, Sector 26, Chandigarh - 160019",
        cin="U01400CH2008PLC034892",
        periods={
            "Q1": PeriodData(date(2024, 1, 1), date(2024, 3, 31), C5_Q1_PL, C5_Q1_BS),
            "Q2": PeriodData(date(2024, 4, 1), date(2024, 6, 30), C5_Q2_PL, C5_Q2_BS),
            "Q3": PeriodData(date(2024, 7, 1), date(2024, 9, 30), C5_Q3_PL, C5_Q3_BS),
        },
    ),
]

ANOMALY_DESCRIPTIONS = {
    "FRSL-001": (
        "Revenue declined 47.0% QoQ (Q2: ₹5,85,00,000 → Q3: ₹3,10,00,000). "
        "Below 3-quarter average of ₹4,75,00,000 by 34.7%. EBITDA turned negative "
        "(-₹62,00,000). Operating expenses unchanged despite revenue collapse."
    ),
    "MMPL-002": (
        "Balance Sheet integrity failure: Stated Total Assets ₹37,49,00,000 does not "
        "equal Total Liabilities (₹23,40,00,000) + Total Equity (₹14,00,00,000) = "
        "₹37,40,00,000. Unreconciled difference: ₹9,00,000 (0.24%)."
    ),
    "AFSL-003": (
        "Operating Expenses = ₹6,69,60,000 (180% of revenue ₹3,72,00,000). "
        "Normal range: 28–33% of revenue. Current ratio: 1.03 (critically low). "
        "Equity turned negative: -₹42,00,000."
    ),
    "BTPL-004": (
        "Exceptional Items = ₹4,50,00,000 vs trailing 2-quarter average of ₹20,00,000 "
        "(2150% above normal). Investment write-off and legal settlement resulted in "
        "net loss of ₹2,51,00,000 vs Q2 profit of ₹1,31,60,000."
    ),
    "IACL-005": (
        "Cost of Goods Sold reported as NIL (₹0). Historical COGS: Q1 = 85.0% of revenue, "
        "Q2 = 85.0% of revenue. Gross margin = 100% (impossible for commodity trading). "
        "Expected COGS at 85%: ₹6,37,50,000."
    ),
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt(amount: int) -> str:
    """Format a rupee amount with Indian number system (comma every 2 digits after first 3)."""
    if amount < 0:
        return f"({fmt(-amount)})"
    s = str(abs(amount))
    if len(s) <= 3:
        return s
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + "," + result if len(s) > 2 else s + "," + result
        s = s[:-2] if len(s) > 2 else ""
    return result


def _period_label(period_start: date, period_end: date) -> str:
    months = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    }
    return (
        f"{months[period_start.month]} {period_start.day}, {period_start.year} "
        f"to {months[period_end.month]} {period_end.day}, {period_end.year}"
    )


def _quarter_label(period_start: date) -> str:
    q = (period_start.month - 1) // 3 + 1
    return f"Q{q} FY{period_start.year}-{str(period_start.year + 1)[2:]}"


# ---------------------------------------------------------------------------
# Text content generators
# ---------------------------------------------------------------------------

def build_pl_text(company: CompanyRecord, period_key: str) -> str:
    p = company.periods[period_key]
    pl = p.pl
    period_label = _period_label(p.period_start, p.period_end)
    quarter = _quarter_label(p.period_start)
    W = 80
    sep = "=" * W

    lines = [
        sep,
        company.name.center(W),
        "STATEMENT OF PROFIT & LOSS".center(W),
        f"For the Quarter: {period_label}".center(W),
        f"({quarter})".center(W),
        "(All amounts in Indian Rupees)".center(W),
        f"CIN: {company.cin}".center(W),
        sep,
        "",
        f"{'INCOME':<45} {'Amount (₹)':>20}",
        "-" * W,
        f"{'Revenue from Operations':<45} {fmt(pl.revenue):>20}",
        f"{'Other Income':<45} {'—':>20}",
        f"{'TOTAL INCOME (A)':<45} {fmt(pl.revenue):>20}",
        "",
        f"{'EXPENSES':<45} {'Amount (₹)':>20}",
        "-" * W,
        f"{'Cost of Goods Sold (COGS)':<45} {fmt(pl.cogs):>20}",
        "-" * W,
        f"{'GROSS PROFIT (A - COGS)':<45} {fmt(pl.gross_profit):>20}",
        f"{'Gross Margin':<45} {f'{pl.gross_profit/pl.revenue*100:.2f}%' if pl.revenue else 'N/A':>20}",
        "",
        "OPERATING EXPENSES BREAKDOWN:",
    ]

    for label, amount in pl.opex_breakdown.items():
        lines.append(f"  {label:<43} {fmt(amount):>20}")

    lines += [
        f"{'TOTAL OPERATING EXPENSES':<45} {fmt(pl.operating_expenses):>20}",
        "",
        f"{'EARNINGS BEFORE INTEREST, TAX, D&A (EBITDA)':<45} {fmt(pl.ebitda):>20}",
    ]

    if pl.exceptional_items:
        lines.append(f"{'Less: Exceptional Items / Write-offs':<45} {fmt(pl.exceptional_items):>20}")
        lines.append(f"{'EBITDA (After Exceptional Items)':<45} {fmt(pl.ebitda):>20}")

    lines += [
        f"{'Less: Depreciation & Amortisation (D&A)':<45} {fmt(pl.depreciation):>20}",
        f"{'EARNINGS BEFORE INTEREST & TAX (EBIT)':<45} {fmt(pl.ebit):>20}",
        f"{'Less: Finance Costs (Interest)':<45} {fmt(pl.interest):>20}",
        f"{'PROFIT / (LOSS) BEFORE TAX (PBT)':<45} {fmt(pl.pbt):>20}",
        f"{'Less: Income Tax Expense':<45} {fmt(pl.tax):>20}",
        "-" * W,
        f"{'NET PROFIT / (LOSS) AFTER TAX':<45} {fmt(pl.net_income):>20}",
        "=" * W,
    ]

    if pl.notes:
        lines += ["", "NOTES TO ACCOUNTS:", "-" * W]
        for line in textwrap.wrap(pl.notes, width=W - 2):
            lines.append("  " + line)
        lines.append("")

    lines += [
        "",
        "For and on behalf of the Board of Directors",
        f"{company.name}",
        "",
        "Authorised Signatory                          Chief Financial Officer",
        f"Date: {p.period_end.strftime('%B %d, %Y')}",
        sep,
    ]

    return "\n".join(lines)


def build_bs_text(company: CompanyRecord, period_key: str) -> str:
    p = company.periods[period_key]
    bs = p.bs
    period_label = p.period_end.strftime("%B %d, %Y")
    quarter = _quarter_label(p.period_start)
    W = 80
    sep = "=" * W

    computed_ta = bs.current_assets + bs.non_current_assets
    total_le = bs.total_liabilities + bs.equity

    lines = [
        sep,
        company.name.center(W),
        "BALANCE SHEET".center(W),
        f"As at {period_label}".center(W),
        f"({quarter})".center(W),
        "(All amounts in Indian Rupees)".center(W),
        f"CIN: {company.cin}".center(W),
        sep,
        "",
        "ASSETS".center(W),
        "-" * W,
        "CURRENT ASSETS",
        f"  {'Cash & Cash Equivalents':<43} {fmt(bs.cash):>20}",
        f"  {'Trade Receivables (Net)':<43} {fmt(bs.trade_receivables):>20}",
    ]

    if bs.inventories:
        lines.append(f"  {'Inventories':<43} {fmt(bs.inventories):>20}")

    lines += [
        f"  {'Other Current Assets':<43} {fmt(bs.other_current_assets):>20}",
        f"{'TOTAL CURRENT ASSETS':<45} {fmt(bs.current_assets):>20}",
        "",
        "NON-CURRENT ASSETS",
        f"  {'Property, Plant & Equipment (Net)':<43} {fmt(bs.ppe_net):>20}",
        f"  {'Intangible Assets & Goodwill':<43} {fmt(bs.intangibles):>20}",
        f"  {'Other Non-Current Assets':<43} {fmt(bs.other_non_current_assets):>20}",
        f"{'TOTAL NON-CURRENT ASSETS':<45} {fmt(bs.non_current_assets):>20}",
        "",
        "-" * W,
        f"{'TOTAL ASSETS':<45} {fmt(bs.total_assets_stated):>20}",
        "=" * W,
        "",
        "EQUITY & LIABILITIES".center(W),
        "-" * W,
        "CURRENT LIABILITIES",
        f"  {'Trade Payables':<43} {fmt(bs.trade_payables):>20}",
        f"  {'Short-Term Borrowings':<43} {fmt(bs.short_term_borrowings):>20}",
        f"  {'Other Current Liabilities & Provisions':<43} {fmt(bs.other_current_liabilities):>20}",
        f"{'TOTAL CURRENT LIABILITIES':<45} {fmt(bs.current_liabilities):>20}",
        "",
        "NON-CURRENT LIABILITIES",
        f"  {'Long-Term Borrowings':<43} {fmt(bs.long_term_borrowings):>20}",
        f"  {'Deferred Tax Liabilities (Net)':<43} {fmt(bs.deferred_tax):>20}",
        f"  {'Other Non-Current Liabilities':<43} {fmt(bs.other_non_current_liabilities):>20}",
        f"{'TOTAL NON-CURRENT LIABILITIES':<45} {fmt(bs.non_current_liabilities):>20}",
        "",
        f"{'TOTAL LIABILITIES':<45} {fmt(bs.total_liabilities):>20}",
        "",
        "EQUITY",
        f"  {'Share Capital':<43} {fmt(bs.share_capital):>20}",
        f"  {'Retained Earnings / (Accumulated Loss)':<43} {fmt(bs.retained_earnings):>20}",
        f"  {'Other Reserves & Surplus':<43} {fmt(bs.other_reserves):>20}",
        f"{'TOTAL EQUITY':<45} {fmt(bs.equity):>20}",
        "",
        "-" * W,
        f"{'TOTAL LIABILITIES & EQUITY':<45} {fmt(total_le):>20}",
        "=" * W,
    ]

    if bs.total_assets_stated != computed_ta or bs.total_assets_stated != total_le:
        lines += [
            "",
            "RECONCILIATION NOTE:",
            f"  Computed Total Assets (Current + Non-Current) : {fmt(computed_ta)}",
            f"  Stated Total Assets                           : {fmt(bs.total_assets_stated)}",
            f"  Total Liabilities + Equity                   : {fmt(total_le)}",
        ]

    if bs.notes:
        lines += ["", "NOTES TO ACCOUNTS:", "-" * W]
        for line in textwrap.wrap(bs.notes, width=W - 2):
            lines.append("  " + line)
        lines.append("")

    lines += [
        "",
        "For and on behalf of the Board of Directors",
        f"{company.name}",
        "",
        "Authorised Signatory                          Chief Financial Officer",
        f"Date: {p.period_end.strftime('%B %d, %Y')}",
        "=" * W,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF generation (reportlab) with TXT fallback
# ---------------------------------------------------------------------------

def save_document(text_content: str, filepath: Path) -> str:
    """Save as PDF if reportlab available, else as .txt. Returns saved path."""
    if REPORTLAB_AVAILABLE:
        pdf_path = filepath.with_suffix(".pdf")
        _save_as_pdf(text_content, pdf_path)
        return str(pdf_path)
    else:
        txt_path = filepath.with_suffix(".txt")
        txt_path.write_text(text_content, encoding="utf-8")
        return str(txt_path)


def _save_as_pdf(text_content: str, pdf_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    mono_style = ParagraphStyle(
        "Mono",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=11,
        spaceAfter=0,
    )

    story = []
    for line in text_content.split("\n"):
        safe_line = (
            line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )
        story.append(Paragraph(safe_line if safe_line.strip() else "&nbsp;", mono_style))

    doc.build(story)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    erp_code    TEXT UNIQUE NOT NULL,
    industry    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(id),
    document_type TEXT NOT NULL,
    period_start  DATE NOT NULL,
    period_end    DATE NOT NULL,
    raw_text      TEXT,
    file_hash     TEXT UNIQUE,
    ingested_at   TIMESTAMPTZ DEFAULT NOW(),
    status        TEXT DEFAULT 'PENDING'
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  TEXT NOT NULL,
    agent_name       TEXT NOT NULL,
    session_data     JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_contexts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID REFERENCES agent_sessions(id),
    step_name        TEXT NOT NULL,
    input_snapshot   JSONB,
    output_snapshot  JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_states (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    temporal_workflow_id  TEXT UNIQUE NOT NULL,
    agno_workflow_name    TEXT NOT NULL,
    status                TEXT NOT NULL,
    state_data            JSONB,
    started_at            TIMESTAMPTZ DEFAULT NOW(),
    completed_at          TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS anomalies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES financial_documents(id),
    metric_name     TEXT NOT NULL,
    expected_range  JSONB,
    actual_value    NUMERIC,
    deviation_pct   NUMERIC,
    severity        TEXT NOT NULL,
    description     TEXT,
    status          TEXT DEFAULT 'PENDING',
    resolution_note TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hitl_approvals (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anomaly_id            UUID REFERENCES anomalies(id),
    temporal_workflow_id  TEXT NOT NULL,
    slack_message_ts      TEXT,
    decision              TEXT,
    reviewer_slack_id     TEXT,
    reviewed_at           TIMESTAMPTZ,
    notes                 TEXT
);

CREATE TABLE IF NOT EXISTS financial_reports (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID REFERENCES financial_documents(id),
    report_data       JSONB NOT NULL,
    executive_summary TEXT,
    generated_at      TIMESTAMPTZ DEFAULT NOW(),
    delivered_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  TEXT,
    agent_name       TEXT NOT NULL,
    action           TEXT NOT NULL,
    input_hash       TEXT,
    output_hash      TEXT,
    eval_score       NUMERIC,
    duration_ms      INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pl_statements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID REFERENCES financial_documents(id),
    revenue             NUMERIC,
    cogs                NUMERIC,
    gross_profit        NUMERIC,
    operating_expenses  NUMERIC,
    ebitda              NUMERIC,
    net_income          NUMERIC,
    period_start        DATE,
    period_end          DATE,
    currency            TEXT DEFAULT 'INR'
);

CREATE TABLE IF NOT EXISTS balance_sheets (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id             UUID REFERENCES financial_documents(id),
    total_assets            NUMERIC,
    current_assets          NUMERIC,
    non_current_assets      NUMERIC,
    total_liabilities       NUMERIC,
    current_liabilities     NUMERIC,
    non_current_liabilities NUMERIC,
    equity                  NUMERIC,
    period_date             DATE,
    currency                TEXT DEFAULT 'INR'
);
"""


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def upsert_company(cur, company: CompanyRecord) -> None:
    cur.execute(
        """
        INSERT INTO companies (id, name, erp_code, industry)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (erp_code) DO UPDATE
            SET name = EXCLUDED.name, industry = EXCLUDED.industry
        """,
        (company.id, company.name, company.erp_code, company.industry),
    )


def upsert_document(
    cur,
    doc_id: str,
    company_id: str,
    doc_type: str,
    period_start: date,
    period_end: date,
    raw_text: str,
    status: str,
) -> None:
    h = _hash(raw_text)
    cur.execute(
        """
        INSERT INTO financial_documents
            (id, company_id, document_type, period_start, period_end, raw_text, file_hash, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_hash) DO UPDATE
            SET status = EXCLUDED.status,
                raw_text = EXCLUDED.raw_text
        """,
        (doc_id, company_id, doc_type, period_start, period_end, raw_text, h, status),
    )


def upsert_pl(cur, doc_id: str, pl: PLData, period_start: date, period_end: date) -> None:
    cur.execute(
        """
        INSERT INTO pl_statements
            (document_id, revenue, cogs, gross_profit, operating_expenses,
             ebitda, net_income, period_start, period_end, currency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'INR')
        ON CONFLICT DO NOTHING
        """,
        (
            doc_id, pl.revenue, pl.cogs, pl.gross_profit,
            pl.operating_expenses, pl.ebitda, pl.net_income,
            period_start, period_end,
        ),
    )


def upsert_bs(cur, doc_id: str, bs: BSData, period_date: date) -> None:
    cur.execute(
        """
        INSERT INTO balance_sheets
            (document_id, total_assets, current_assets, non_current_assets,
             total_liabilities, current_liabilities, non_current_liabilities,
             equity, period_date, currency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'INR')
        ON CONFLICT DO NOTHING
        """,
        (
            doc_id,
            bs.total_assets_stated, bs.current_assets, bs.non_current_assets,
            bs.total_liabilities, bs.current_liabilities, bs.non_current_liabilities,
            bs.equity, period_date,
        ),
    )


# ---------------------------------------------------------------------------
# Main seed routine
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Connecting to %s", DATABASE_URL.split("@")[-1])
    try:
        conn = get_connection()
    except Exception as exc:
        log.error("Cannot connect to PostgreSQL: %s", exc)
        sys.exit(1)

    with conn:
        with conn.cursor() as cur:
            log.info("Creating tables (idempotent)…")
            cur.execute(CREATE_TABLES_SQL)

    generated_files: List[Tuple[str, str, str]] = []  # (company, period, filepath)

    with conn:
        with conn.cursor() as cur:
            for company in COMPANIES:
                log.info("Seeding company: %s (%s)", company.name, company.erp_code)
                upsert_company(cur, company)

                for period_key, period_data in company.periods.items():
                    is_q3 = period_key == "Q3"
                    status = "PENDING" if is_q3 else "COMPLETE"

                    # Build text content
                    pl_text = build_pl_text(company, period_key)
                    bs_text = build_bs_text(company, period_key)

                    # Document IDs (deterministic)
                    pl_doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{company.erp_code}-PL-{period_key}"))
                    bs_doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{company.erp_code}-BS-{period_key}"))

                    # Upsert document records
                    upsert_document(
                        cur, pl_doc_id, company.id, "PL",
                        period_data.period_start, period_data.period_end,
                        pl_text, status,
                    )
                    upsert_document(
                        cur, bs_doc_id, company.id, "BALANCE_SHEET",
                        period_data.period_start, period_data.period_end,
                        bs_text, status,
                    )

                    if not is_q3:
                        # Insert historical financial records (baseline for comparison)
                        upsert_pl(cur, pl_doc_id, period_data.pl,
                                  period_data.period_start, period_data.period_end)
                        upsert_bs(cur, bs_doc_id, period_data.bs,
                                  period_data.period_end)
                    else:
                        # Q3: generate PDF files for the student to upload
                        erp = company.erp_code.replace("-", "")
                        pl_base = OUTPUT_DIR / f"{erp}_PL_{period_key}_2024"
                        bs_base = OUTPUT_DIR / f"{erp}_BS_{period_key}_2024"

                        pl_path = save_document(pl_text, pl_base)
                        bs_path = save_document(bs_text, bs_base)

                        generated_files.append((company.erp_code, f"{period_key} P&L", pl_path))
                        generated_files.append((company.erp_code, f"{period_key} BS", bs_path))

                        log.info(
                            "  ✓ Generated %s P&L → %s", period_key, pl_path
                        )
                        log.info(
                            "  ✓ Generated %s Balance Sheet → %s", period_key, bs_path
                        )

    conn.close()
    log.info("")
    log.info("=" * 60)
    log.info("SEED COMPLETE")
    log.info("=" * 60)
    log.info("")
    log.info("PostgreSQL:")
    log.info("  • %d companies", len(COMPANIES))
    log.info("  • Q1 + Q2 historical data (COMPLETE) for all companies")
    log.info("  • Q3 document stubs (PENDING) for all companies")
    log.info("")
    log.info("Generated files in sample_documents/:")
    for erp, label, path in generated_files:
        log.info("  [%s] %s  →  %s", erp, label, Path(path).name)

    log.info("")
    log.info("PLANTED ANOMALIES (one per company in Q3):")
    log.info("-" * 60)
    for erp, desc in ANOMALY_DESCRIPTIONS.items():
        log.info("[%s]", erp)
        for line in textwrap.wrap(desc, width=56):
            log.info("  %s", line)
        log.info("")

    log.info("Upload any Q3 PDF from sample_documents/ to your FastAPI")
    log.info("/api/v1/documents/upload endpoint to trigger the pipeline.")


if __name__ == "__main__":
    main()
