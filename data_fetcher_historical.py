import json
from datetime import datetime
from pathlib import Path

import yfinance as yf

from thesis_utils import canonical_ticker, filename_key


PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
YFINANCE_CACHE_DIR = PROJECT_ROOT / "tmp" / "yfinance-cache"
HISTORICAL_CACHE_VERSION = "v374"
SCHEMA_VERSION = "historical_v2"
SOURCE = "yfinance"

# V3.7.1: expanded BS field coverage so the Excel Balance Sheet Forecast can
# show real items (marketable securities, goodwill / intangibles, deferred
# revenue, leases, deferred taxes, total current / non-current buckets) instead
# of stuffing everything into a single residual plug. Income statement and
# cash flow maps are unchanged.

YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
try:
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))
except Exception:
    pass

FIELD_DICTIONARY = {
    # Income statement
    "revenue": "Revenue",
    "cost_of_revenue": "COGS / Cost of Revenue",
    "gross_profit": "Gross Profit",
    "research_development": "R&D",
    "selling_general_admin": "SG&A",
    "operating_expenses": "Total Operating Expenses",
    "operating_income": "Operating Income / EBIT",
    "other_income_expense_net": "Other Income / Expense, net",
    "pretax_income": "Pre-tax Income",
    "net_income": "Net Income",
    "tax_expense": "Tax Expense",
    "interest_expense": "Interest Expense",
    "diluted_shares": "Diluted Shares",
    # Balance sheet — V3.7.1 expanded set
    "cash": "Cash & Equivalents",
    "cash_and_short_term_investments": "Cash + Short-term Investments",
    "short_term_investments": "Short-term Investments / Marketable Securities (Current)",
    "accounts_receivable": "Accounts Receivable",
    "other_receivables": "Other Receivables",
    "inventory": "Inventory",
    "other_current_assets": "Other Current Assets",
    "total_current_assets": "Total Current Assets",
    "ppe": "PP&E, Net",
    "goodwill": "Goodwill",
    "intangible_assets": "Intangible Assets",
    "goodwill_and_intangibles": "Goodwill + Intangibles",
    "long_term_investments": "Long-term Investments / Marketable Securities (Non-current)",
    "deferred_tax_assets": "Deferred Tax Assets (Non-current)",
    "other_non_current_assets": "Other Non-current Assets",
    "total_non_current_assets": "Total Non-current Assets",
    "total_assets": "Total Assets",
    "accounts_payable": "Accounts Payable",
    "current_deferred_revenue": "Deferred Revenue, Current",
    "short_term_debt": "Short-term Debt / Current Portion of Debt",
    "current_capital_lease_obligation": "Capital Lease Obligation, Current",
    "other_current_liabilities": "Other Current Liabilities",
    "total_current_liabilities": "Total Current Liabilities",
    "long_term_debt": "Long-term Debt",
    "long_term_capital_lease_obligation": "Capital Lease Obligation, Non-current",
    "non_current_deferred_revenue": "Deferred Revenue, Non-current",
    "deferred_tax_liabilities": "Deferred Tax Liabilities (Non-current)",
    "other_non_current_liabilities": "Other Non-current Liabilities",
    "total_non_current_liabilities": "Total Non-current Liabilities",
    "total_debt": "Total Debt",
    "total_liabilities": "Total Liabilities",
    "total_equity": "Total Equity",
    "net_debt": "Net Debt (cache reported)",
    # Cash flow
    "operating_cash_flow": "Operating Cash Flow",
    "capex": "Capital Expenditure",
    "depreciation_amortization": "D&A",
    "free_cash_flow": "Free Cash Flow",
    # V3.7.4: Shareholder Returns v1 source fields. Cash-flow sign convention is
    # preserved as-reported (typically negative for cash outflows); the calculator
    # / Excel display flip signs explicitly so reviewers can read absolute values.
    "cash_dividends_paid": "Cash Dividends Paid",
    "repurchase_of_capital_stock": "Repurchase Of Capital Stock",
    "issuance_of_capital_stock": "Issuance Of Capital Stock",
    "stock_based_compensation": "Stock-based Compensation",
}

