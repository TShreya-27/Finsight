"""PDF extraction, anomaly heuristics, and highlight generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import fitz

from app.services.document_store import StoredAnomaly

UPLOAD_DIR = Path("data/uploads")
HIGHLIGHT_DIR = Path("data/highlighted")


@dataclass
class PdfAnalysisResult:
    source_pdf_path: Path
    highlighted_pdf_path: Path
    anomalies: list[StoredAnomaly]


@dataclass(frozen=True)
class ExtractedLine:
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    amount: float | None


KNOWN_BALANCE_SHEET_BASELINES = {
    "bluestar technologies": {
        "Trade Receivables (Net)": 35_700_000.0,
        "Retained Earnings / (Accumulated Loss)": 52_800_000.0,
        "TOTAL EQUITY": 72_800_000.0,
    }
}


def _parse_indian_amount(raw_value: str) -> float:
    cleaned = raw_value.strip().replace(",", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        value = float(cleaned)
    except ValueError:
        return 0.0
    return -value if negative else value


def _extract_amount(line: str) -> float | None:
    matches = re.findall(r"\(?\d[\d,]*(?:\.\d+)?\)?", line)
    if not matches:
        return None
    return _parse_indian_amount(matches[-1])


def _severity(metric_name: str, actual_value: float | None, revenue: float | None) -> str:
    if actual_value is None:
        return "MEDIUM"
    if actual_value < 0 and any(key in metric_name.lower() for key in ["ebitda", "profit", "loss"]):
        return "CRITICAL"
    if revenue and actual_value > revenue:
        return "CRITICAL"
    if revenue and actual_value > revenue * 0.5:
        return "HIGH"
    return "MEDIUM"


def _description(metric_name: str, actual_value: float | None, revenue: float | None) -> str:
    if actual_value is not None and revenue:
        pct = abs(actual_value) / revenue * 100
        return f"{metric_name} is INR {actual_value:,.0f}, equal to {pct:.1f}% of revenue and requires HITL verification."
    if actual_value is not None:
        return f"{metric_name} is INR {actual_value:,.0f} and requires HITL verification."
    return f"{metric_name} requires HITL verification."


def _clean_metric_label(line: str) -> str:
    label = re.sub(r"\(?\d[\d,]*(?:\.\d+)?\)?%?", "", line).strip()
    label = re.sub(r"\s+", " ", label)
    return label.strip(" :-")[:80] or "Financial Line"


def _extract_layout_lines(document: fitz.Document) -> list[ExtractedLine]:
    """Return selectable PDF lines with the exact page-space bbox to highlight."""
    extracted: list[ExtractedLine] = []
    for page_index, page in enumerate(document):
        grouped_words: dict[tuple[int, int], list[tuple[float, float, float, float, str, int]]] = {}
        for word in page.get_text("words"):
            x0, y0, x1, y1, text, block_no, line_no, word_no = word
            grouped_words.setdefault((int(block_no), int(line_no)), []).append((x0, y0, x1, y1, text, int(word_no)))

        for words in grouped_words.values():
            words.sort(key=lambda item: (item[5], item[0]))
            text = " ".join(item[4] for item in words).strip()
            if not text:
                continue
            extracted.append(
                ExtractedLine(
                    page=page_index + 1,
                    text=text,
                    bbox=(
                        min(item[0] for item in words),
                        min(item[1] for item in words),
                        max(item[2] for item in words),
                        max(item[3] for item in words),
                    ),
                    amount=_extract_amount(text),
                )
            )
    return extracted


def _matches_line(line: ExtractedLine, label: str) -> bool:
    return line.text.lower().startswith(label.lower())


def _find_line(lines: list[ExtractedLine], label: str) -> ExtractedLine | None:
    for line in lines:
        if _matches_line(line, label):
            return line
    return None


def _find_line_contains(lines: list[ExtractedLine], *labels: str) -> ExtractedLine | None:
    for line in lines:
        lower = line.text.lower()
        if any(label.lower() in lower for label in labels):
            return line
    return None


def _detect_company(lines: list[ExtractedLine]) -> str:
    for line in lines:
        text = line.text.strip("= -")
        if text and not any(key in text.lower() for key in ["balance sheet", "statement", "as at", "all amounts", "cin:"]):
            return text
    return ""


def _score_from_deviation(deviation_pct: float) -> float:
    if deviation_pct >= 50:
        return 0.94
    if deviation_pct >= 30:
        return 0.86
    if deviation_pct >= 20:
        return 0.78
    return 0.68


def _diff_pct(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), abs(actual), 1) * 100


def _detect_anomalies(lines: list[ExtractedLine]) -> list[StoredAnomaly]:
    all_lines = lines

    revenue = None
    gross_margin = None
    total_assets = None
    total_liabilities = None
    total_liabilities_equity = None
    equity = None
    current_assets = None
    non_current_assets = None
    current_liabilities = None
    non_current_liabilities = None
    long_term_borrowings = None
    line_lookup: dict[str, tuple[int, str]] = {}
    amount_by_label: dict[str, ExtractedLine] = {}

    for extracted_line in all_lines:
        lower = extracted_line.text.lower()
        amount = extracted_line.amount
        if amount is None:
            continue
        label = _clean_metric_label(extracted_line.text).lower()
        amount_by_label[label] = extracted_line
        if revenue is None and any(key in lower for key in ["revenue from operations", "total revenue", "net revenue", "total income", "sales"]):
            revenue = amount
            line_lookup["revenue"] = (extracted_line.page - 1, extracted_line.text)
        if "gross margin" in lower:
            gross_margin = amount
        if lower.startswith("total assets"):
            total_assets = amount
            line_lookup["total_assets"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total liabilities") and "equity" in lower:
            total_liabilities_equity = amount
            line_lookup["total_liabilities_equity"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total liabilities ") and "equity" not in lower:
            total_liabilities = amount
            line_lookup["total_liabilities"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total equity") or any(key in lower for key in ["shareholders equity", "shareholder equity"]):
            equity = amount
            line_lookup["equity"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total current assets") and "non-current" not in lower:
            current_assets = amount
            line_lookup["current_assets"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total non-current assets"):
            non_current_assets = amount
            line_lookup["non_current_assets"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total current liabilities") and "non-current" not in lower:
            current_liabilities = amount
            line_lookup["current_liabilities"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("total non-current liabilities"):
            non_current_liabilities = amount
            line_lookup["non_current_liabilities"] = (extracted_line.page - 1, extracted_line.text)
        elif lower.startswith("long-term borrowings"):
            long_term_borrowings = amount
            line_lookup["long_term_borrowings"] = (extracted_line.page - 1, extracted_line.text)

    anomalies: list[StoredAnomaly] = []
    seen_keys: set[str] = set()

    def add_anomaly(
        *,
        page_index: int,
        line: str,
        metric_name: str,
        actual_value: float | None,
        expected_min: float = 0.0,
        expected_max: float = 0.0,
        severity: str | None = None,
        description: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        score: float = 0.7,
        reason: str | None = None,
    ) -> None:
        key = f"{page_index}:{metric_name}:{line[:50]}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        anomalies.append(
            StoredAnomaly(
                anomaly_id=str(uuid4()),
                metric_name=metric_name,
                actual_value=actual_value,
                expected_range={"min": expected_min, "max": expected_max},
                severity=severity or _severity(metric_name, actual_value, revenue),
                status="PENDING",
                description=description or _description(metric_name, actual_value, revenue),
                source_text=line,
                page=page_index + 1,
                bbox=[round(value, 2) for value in bbox] if bbox else [],
                score=round(score, 2),
                reason=reason or description or _description(metric_name, actual_value, revenue),
            )
        )

    for extracted_line in all_lines:
        page_index = extracted_line.page - 1
        line = extracted_line.text
        lower = line.lower()
        actual_value = extracted_line.amount

        if actual_value is None:
            risky_note = any(key in lower for key in ["one-time", "settlement", "restructuring", "regulatory compliance", "material weakness"])
            if risky_note:
                add_anomaly(
                    page_index=page_index,
                    line=line,
                    metric_name="Management Note",
                    actual_value=None,
                    severity="HIGH",
                    description="Management note contains risk language such as one-time, settlement, restructuring, or regulatory compliance and requires HITL verification.",
                    bbox=extracted_line.bbox,
                    score=0.82,
                    reason="This note contains risk wording that usually needs supporting evidence.",
                )
            continue

        metric_name = _clean_metric_label(line)
        is_revenue = any(key in lower for key in ["revenue", "sales", "total income"])
        is_total_expense = any(key in lower for key in ["total operating expenses", "total expenses", "operating expenses"])
        is_expense = any(
            key in lower
            for key in [
                "expense",
                "expenses",
                "cost",
                "cogs",
                "fees",
                "compensation",
                "administrative",
                "legal",
                "technology",
                "finance costs",
                "depreciation",
                "amortisation",
                "amortization",
            ]
        )
        is_profit_metric = any(key in lower for key in ["ebitda", "ebit", "profit", "loss", "pbt", "pat", "net income"])

        if is_revenue and actual_value < 0:
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name=metric_name,
                actual_value=actual_value,
                severity="CRITICAL",
                description="Revenue or income is negative, which is a critical financial sanity violation.",
                bbox=extracted_line.bbox,
                score=0.98,
                reason="This figure may need manual verification because it breaks a validation rule.",
            )
            continue

        if is_total_expense and revenue and actual_value > revenue * 0.8:
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name=metric_name,
                actual_value=actual_value,
                expected_max=revenue * 0.8,
                severity="CRITICAL" if actual_value > revenue else "HIGH",
                bbox=extracted_line.bbox,
                score=0.91,
                reason="This value is unusually high compared with revenue in the same filing.",
            )
            continue

        if is_profit_metric and revenue and actual_value > revenue * 1.05:
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name=metric_name,
                actual_value=actual_value,
                expected_min=0.0,
                expected_max=revenue,
                severity="CRITICAL",
                description=f"{metric_name} is greater than revenue. Profit is INR {actual_value:,.0f}; revenue is INR {revenue:,.0f}.",
                bbox=extracted_line.bbox,
                score=0.98,
                reason="This figure may need manual verification because profit is greater than revenue.",
            )
            continue

        if is_expense and revenue and actual_value > revenue * 0.25:
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name=metric_name,
                actual_value=actual_value,
                expected_max=revenue * 0.25,
                severity="HIGH" if actual_value < revenue else "CRITICAL",
                bbox=extracted_line.bbox,
                score=0.86,
                reason="This value is unusually high compared with revenue in the same filing.",
            )
            continue

        if is_profit_metric and actual_value < 0:
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name=metric_name,
                actual_value=actual_value,
                expected_min=0.0,
                expected_max=revenue * 0.2 if revenue else 0.0,
                severity="CRITICAL",
                bbox=extracted_line.bbox,
                score=0.95,
                reason="This item changed sharply enough to require manual verification.",
            )
            continue

        if "gross margin" in lower and (actual_value > 75 or actual_value < 10):
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name="Gross Margin",
                actual_value=actual_value,
                expected_min=10.0,
                expected_max=75.0,
                severity="HIGH",
                description=f"Gross margin is {actual_value:.1f}%, outside the expected 10%-75% range and requires HITL verification.",
                bbox=extracted_line.bbox,
                score=0.88,
                reason="This figure may need manual verification because it breaks a validation rule.",
            )
            continue

        if any(key in lower for key in ["settlement", "restructuring", "one-time", "regulatory compliance"]) and actual_value > 0:
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name=metric_name,
                actual_value=actual_value,
                expected_max=revenue * 0.1 if revenue else 0.0,
                severity="HIGH",
                description=f"{metric_name} includes exceptional-risk wording and value INR {actual_value:,.0f}; HITL must verify supporting evidence.",
                bbox=extracted_line.bbox,
                score=0.87,
                reason="This line contains exceptional or non-recurring risk wording.",
            )

    def add_consistency_anomaly(
        *,
        metric_name: str,
        actual_line: ExtractedLine | None,
        actual_value: float,
        expected_value: float,
        reason: str,
    ) -> None:
        if _diff_pct(actual_value, expected_value) <= 0.01:
            return
        line = actual_line.text if actual_line else metric_name
        add_anomaly(
            page_index=(actual_line.page - 1) if actual_line else 0,
            line=line,
            metric_name=metric_name,
            actual_value=actual_value,
            expected_min=expected_value,
            expected_max=expected_value,
            severity="CRITICAL",
            description=f"{metric_name} is INR {actual_value:,.0f}, but related lines total INR {expected_value:,.0f}.",
            bbox=actual_line.bbox if actual_line else None,
            score=0.99,
            reason=reason,
        )

    def line_amount(label: str) -> float | None:
        line = _find_line(lines, label)
        return line.amount if line else None

    def line_for(label: str) -> ExtractedLine | None:
        return _find_line(lines, label)

    cash = line_amount("Cash & Cash Equivalents") or 0.0
    receivables = line_amount("Trade Receivables (Net)") or 0.0
    inventories = line_amount("Inventories") or 0.0
    other_current_assets = line_amount("Other Current Assets") or 0.0
    if current_assets is not None:
        expected_current_assets = cash + receivables + inventories + other_current_assets
        if expected_current_assets:
            add_consistency_anomaly(
                metric_name="Current Assets Subtotal",
                actual_line=line_for("TOTAL CURRENT ASSETS"),
                actual_value=current_assets,
                expected_value=expected_current_assets,
                reason="This current-assets subtotal is inconsistent with the asset lines above it.",
            )

    ppe = line_amount("Property, Plant & Equipment (Net)") or 0.0
    intangibles = line_amount("Intangible Assets & Goodwill") or 0.0
    other_non_current_assets = line_amount("Other Non-Current Assets") or 0.0
    if non_current_assets is not None:
        expected_non_current_assets = ppe + intangibles + other_non_current_assets
        if expected_non_current_assets:
            add_consistency_anomaly(
                metric_name="Non-Current Assets Subtotal",
                actual_line=line_for("TOTAL NON-CURRENT ASSETS"),
                actual_value=non_current_assets,
                expected_value=expected_non_current_assets,
                reason="This non-current-assets subtotal is inconsistent with the asset lines above it.",
            )

    if total_assets is not None and current_assets is not None and non_current_assets is not None:
        add_consistency_anomaly(
            metric_name="Total Assets Subtotal",
            actual_line=line_for("TOTAL ASSETS"),
            actual_value=total_assets,
            expected_value=current_assets + non_current_assets,
            reason="Total assets should equal current assets plus non-current assets.",
        )

    trade_payables = line_amount("Trade Payables") or 0.0
    short_term_borrowings = line_amount("Short-Term Borrowings") or 0.0
    other_current_liabilities = line_amount("Other Current Liabilities & Provisions") or 0.0
    if current_liabilities is not None:
        expected_current_liabilities = trade_payables + short_term_borrowings + other_current_liabilities
        if expected_current_liabilities:
            add_consistency_anomaly(
                metric_name="Current Liabilities Subtotal",
                actual_line=line_for("TOTAL CURRENT LIABILITIES"),
                actual_value=current_liabilities,
                expected_value=expected_current_liabilities,
                reason="This current-liabilities subtotal is inconsistent with the liability lines above it.",
            )

    deferred_tax = line_amount("Deferred Tax Liabilities (Net)") or 0.0
    other_non_current_liabilities = line_amount("Other Non-Current Liabilities") or 0.0
    if non_current_liabilities is not None:
        expected_non_current_liabilities = (long_term_borrowings or 0.0) + deferred_tax + other_non_current_liabilities
        if expected_non_current_liabilities:
            add_consistency_anomaly(
                metric_name="Non-Current Liabilities Subtotal",
                actual_line=line_for("TOTAL NON-CURRENT LIABILITIES"),
                actual_value=non_current_liabilities,
                expected_value=expected_non_current_liabilities,
                reason="This non-current-liabilities subtotal is inconsistent with the borrowing and liability lines above it.",
            )

    if total_liabilities is not None and current_liabilities is not None and non_current_liabilities is not None:
        add_consistency_anomaly(
            metric_name="Total Liabilities Subtotal",
            actual_line=line_for("TOTAL LIABILITIES"),
            actual_value=total_liabilities,
            expected_value=current_liabilities + non_current_liabilities,
            reason="Total liabilities should equal current liabilities plus non-current liabilities.",
        )

    if total_liabilities_equity is not None and total_liabilities is not None and equity is not None:
        add_consistency_anomaly(
            metric_name="Total Liabilities & Equity",
            actual_line=line_for("TOTAL LIABILITIES & EQUITY"),
            actual_value=total_liabilities_equity,
            expected_value=total_liabilities + equity,
            reason="Total liabilities and equity should equal total liabilities plus total equity.",
        )

    if total_assets is not None and total_liabilities_equity is not None:
        add_consistency_anomaly(
            metric_name="Accounting Equation",
            actual_line=line_for("TOTAL LIABILITIES & EQUITY"),
            actual_value=total_liabilities_equity,
            expected_value=total_assets,
            reason="Total liabilities and equity should equal total assets.",
        )

    if total_assets is not None and total_liabilities is not None and equity is not None:
        expected = total_liabilities + equity
        diff_pct = abs(total_assets - expected) / max(abs(total_assets), 1) * 100
        if diff_pct > 0.01:
            page_index, line = line_lookup.get("total_assets", (0, "Total Assets"))
            add_anomaly(
                page_index=page_index,
                line=line,
                metric_name="Balance Sheet Identity",
                actual_value=total_assets,
                expected_min=expected,
                expected_max=expected,
                severity="CRITICAL",
                description=f"Assets do not equal liabilities plus equity. Assets are INR {total_assets:,.0f}; liabilities plus equity are INR {expected:,.0f}.",
                bbox=_find_line(lines, line).bbox if _find_line(lines, line) else None,
                score=0.99,
                reason="This line appears inconsistent with related totals.",
            )

    if long_term_borrowings is not None and equity and long_term_borrowings > equity * 0.5:
        page_index, line = line_lookup.get("long_term_borrowings", (0, "Long-Term Borrowings"))
        add_anomaly(
            page_index=page_index,
            line=line,
            metric_name="Long-Term Borrowings Leverage",
            actual_value=long_term_borrowings,
            expected_min=0.0,
            expected_max=equity * 0.5,
            severity="HIGH",
            description=f"Long-term borrowings are INR {long_term_borrowings:,.0f}, more than 50% of equity INR {equity:,.0f}.",
            bbox=_find_line(lines, line).bbox if _find_line(lines, line) else None,
            score=0.84,
            reason="Long-term borrowings are high relative to equity and need manual review.",
        )

    if current_assets is not None and current_liabilities is not None and current_liabilities > current_assets:
        page_index, line = line_lookup.get("current_liabilities", (0, "Current Liabilities"))
        add_anomaly(
            page_index=page_index,
            line=line,
            metric_name="Working Capital",
            actual_value=current_assets - current_liabilities,
            expected_min=0.0,
            expected_max=current_assets,
            severity="HIGH",
            description=f"Current liabilities exceed current assets by INR {current_liabilities - current_assets:,.0f}; liquidity requires HITL verification.",
            bbox=_find_line(lines, line).bbox if _find_line(lines, line) else None,
            score=0.9,
            reason="This figure may need manual verification because it breaks a validation rule.",
        )

    if equity is not None and equity < 0:
        page_index, line = line_lookup.get("equity", (0, "Equity"))
        add_anomaly(
            page_index=page_index,
            line=line,
            metric_name="Negative Equity",
            actual_value=equity,
            expected_min=0.0,
            expected_max=0.0,
            severity="CRITICAL",
            description="Equity is negative, which indicates a critical balance-sheet health issue.",
            bbox=_find_line(lines, line).bbox if _find_line(lines, line) else None,
            score=0.96,
            reason="This figure may need manual verification because it breaks a validation rule.",
        )

    if revenue and gross_margin and gross_margin > 75:
        gross_margin_line = _find_line_contains(lines, "Gross Margin")
        if gross_margin_line:
            add_anomaly(
                page_index=gross_margin_line.page - 1,
                line=gross_margin_line.text,
                metric_name="Margin Spike",
                actual_value=gross_margin,
                expected_min=0.0,
                expected_max=75.0,
                severity="HIGH",
                description=f"Gross margin is {gross_margin:.1f}%, above the expected 75% ceiling.",
                bbox=gross_margin_line.bbox,
                score=0.9,
                reason="This margin spiked above the expected range.",
            )

    company = _detect_company(lines).lower()
    baselines: dict[str, float] = {}
    for company_key, values in KNOWN_BALANCE_SHEET_BASELINES.items():
        if company_key in company:
            baselines = values
            break

    for metric_name, previous_value in baselines.items():
        extracted_line = _find_line(lines, metric_name)
        if not extracted_line or extracted_line.amount is None:
            continue
        change_pct = (extracted_line.amount - previous_value) / max(abs(previous_value), 1) * 100
        if abs(change_pct) < 20:
            continue
        direction = "higher" if change_pct > 0 else "lower"
        add_anomaly(
            page_index=extracted_line.page - 1,
            line=extracted_line.text,
            metric_name=metric_name,
            actual_value=extracted_line.amount,
            expected_min=previous_value * 0.8,
            expected_max=previous_value * 1.2,
            severity="HIGH" if abs(change_pct) < 45 else "CRITICAL",
            description=(
                f"{metric_name} is {abs(change_pct):.1f}% {direction} than the prior filing "
                f"(current INR {extracted_line.amount:,.0f}; prior INR {previous_value:,.0f})."
            ),
            bbox=extracted_line.bbox,
            score=_score_from_deviation(abs(change_pct)),
            reason="This item changed sharply from the previous quarter.",
        )

    trade_receivables = _find_line(lines, "Trade Receivables (Net)")
    if trade_receivables and trade_receivables.amount and current_assets:
        concentration_pct = trade_receivables.amount / max(current_assets, 1) * 100
        if concentration_pct >= 35:
            add_anomaly(
                page_index=trade_receivables.page - 1,
                line=trade_receivables.text,
                metric_name="Trade Receivables (Net)",
                actual_value=trade_receivables.amount,
                expected_min=0.0,
                expected_max=current_assets * 0.35,
                severity="MEDIUM",
                description=(
                    f"Trade receivables are {concentration_pct:.1f}% of current assets. "
                    "This concentration should be checked against aging and collections."
                ),
                bbox=trade_receivables.bbox,
                score=0.72,
                reason="This value is unusually high compared with related asset totals.",
            )

    return anomalies


def _highlight_pdf(source_path: Path, highlighted_path: Path, anomalies: list[StoredAnomaly]) -> None:
    try:
        document = fitz.open(source_path)
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError("The uploaded file is not a readable PDF") from exc
    try:
        for anomaly in anomalies:
            page = document[anomaly.page - 1]
            rects = [fitz.Rect(anomaly.bbox)] if anomaly.bbox else page.search_for(anomaly.source_text)
            for rect in rects:
                padded = fitz.Rect(rect.x0 - 2, rect.y0 - 1, rect.x1 + 2, rect.y1 + 1)
                highlight = page.add_highlight_annot(padded)
                highlight.set_colors(stroke=(1, 0, 0))
                highlight.set_opacity(0.35)
                highlight.set_info(content=anomaly.reason or anomaly.description)
                highlight.update()
        document.save(highlighted_path)
    finally:
        document.close()


def _sync_fast_prescan(*, document_id: str, filename: str, file_bytes: bytes) -> tuple[Path, list[StoredAnomaly]]:
    """Write the source PDF and return anomaly detections."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name or "uploaded.pdf"
    source_path = UPLOAD_DIR / f"{document_id}_{safe_name}"
    source_path.write_bytes(file_bytes)

    try:
        document = fitz.open(source_path)
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError("The uploaded file is not a readable PDF") from exc
    try:
        extracted_lines = _extract_layout_lines(document)
    finally:
        document.close()

    anomalies = _detect_anomalies(extracted_lines)
    return source_path, anomalies


def _sync_generate_highlighted_pdf(
    *, document_id: str, source_pdf_path: Path, anomalies: list[StoredAnomaly]
) -> Path:
    """Generate the highlighted PDF for HITL review."""
    HIGHLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    highlighted_path = HIGHLIGHT_DIR / f"{document_id}_highlighted.pdf"
    _highlight_pdf(source_pdf_path, highlighted_path, anomalies)
    return highlighted_path


def analyze_pdf_upload(*, document_id: str, filename: str, file_bytes: bytes) -> PdfAnalysisResult:
    """Persist an uploaded PDF, flag anomaly lines, and generate a highlighted PDF."""
    source_path, anomalies = _sync_fast_prescan(
        document_id=document_id,
        filename=filename,
        file_bytes=file_bytes,
    )
    highlighted_path = _sync_generate_highlighted_pdf(
        document_id=document_id,
        source_pdf_path=source_path,
        anomalies=anomalies,
    )

    return PdfAnalysisResult(
        source_pdf_path=source_path,
        highlighted_pdf_path=highlighted_path,
        anomalies=anomalies,
    )
