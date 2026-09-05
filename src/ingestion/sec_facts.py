"""Fundamentals from SEC XBRL company facts (Polygon migration, slice 3).

data.sec.gov/api/xbrl/companyfacts is the PRIMARY source Polygon's paid
financials endpoints resell: every ratio here is computed from audited filing
values. Free, keyless; requires a User-Agent and polite request rates.

Public surface mirrors what the stocks handlers consume:
  get_ratios(symbol, price)  -> Polygon-ratios-shaped dict (nullable fields)
  trailing_eps(symbol)       -> float | None (sum of last 4 quarterly diluted EPS)
  shares_outstanding(symbol) -> float | None
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from src.utils.logging import logger

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_UA = {"User-Agent": "TradeStreak data research contact@tradestreak.net"}

_cik_by_ticker: Optional[Dict[str, int]] = None
_facts_cache: Dict[str, tuple] = {}          # symbol -> (fetched_at, facts)
_FACTS_TTL = 6 * 3600


async def _ticker_to_cik(symbol: str) -> Optional[int]:
    global _cik_by_ticker
    if _cik_by_ticker is None:
        async with httpx.AsyncClient(timeout=30, headers=_UA) as c:
            resp = await c.get(_TICKERS_URL)
            resp.raise_for_status()
            raw = resp.json()
        _cik_by_ticker = {row["ticker"].upper(): int(row["cik_str"])
                          for row in raw.values()}
    sym = symbol.upper()
    # SEC uses dashes for share classes where brokers use dots (BRK.B -> BRK-B).
    return _cik_by_ticker.get(sym) or _cik_by_ticker.get(sym.replace(".", "-"))


async def _company_facts(symbol: str) -> Optional[Dict]:
    cached = _facts_cache.get(symbol.upper())
    if cached and time.time() - cached[0] < _FACTS_TTL:
        return cached[1]
    cik = await _ticker_to_cik(symbol)
    if cik is None:
        return None
    async with httpx.AsyncClient(timeout=30, headers=_UA) as c:
        resp = await c.get(_FACTS_URL.format(cik=cik))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        facts = resp.json()
    _facts_cache[symbol.upper()] = (time.time(), facts)
    return facts


def and_first(facts: Dict, taxonomy: str, tag: str) -> List[Dict]:
    """Values list from the first (usually only) unit of a tag."""
    units = (facts.get("facts", {}).get(taxonomy, {}).get(tag, {})
             .get("units", {}) or {})
    for _, values in units.items():
        return values
    return []


def _latest_annual(facts: Dict, tag: str, taxonomy: str = "us-gaap") -> Optional[float]:
    """Most recent full-year (10-K, ~12-month frame) value for a tag."""
    best = None
    for v in and_first(facts, taxonomy, tag):
        if v.get("form") not in ("10-K", "20-F") or v.get("val") is None:
            continue
        start, end = v.get("start"), v.get("end")
        if start and end:
            try:
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                if not 300 < days < 400:
                    continue
            except ValueError:
                continue
        if best is None or (v.get("end") or "") > (best.get("end") or ""):
            best = v
    return float(best["val"]) if best else None


def _latest_instant(facts: Dict, tag: str, taxonomy: str = "us-gaap") -> Optional[float]:
    """Most recent point-in-time (balance-sheet style) value for a tag."""
    best = None
    for v in and_first(facts, taxonomy, tag):
        if v.get("val") is None:
            continue
        if best is None or (v.get("end") or "") > (best.get("end") or ""):
            best = v
    return float(best["val"]) if best else None


def _first_present(facts: Dict, tags: List[str],
                   annual: bool = True, taxonomy: str = "us-gaap") -> Optional[float]:
    for tag in tags:
        val = (_latest_annual if annual else _latest_instant)(facts, tag, taxonomy)
        if val is not None:
            return val
    return None


def trailing_eps_from_facts(facts: Dict) -> Optional[float]:
    """Sum of the four most recent quarterly diluted EPS values (10-Q/10-K)."""
    quarters = []
    for v in and_first(facts, "us-gaap", "EarningsPerShareDiluted"):
        start, end = v.get("start"), v.get("end")
        if v.get("val") is None or not start or not end:
            continue
        try:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        except ValueError:
            continue
        if 80 <= days <= 100:  # a quarter
            quarters.append((end, float(v["val"])))
    if len(quarters) < 4:
        return None
    quarters.sort()
    seen = dict(quarters)  # dedupe amended filings by period end
    last4 = sorted(seen.items())[-4:]
    return round(sum(v for _, v in last4), 4) if len(last4) == 4 else None


async def trailing_eps(symbol: str) -> Optional[float]:
    facts = await _company_facts(symbol)
    return trailing_eps_from_facts(facts) if facts else None


async def shares_outstanding(symbol: str) -> Optional[float]:
    facts = await _company_facts(symbol)
    if not facts:
        return None
    return _first_present(
        facts,
        ["EntityCommonStockSharesOutstanding"],
        annual=False, taxonomy="dei",
    ) or _first_present(facts, ["CommonStockSharesOutstanding"], annual=False)


def ratios_from_facts(facts: Dict, symbol: str,
                      price: Optional[float]) -> Dict[str, Any]:
    """Polygon-ratios-shaped dict computed from audited filing values.
    Any component that can't be sourced comes back None (never fabricated)."""
    # EPS resolution chain: trailing 4 quarters -> latest annual tag ->
    # computed NetIncome / weighted diluted shares (filers like KO tag EPS
    # only in their custom namespace, but these components are standard).
    eps = trailing_eps_from_facts(facts) or _latest_annual(facts, "EarningsPerShareDiluted")
    if eps is None:
        ni = _first_present(facts, ["NetIncomeLoss"])
        wshares = _first_present(
            facts, ["WeightedAverageNumberOfDilutedSharesOutstanding",
                    "WeightedAverageNumberOfSharesOutstandingBasic"])
        if ni is not None and wshares:
            eps = round(ni / wshares, 4)
    shares = (_first_present(facts, ["EntityCommonStockSharesOutstanding"],
                             annual=False, taxonomy="dei")
              or _first_present(facts, ["CommonStockSharesOutstanding"], annual=False))
    revenue = _first_present(facts, [
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
        "SalesRevenueNet"])
    net_income = _first_present(facts, ["NetIncomeLoss"])
    equity = _first_present(
        facts, ["StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        annual=False)
    assets = _first_present(facts, ["Assets"], annual=False)
    current_assets = _first_present(facts, ["AssetsCurrent"], annual=False)
    current_liabilities = _first_present(facts, ["LiabilitiesCurrent"], annual=False)
    long_term_debt = _first_present(
        facts, ["LongTermDebtNoncurrent", "LongTermDebt"], annual=False)
    op_cash = _first_present(facts, ["NetCashProvidedByUsedInOperatingActivities"])
    capex = _first_present(facts, [
        "PaymentsToAcquirePropertyPlantAndEquipment"])
    dividends = _first_present(facts, ["PaymentsOfDividendsCommonStock",
                                       "PaymentsOfDividends"])

    market_cap = price * shares if price and shares else None

    def ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return round(a / b, 4) if a is not None and b else None

    return {
        "ticker": symbol.upper(),
        "date": date.today().isoformat(),
        "price": price,
        "market_cap": market_cap,
        "enterprise_value": None,
        "earnings_per_share": eps,
        "price_to_earnings": ratio(price, eps) if eps and eps > 0 else None,
        "price_to_book": ratio(market_cap, equity),
        "price_to_sales": ratio(market_cap, revenue),
        "dividend_yield": ratio(dividends, market_cap),
        "return_on_assets": ratio(net_income, assets),
        "return_on_equity": ratio(net_income, equity),
        "debt_to_equity": ratio(long_term_debt, equity),
        "current": ratio(current_assets, current_liabilities),
        "quick": None,
        "cash": None,
        "ev_to_ebitda": None,
        "free_cash_flow": (op_cash - capex) if op_cash is not None and capex is not None else None,
        "average_volume": None,
    }


async def get_ratios(symbol: str, price: Optional[float]) -> Optional[Dict]:
    facts = await _company_facts(symbol)
    if not facts:
        return None
    try:
        return ratios_from_facts(facts, symbol, price)
    except Exception as e:  # noqa: BLE001 — never let math kill the endpoint
        logger.warning("SEC ratios computation failed", symbol=symbol, error=str(e))
        return None