STATEMENT_FIELD_MAP = {
    "income_statement": {
        "revenue": ("Total Revenue", "Revenue"),
        "cost_of_revenue": ("Cost Of Revenue", "Cost Of Goods Sold"),
        "gross_profit": ("Gross Profit",),
        "research_development": ("Research And Development", "Research Development", "Research And Development Expense"),
        "selling_general_admin": ("Selling General And Administration", "Selling General And Administrative", "Selling General And Administrative Expense"),
        "operating_expenses": ("Operating Expense", "Operating Expenses", "Total Operating Expenses"),
        "operating_income": ("Operating Income", "EBIT"),
        "other_income_expense_net": ("Other Income Expense", "Other Non Operating Income Expenses", "Other Income Expense Net"),
        "pretax_income": ("Pretax Income", "Income Before Tax", "Income Before Tax Continuing Operations"),
        "net_income": ("Net Income", "Net Income Common Stockholders"),
        "tax_expense": ("Tax Provision", "Income Tax Expense"),
        "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
        "diluted_shares": ("Diluted Average Shares", "Diluted Shares"),
    },
    "balance_sheet": {
        # Cash and near-cash
        "cash": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
        "cash_and_short_term_investments": ("Cash Cash Equivalents And Short Term Investments",),
        "short_term_investments": (
            "Other Short Term Investments",
            "Short Term Investments",
            "Available For Sale Securities",
        ),
        # Current assets
        "accounts_receivable": ("Accounts Receivable", "Receivables"),
        "other_receivables": ("Other Receivables",),
        "inventory": ("Inventory",),
        "other_current_assets": ("Other Current Assets",),
        "total_current_assets": ("Current Assets", "Total Current Assets"),
        # Non-current assets
        "ppe": ("Net PPE", "Property Plant Equipment", "Gross PPE"),
        "goodwill": ("Goodwill",),
        "intangible_assets": ("Other Intangible Assets", "Intangible Assets"),
        "goodwill_and_intangibles": ("Goodwill And Other Intangible Assets",),
        "long_term_investments": (
            "Investments And Advances",
            "Long Term Investments",
            "Investmentin Financial Assets",
            "Other Investments",
        ),
        "deferred_tax_assets": (
            "Non Current Deferred Taxes Assets",
            "Non Current Deferred Assets",
            "Deferred Tax Assets Non Current",
        ),
        "other_non_current_assets": ("Other Non Current Assets",),
        "total_non_current_assets": ("Total Non Current Assets",),
        "total_assets": ("Total Assets",),
        # Current liabilities
        "accounts_payable": ("Accounts Payable",),
        "current_deferred_revenue": ("Current Deferred Revenue", "Current Deferred Liabilities"),
        "short_term_debt": (
            "Current Debt",
            "Current Debt And Capital Lease Obligation",
            "Short Long Term Debt",
        ),
        "current_capital_lease_obligation": ("Current Capital Lease Obligation",),
        "other_current_liabilities": ("Other Current Liabilities",),
        "total_current_liabilities": ("Current Liabilities", "Total Current Liabilities"),
        # Non-current liabilities
        "long_term_debt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
        "long_term_capital_lease_obligation": ("Long Term Capital Lease Obligation",),
        "non_current_deferred_revenue": (
            "Non Current Deferred Revenue",
            "Tradeand Other Payables Non Current",
        ),
        "deferred_tax_liabilities": (
            "Non Current Deferred Taxes Liabilities",
            "Deferred Tax Liabilities Non Current",
        ),
        "other_non_current_liabilities": ("Other Non Current Liabilities",),
        "total_non_current_liabilities": ("Total Non Current Liabilities Net Minority Interest",),
        # Aggregates
        "total_debt": ("Total Debt",),
        "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
        "total_equity": (
            "Stockholders Equity",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity",
        ),
        "net_debt": ("Net Debt",),
    },
    "cash_flow": {
        "operating_cash_flow": ("Operating Cash Flow", "Total Cash From Operating Activities"),
        "capex": ("Capital Expenditure", "Capital Expenditures", "Purchase Of Property Plant And Equipment"),
        "depreciation_amortization": (
            "Depreciation And Amortization",
            "Depreciation Depletion And Amortization",
        ),
        "free_cash_flow": ("Free Cash Flow",),
        # V3.7.4 Shareholder Returns sources. Raw yfinance values are typically
        # negative for cash outflows; sign is preserved in the cache.
        "cash_dividends_paid": (
            "Cash Dividends Paid",
            "Common Stock Dividend Paid",
            "Dividends Paid",
        ),
        "repurchase_of_capital_stock": (
            "Repurchase Of Capital Stock",
            "Common Stock Payments",
            "Repurchase Of Common Stock",
        ),
        "issuance_of_capital_stock": (
            "Issuance Of Capital Stock",
            "Common Stock Issuance",
        ),
        "stock_based_compensation": ("Stock Based Compensation",),
    },
}

AAPL_KEY_5Y_FIELDS = {
    "income_statement": [
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "research_development",
        "selling_general_admin",
        "operating_expenses",
        "operating_income",
        "interest_expense",
        "other_income_expense_net",
        "pretax_income",
        "net_income",
        "tax_expense",
        "diluted_shares",
    ],
    "balance_sheet": [
        "cash",
        "short_term_debt",
        "long_term_debt",
        "total_debt",
        "total_assets",
        "total_equity",
        "ppe",
        "net_debt",
    ],
    "cash_flow": [
        "operating_cash_flow",
        "capex",
        "depreciation_amortization",
        "free_cash_flow",
    ],
}

# yfinance can expose Apple FY2021 as a partially populated annual column:
# lease/debt memo rows are present, while the core statements are null. Apple is
# not a data-limited issuer, so keep a narrow 10-K backfill at the normalized
# cache layer instead of allowing downstream sheets to show unexplained blanks.
AAPL_FY2021_FORM_10K_BACKFILL = {
    "period_end_date": "2021-09-30",
    "fiscal_year": 2021,
    "source": "Apple FY2021 Form 10-K",
    "fields": {
        "income_statement": {
            "revenue": ("Total Revenue", 365_817_000_000.0),
            "gross_profit": ("Gross Profit", 152_836_000_000.0),
            "operating_income": ("Operating Income", 108_949_000_000.0),
            "net_income": ("Net Income", 94_680_000_000.0),
            "tax_expense": ("Tax Provision", 14_527_000_000.0),
            "interest_expense": ("Interest Expense", 2_645_000_000.0),
            "diluted_shares": ("Diluted Average Shares", 16_864_919_000.0),
        },
        "balance_sheet": {
            "cash": ("Cash And Cash Equivalents", 34_940_000_000.0),
            "cash_and_short_term_investments": (
                "Cash Cash Equivalents And Short Term Investments",
                62_639_000_000.0,
            ),
            "short_term_investments": ("Other Short Term Investments", 27_699_000_000.0),
            "accounts_receivable": ("Accounts Receivable", 26_278_000_000.0),
            "other_receivables": ("Other Receivables", 25_228_000_000.0),
            "inventory": ("Inventory", 6_580_000_000.0),
            "other_current_assets": ("Other Current Assets", 14_111_000_000.0),
            "total_current_assets": ("Current Assets", 134_836_000_000.0),
            "ppe": ("Net PPE", 39_440_000_000.0),
            "long_term_investments": ("Long Term Investments", 127_877_000_000.0),
            "other_non_current_assets": ("Other Non Current Assets", 48_849_000_000.0),
            "total_non_current_assets": ("Total Non Current Assets", 216_166_000_000.0),
            "total_assets": ("Total Assets", 351_002_000_000.0),
            "accounts_payable": ("Accounts Payable", 54_763_000_000.0),
            "current_deferred_revenue": ("Current Deferred Revenue", 7_612_000_000.0),
            "short_term_debt": ("Current Debt", 15_613_000_000.0),
            "current_capital_lease_obligation": ("Current Capital Lease Obligation", 1_528_000_000.0),
            "other_current_liabilities": ("Other Current Liabilities", 47_493_000_000.0),
            "total_current_liabilities": ("Current Liabilities", 125_481_000_000.0),
            "long_term_debt": ("Long Term Debt", 109_106_000_000.0),
            "long_term_capital_lease_obligation": ("Long Term Capital Lease Obligation", 10_275_000_000.0),
            "non_current_deferred_revenue": ("Non Current Deferred Revenue", 24_689_000_000.0),
            "other_non_current_liabilities": ("Other Non Current Liabilities", 28_361_000_000.0),
            "total_non_current_liabilities": (
                "Total Non Current Liabilities Net Minority Interest",
                162_431_000_000.0,
            ),
            "total_debt": ("Total Debt", 136_522_000_000.0),
            "total_liabilities": ("Total Liabilities Net Minority Interest", 287_912_000_000.0),
            "total_equity": ("Stockholders Equity", 63_090_000_000.0),
            "net_debt": ("Net Debt", 89_779_000_000.0),
        },
        "cash_flow": {
            "operating_cash_flow": ("Operating Cash Flow", 104_038_000_000.0),
            "capex": ("Capital Expenditure", -11_085_000_000.0),
            "depreciation_amortization": ("Depreciation And Amortization", 11_284_000_000.0),
            "free_cash_flow": ("Free Cash Flow", 92_953_000_000.0),
            "cash_dividends_paid": ("Cash Dividends Paid", -14_467_000_000.0),
            "repurchase_of_capital_stock": ("Repurchase Of Capital Stock", -85_971_000_000.0),
            "issuance_of_capital_stock": ("Issuance Of Capital Stock", 1_105_000_000.0),
            "stock_based_compensation": ("Stock Based Compensation", 7_906_000_000.0),
        },
    },
}

# Apple Form 10-K consolidated statements of operations backfill. Apple stopped
# separately presenting interest expense in FY2024/FY2025 annual statement/XBRL;
# keep those cells explicit in the workbook as "not separately disclosed" rather
# than leaving them blank or fabricating a debt-cost estimate.
AAPL_FORM_10K_PNL_DETAIL_BACKFILL = {
    2021: {
        "period_end_date": "2021-09-25",
        "source": "Apple FY2021 Form 10-K",
        "fields": {
            "cost_of_revenue": ("Cost of sales", 212_981_000_000.0),
            "research_development": ("Research and development", 21_914_000_000.0),
            "selling_general_admin": ("Selling, general and administrative", 21_973_000_000.0),
            "operating_expenses": ("Total operating expenses", 43_887_000_000.0),
            "other_income_expense_net": ("Other income/(expense), net", 258_000_000.0),
            "pretax_income": ("Income before provision for income taxes", 109_207_000_000.0),
        },
    },
    2022: {
        "period_end_date": "2022-09-24",
        "source": "Apple FY2022 Form 10-K",
        "fields": {
            "cost_of_revenue": ("Cost of sales", 223_546_000_000.0),
            "research_development": ("Research and development", 26_251_000_000.0),
            "selling_general_admin": ("Selling, general and administrative", 25_094_000_000.0),
            "operating_expenses": ("Total operating expenses", 51_345_000_000.0),
            "other_income_expense_net": ("Other income/(expense), net", -334_000_000.0),
            "pretax_income": ("Income before provision for income taxes", 119_103_000_000.0),
        },
    },
    2023: {
        "period_end_date": "2023-09-30",
        "source": "Apple FY2023 Form 10-K",
        "fields": {
            "cost_of_revenue": ("Cost of sales", 214_137_000_000.0),
            "research_development": ("Research and development", 29_915_000_000.0),
            "selling_general_admin": ("Selling, general and administrative", 24_932_000_000.0),
            "operating_expenses": ("Total operating expenses", 54_847_000_000.0),
            "other_income_expense_net": ("Other income/(expense), net", -565_000_000.0),
            "pretax_income": ("Income before provision for income taxes", 113_736_000_000.0),
        },
    },
    2024: {
        "period_end_date": "2024-09-28",
        "source": "Apple FY2024 Form 10-K",
        "fields": {
            "cost_of_revenue": ("Cost of sales", 210_352_000_000.0),
            "research_development": ("Research and development", 31_370_000_000.0),
            "selling_general_admin": ("Selling, general and administrative", 26_097_000_000.0),
            "operating_expenses": ("Total operating expenses", 57_467_000_000.0),
            "other_income_expense_net": ("Other income/(expense), net", 269_000_000.0),
            "pretax_income": ("Income before provision for income taxes", 123_485_000_000.0),
            "interest_expense": (
                "Interest Expense",
                None,
                {
                    "backfilled_from": "Apple FY2024 Form 10-K",
                    "override_reason": "yfinance historical row unavailable; Apple FY2024 Form 10-K does not separately disclose interest expense and includes non-operating items in Other Income/(Expense), net",
                    "not_separately_disclosed": True,
                    "display_value": "N/D in 10-K",
                },
            ),
        },
    },
    2025: {
        "period_end_date": "2025-09-27",
        "source": "Apple FY2025 Form 10-K",
        "fields": {
            "cost_of_revenue": ("Cost of sales", 220_960_000_000.0),
            "research_development": ("Research and development", 34_550_000_000.0),
            "selling_general_admin": ("Selling, general and administrative", 27_601_000_000.0),
            "operating_expenses": ("Total operating expenses", 62_151_000_000.0),
            "other_income_expense_net": ("Other income/(expense), net", -321_000_000.0),
            "pretax_income": ("Income before provision for income taxes", 132_729_000_000.0),
            "interest_expense": (
                "Interest Expense",
                None,
                {
                    "backfilled_from": "Apple FY2025 Form 10-K",
                    "override_reason": "yfinance historical row unavailable; Apple FY2025 Form 10-K does not separately disclose interest expense and includes non-operating items in Other Income/(Expense), net",
                    "not_separately_disclosed": True,
                    "display_value": "N/D in 10-K",
                },
            ),
        },
    },
}


def _detect_market(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(".HK"):
        return "HK"
    if s.endswith(".SS") or s.endswith(".SZ"):
        return "CN"
    return "US"


def historical_cache_key(symbol: str) -> str:
    return filename_key(symbol)


def historical_cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"financials_historical_{historical_cache_key(symbol)}_{HISTORICAL_CACHE_VERSION}.json"


def _iso_date(value) -> str | None:
    if value is None:
        return None
    try:
        return value.date().isoformat()
    except AttributeError:
        text = str(value)
        return text[:10] if len(text) >= 10 else text


def _clean_number(value):
    if value is None:
        return None
    try:
        if value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_field(df, period, candidates: tuple[str, ...]):
    if df is None or getattr(df, "empty", True):
        return None, None
    for raw_name in candidates:
        if raw_name in df.index:
            return raw_name, _clean_number(df.loc[raw_name, period])
    return None, None


def _entry_for_period(df, period, field_map: dict) -> dict:
    period_end = _iso_date(period)
    fiscal_year = None
    if period_end:
        try:
            fiscal_year = int(period_end[:4])
        except ValueError:
            fiscal_year = None

    fields = {}
    for normalized_key, candidates in field_map.items():
        raw_name, value = _extract_field(df, period, candidates)
        fields[normalized_key] = {
            "raw_field_name": raw_name,
            "normalized_field_key": normalized_key,
            "value": value,
        }

    return {
        "period_end_date": period_end,
        "fiscal_year": fiscal_year,
        "period_type": "annual",
        "fields": fields,
    }


def _summarize_field_coverage(statements: dict, field_filter: str) -> dict:
    """Return per-statement field coverage for cache metadata.

    field_filter == "available" lists keys that have at least one non-null value
    across the captured periods; "missing" lists keys whose value is null in
    every period (or whose yfinance row was not matched).
    """
    summary: dict[str, list[str]] = {}
    for statement_name, entries in (statements or {}).items():
        all_keys = list(STATEMENT_FIELD_MAP.get(statement_name, {}).keys())
        seen: dict[str, bool] = {key: False for key in all_keys}
        for entry in entries or []:
            for key, meta in (entry.get("fields") or {}).items():
                if meta.get("value") is not None:
                    seen[key] = True
        if field_filter == "available":
            summary[statement_name] = [k for k, ok in seen.items() if ok]
        else:
            summary[statement_name] = [k for k, ok in seen.items() if not ok]
    return summary


def _merge_backfill_entry(entries: list[dict], statement_name: str, backfill: dict) -> None:
    target_year = backfill["fiscal_year"]
    entry = next((item for item in entries if item.get("fiscal_year") == target_year), None)
    if entry is None:
        entry = {
            "period_end_date": backfill["period_end_date"],
            "fiscal_year": target_year,
            "period_type": "annual",
            "fields": {},
        }
        entries.append(entry)

    fields = entry.setdefault("fields", {})
    for normalized_key, item in backfill["fields"].get(statement_name, {}).items():
        raw_name = item[0]
        value = item[1]
        extra = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
        current = fields.get(normalized_key) or {}
        if current.get("value") is None and not current.get("not_separately_disclosed"):
            merged = {
                "raw_field_name": current.get("raw_field_name") or raw_name,
                "normalized_field_key": normalized_key,
                "value": value,
                "backfilled_from": backfill["source"],
            }
            merged.update(extra)
            fields[normalized_key] = merged


def _key_history_coverage(statements: dict, required_fields: dict, years: list[int]) -> dict:
    missing = []
    by_statement = {}
    for statement_name, field_keys in required_fields.items():
        entries_by_year = {
            entry.get("fiscal_year"): entry
            for entry in statements.get(statement_name) or []
        }
        statement_missing = []
        for year in years:
            fields = (entries_by_year.get(year) or {}).get("fields") or {}
            for field_key in field_keys:
                meta = fields.get(field_key) or {}
                value = meta.get("value")
                if value is None and not meta.get("not_separately_disclosed"):
                    statement_missing.append(f"{year}:{field_key}")
                    missing.append(f"{statement_name}:{year}:{field_key}")
        by_statement[statement_name] = {
            "required_fields": field_keys,
            "missing": statement_missing,
        }
    return {
        "years": years,
        "complete": not missing,
        "missing": missing,
        "by_statement": by_statement,
    }


def _apply_company_specific_backfills(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload
    if canonical_ticker(payload.get("symbol") or "") != "AAPL":
        return payload

    statements = payload.setdefault("statements", {})
    for statement_name in ("income_statement", "balance_sheet", "cash_flow"):
        entries = statements.setdefault(statement_name, [])
        _merge_backfill_entry(entries, statement_name, AAPL_FY2021_FORM_10K_BACKFILL)
        if statement_name == "income_statement":
            for fiscal_year, detail in AAPL_FORM_10K_PNL_DETAIL_BACKFILL.items():
                _merge_backfill_entry(
                    entries,
                    statement_name,
                    {
                        "period_end_date": detail["period_end_date"],
                        "fiscal_year": fiscal_year,
                        "source": detail["source"],
                        "fields": {"income_statement": detail["fields"]},
                    },
                )
        entries.sort(key=lambda item: item.get("period_end_date") or "")

    all_periods = sorted({
        entry.get("period_end_date")
        for entries in statements.values()
        for entry in entries or []
        if entry.get("period_end_date")
    })
    payload["periods"] = all_periods
    payload["field_dictionary"] = FIELD_DICTIONARY
    payload["available_fields"] = _summarize_field_coverage(statements, field_filter="available")
    payload["missing_fields"] = _summarize_field_coverage(statements, field_filter="missing")
    payload.setdefault("source_overrides", [])
    override = {
        "symbol": "AAPL",
        "fiscal_year": 2021,
        "source": AAPL_FY2021_FORM_10K_BACKFILL["source"],
        "reason": "yfinance annual frame exposed FY2021 as a partial/null column for core statements",
    }
    if override not in payload["source_overrides"]:
        payload["source_overrides"].append(override)
    for fiscal_year, detail in AAPL_FORM_10K_PNL_DETAIL_BACKFILL.items():
        detail_override = {
            "symbol": "AAPL",
            "fiscal_year": fiscal_year,
            "source": detail["source"],
            "field_name": "P&L detail fields",
            "reason": "filing-backed COGS/R&D/SG&A/opex/other income/pretax detail for Apple P&L presentation layer",
        }
        if detail_override not in payload["source_overrides"]:
            payload["source_overrides"].append(detail_override)
    for fiscal_year in (2024, 2025):
        interest_override = {
            "symbol": "AAPL",
            "fiscal_year": fiscal_year,
            "source": f"Apple FY{fiscal_year} Form 10-K",
            "field_name": "Interest Expense",
            "reason": "yfinance historical row unavailable; annual Form 10-K does not separately disclose interest expense, so workbook displays a filing-backed not-separately-disclosed marker instead of a blank or fabricated estimate",
        }
        if interest_override not in payload["source_overrides"]:
            payload["source_overrides"].append(interest_override)
    payload["coverage_qa"] = {
        "aapl_key_5y_history": _key_history_coverage(
            statements,
            AAPL_KEY_5Y_FIELDS,
            [2021, 2022, 2023, 2024, 2025],
        )
    }
    return payload


def _annual_entries(df, field_map: dict, max_years: int) -> list[dict]:
    if df is None or getattr(df, "empty", True):
        return []
    periods = list(df.columns)[:max_years]
    entries = [_entry_for_period(df, period, field_map) for period in periods]
    return sorted(entries, key=lambda item: item.get("period_end_date") or "")


def _currency_from_info(info: dict) -> str:
    return info.get("financialCurrency") or info.get("currency") or "USD"


def fetch_historical_financials(symbol: str, max_years: int = 5) -> dict:
    canonical = canonical_ticker(symbol)
    market = _detect_market(canonical)
    if market != "US":
        return {
            "symbol": canonical,
            "market": market,
            "currency": None,
            "units": "actual local currency",
            "schema_version": SCHEMA_VERSION,
            "cache_version": HISTORICAL_CACHE_VERSION,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "cached_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": SOURCE,
            "status": "unavailable",
            "message": "Historical financials not available yet for this market",
            "periods": [],
            "available_fields": {"income_statement": [], "balance_sheet": [], "cash_flow": []},
            "missing_fields": {
                statement: list(fields.keys())
                for statement, fields in STATEMENT_FIELD_MAP.items()
            },
            "statements": {"income_statement": [], "balance_sheet": [], "cash_flow": []},
            "field_dictionary": FIELD_DICTIONARY,
        }

    ticker = yf.Ticker(canonical)
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    income_statement = getattr(ticker, "income_stmt", None)
    balance_sheet = getattr(ticker, "balance_sheet", None)
    cash_flow = getattr(ticker, "cashflow", None)

    statements = {
        "income_statement": _annual_entries(
            income_statement, STATEMENT_FIELD_MAP["income_statement"], max_years
        ),
        "balance_sheet": _annual_entries(balance_sheet, STATEMENT_FIELD_MAP["balance_sheet"], max_years),
        "cash_flow": _annual_entries(cash_flow, STATEMENT_FIELD_MAP["cash_flow"], max_years),
    }
    payload = {
        "symbol": canonical,
        "market": market,
        "currency": _currency_from_info(info),
        "units": "actual local currency",
        "schema_version": SCHEMA_VERSION,
        "cache_version": HISTORICAL_CACHE_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cached_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": SOURCE,
        "status": "ok",
        "periods": [
            entry.get("period_end_date")
            for entry in statements.get("balance_sheet") or []
            if entry.get("period_end_date")
        ],
        "available_fields": _summarize_field_coverage(statements, field_filter="available"),
        "missing_fields": _summarize_field_coverage(statements, field_filter="missing"),
        "statements": statements,
        "field_dictionary": FIELD_DICTIONARY,
    }
    return _apply_company_specific_backfills(payload)


def write_historical_cache(symbol: str, max_years: int = 5) -> dict:
    payload = fetch_historical_financials(symbol, max_years=max_years)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = historical_cache_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"path": str(path), "data": payload}


def read_historical_cache(symbol: str, auto_rebuild: bool = True) -> dict:
    """Return the V3.7.1 historical cache for ``symbol``.

    If the on-disk cache is the wrong schema_version (e.g. the legacy v360
    payload from V3.6.x), this function will rebuild via yfinance when
    ``auto_rebuild`` is True. Network failures fall back to returning the
    legacy payload with a `stale_schema` flag so callers can decide.
    """
    path = historical_cache_path(symbol)
    if not path.exists() and auto_rebuild:
        try:
            return write_historical_cache(symbol)
        except Exception as e:
            return {"path": str(path), "data": None, "rebuild_error": repr(e)}
    if not path.exists():
        return {"path": str(path), "data": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("schema_version") != SCHEMA_VERSION:
            if auto_rebuild:
                try:
                    return write_historical_cache(symbol)
                except Exception as e:
                    return {
                        "path": str(path),
                        "data": payload,
                        "stale_schema": True,
                        "rebuild_error": repr(e),
                    }
            return {"path": str(path), "data": None, "stale_schema": True}
        return {"path": str(path), "data": _apply_company_specific_backfills(payload)}
    except Exception:
        return {"path": str(path), "data": None}


def historical_cache_to_tables(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    tables = {}
    for statement_name, entries in (payload.get("statements") or {}).items():
        rows = {}
        years = []
        for entry in entries or []:
            year = entry.get("fiscal_year")
            if year is None:
                continue
            years.append(year)
            for field_key, meta in (entry.get("fields") or {}).items():
                rows.setdefault(field_key, {})[year] = meta.get("value")
        years = sorted(set(years))
        tables[statement_name] = {"years": years, "rows": rows}
    return tables


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch annual historical financial statements into V3.6 cache.")
    parser.add_argument("symbol")
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()
    result = write_historical_cache(args.symbol, max_years=args.years)
    print(result["path"])
