"""Stock fundamentals, technicals, IPO, market status, and SEC filing handlers.

All handlers are synchronous; async Polygon client calls are bridged via
PolygonMarketClient.sync_* wrapper methods that create a dedicated event loop
per invocation (safe for Lambda's single-threaded execution model).
"""

import json
from typing import Optional

from src.ingestion.polygon_client import PolygonMarketClient
from src.models.base import APIResponse
from src.models.stocks import (
    FloatData,
    IPOEvent,
    IncomeStatement,
    MarketStatus,
    SECFiling,
    ShortInterestData,
    ShortVolumeData,
    StockDetail,
    StockRatios,
    StockSnapshot,
    TechnicalIndicatorPoint,
    TechnicalIndicators,
)
from src.utils.errors import ExternalAPIError, NotFoundError, ValidationError
from src.utils.logging import logger


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _response(status_code: int, body: dict) -> dict:
    """Format API response with JSON string body and CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def _validate_symbol(symbol: str) -> str:
    """Return the upper-cased symbol or raise ValidationError."""
    if not symbol or not symbol.strip():
        raise ValidationError("Stock symbol is required", field="symbol")
    cleaned = symbol.strip().upper()
    if len(cleaned) > 10 or not cleaned.isalpha():
        raise ValidationError(
            f"Invalid stock symbol: {symbol!r}. Must be 1–10 alphabetic characters.",
            field="symbol",
        )
    return cleaned


def _build_snapshot(raw: Optional[dict]) -> Optional[StockSnapshot]:
    if not raw:
        return None
    return StockSnapshot(
        symbol=raw.get("symbol", ""),
        price=raw.get("price", 0.0),
        change=raw.get("change", 0.0),
        changePercent=raw.get("changePercent", 0.0),
        volume=raw.get("volume", 0),
        latestTradingDay=raw.get("latestTradingDay", ""),
    )


def _build_ratios(raw: Optional[dict]) -> Optional[StockRatios]:
    if not raw:
        return None
    return StockRatios(
        ticker=raw.get("ticker"),
        date=raw.get("date"),
        price=raw.get("price"),
        market_cap=raw.get("market_cap"),
        enterprise_value=raw.get("enterprise_value"),
        earnings_per_share=raw.get("earnings_per_share"),
        price_to_earnings=raw.get("price_to_earnings"),
        price_to_book=raw.get("price_to_book"),
        price_to_sales=raw.get("price_to_sales"),
        dividend_yield=raw.get("dividend_yield"),
        return_on_assets=raw.get("return_on_assets"),
        return_on_equity=raw.get("return_on_equity"),
        debt_to_equity=raw.get("debt_to_equity"),
        current=raw.get("current"),
        quick=raw.get("quick"),
        cash=raw.get("cash"),
        ev_to_ebitda=raw.get("ev_to_ebitda"),
        free_cash_flow=raw.get("free_cash_flow"),
        average_volume=raw.get("average_volume"),
    )


def _build_short_interest(raw: Optional[dict]) -> Optional[ShortInterestData]:
    if not raw:
        return None
    return ShortInterestData(
        ticker=raw.get("ticker"),
        short_interest=raw.get("short_interest"),
        avg_daily_volume=raw.get("avg_daily_volume"),
        days_to_cover=raw.get("days_to_cover"),
        settlement_date=raw.get("settlement_date"),
    )


def _build_income_statement(raw: dict) -> IncomeStatement:
    return IncomeStatement(
        ticker=raw.get("ticker"),
        timeframe=raw.get("timeframe"),
        fiscal_year=raw.get("fiscal_year"),
        fiscal_period=raw.get("fiscal_period"),
        start_date=raw.get("start_date"),
        end_date=raw.get("end_date"),
        revenue=raw.get("revenue"),
        cost_of_revenue=raw.get("cost_of_revenue"),
        gross_profit=raw.get("gross_profit"),
        operating_income=raw.get("operating_income"),
        ebitda=raw.get("ebitda"),
        net_income_loss=raw.get("net_income_loss"),
        earnings_per_share_basic=raw.get("earnings_per_share_basic"),
        earnings_per_share_diluted=raw.get("earnings_per_share_diluted"),
        operating_expenses=raw.get("operating_expenses"),
        research_and_development=raw.get("research_and_development"),
        interest_expense=raw.get("interest_expense"),
        income_tax_expense=raw.get("income_tax_expense"),
    )


def _build_indicator_point(raw: dict) -> TechnicalIndicatorPoint:
    return TechnicalIndicatorPoint(
        timestamp=raw.get("timestamp"),
        value=raw.get("value"),
        signal=raw.get("signal"),
        histogram=raw.get("histogram"),
    )


def _build_ipo_event(raw: dict) -> IPOEvent:
    return IPOEvent(
        ticker=raw.get("ticker"),
        issuer_name=raw.get("issuer_name"),
        listing_date=raw.get("listing_date"),
        ipo_status=raw.get("ipo_status"),
        final_issue_price=raw.get("final_issue_price"),
        shares_outstanding=raw.get("shares_outstanding"),
        primary_exchange=raw.get("primary_exchange"),
        security_type=raw.get("security_type"),
        total_offer_size=raw.get("total_offer_size"),
    )


def _build_market_status(raw: dict) -> MarketStatus:
    exchanges = raw.get("exchanges", {})
    return MarketStatus(
        market=raw.get("market"),
        afterHours=raw.get("afterHours"),
        earlyHours=raw.get("earlyHours"),
        serverTime=raw.get("serverTime"),
        nasdaq=exchanges.get("nasdaq"),
        nyse=exchanges.get("nyse"),
        otc=exchanges.get("otc"),
    )


def _build_sec_filing(raw: dict) -> SECFiling:
    return SECFiling(
        accession_number=raw.get("accession_number"),
        cik=raw.get("cik"),
        ticker=raw.get("ticker"),
        issuer_name=raw.get("issuer_name"),
        filing_date=raw.get("filing_date"),
        form_type=raw.get("form_type"),
        filing_url=raw.get("filing_url"),
    )


# ---------------------------------------------------------------------------
# Public handlers
# ---------------------------------------------------------------------------


def get_stock_detail(symbol: str) -> dict:
    """Return combined snapshot + ratios + latest short interest for a stock.

    GET /wall-street/stocks/{symbol}
    """
    symbol = _validate_symbol(symbol)
    logger.info("Fetching stock detail", symbol=symbol)

    client = PolygonMarketClient()
    raw = client.sync_get_stock_detail(symbol)

    snapshot = _build_snapshot(raw.get("snapshot"))
    ratios = _build_ratios(raw.get("ratios"))
    short_interest = _build_short_interest(raw.get("shortInterest"))

    if snapshot is None:
        raise NotFoundError("Stock", symbol)

    detail = StockDetail(
        symbol=symbol,
        snapshot=snapshot,
        ratios=ratios,
        shortInterest=short_interest,
    )

    return _response(
        200,
        APIResponse(success=True, data=detail.model_dump(mode="json")).model_dump(mode="json"),
    )


def get_stock_ratios(symbol: str) -> dict:
    """Return financial ratios for a stock.

    GET /wall-street/stocks/{symbol}/ratios
    """
    symbol = _validate_symbol(symbol)
    logger.info("Fetching stock ratios", symbol=symbol)

    client = PolygonMarketClient()
    raw = client.sync_get_ratios(symbol)

    if raw is None:
        raise NotFoundError("StockRatios", symbol)

    ratios = _build_ratios(raw)

    return _response(
        200,
        APIResponse(success=True, data=ratios.model_dump(mode="json")).model_dump(mode="json"),
    )


def get_stock_financials(symbol: str, timeframe: str = "annual") -> dict:
    """Return income statement history for a stock.

    GET /wall-street/stocks/{symbol}/financials?timeframe=annual
    Supported timeframe values: annual, quarterly
    """
    symbol = _validate_symbol(symbol)

    allowed_timeframes = {"annual", "quarterly"}
    if timeframe not in allowed_timeframes:
        raise ValidationError(
            f"Invalid timeframe {timeframe!r}. Must be one of: {', '.join(sorted(allowed_timeframes))}",
            field="timeframe",
        )

    logger.info("Fetching stock financials", symbol=symbol, timeframe=timeframe)

    client = PolygonMarketClient()
    raw_list = client.sync_get_income_statements(symbol, timeframe=timeframe, limit=4)

    statements = [_build_income_statement(r) for r in raw_list]

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "symbol": symbol,
                "timeframe": timeframe,
                "statements": [s.model_dump(mode="json") for s in statements],
            },
        ).model_dump(mode="json"),
    )


def get_stock_short_interest(symbol: str) -> dict:
    """Return short interest and short volume history for a stock.

    GET /wall-street/stocks/{symbol}/short-interest
    """
    symbol = _validate_symbol(symbol)
    logger.info("Fetching short interest", symbol=symbol)

    client = PolygonMarketClient()
    si_raw = client.sync_get_short_interest(symbol, limit=5)
    sv_raw = client.sync_get_short_volume(symbol, limit=5)
    float_raw = client.sync_get_float(symbol)

    short_interest = [
        ShortInterestData(
            ticker=r.get("ticker"),
            short_interest=r.get("short_interest"),
            avg_daily_volume=r.get("avg_daily_volume"),
            days_to_cover=r.get("days_to_cover"),
            settlement_date=r.get("settlement_date"),
        )
        for r in si_raw
    ]

    short_volume = [
        ShortVolumeData(
            ticker=r.get("ticker"),
            date=r.get("date"),
            short_volume=r.get("short_volume"),
            total_volume=r.get("total_volume"),
            short_volume_ratio=r.get("short_volume_ratio"),
        )
        for r in sv_raw
    ]

    float_data = (
        FloatData(
            ticker=float_raw.get("ticker"),
            effective_date=float_raw.get("effective_date"),
            free_float=float_raw.get("free_float"),
            free_float_percent=float_raw.get("free_float_percent"),
        )
        if float_raw
        else None
    )

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "symbol": symbol,
                "shortInterest": [s.model_dump(mode="json") for s in short_interest],
                "shortVolume": [s.model_dump(mode="json") for s in short_volume],
                "float": float_data.model_dump(mode="json") if float_data else None,
            },
        ).model_dump(mode="json"),
    )


def get_stock_technicals(symbol: str) -> dict:
    """Return SMA-50, EMA-20, MACD, and RSI-14 for a stock.

    GET /wall-street/stocks/{symbol}/technicals
    """
    symbol = _validate_symbol(symbol)
    logger.info("Fetching stock technicals", symbol=symbol)

    client = PolygonMarketClient()

    # Fetch all four indicators; partial failures surface as empty lists rather
    # than aborting the entire request so the client can still render available data.
    def _safe_fetch(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ExternalAPIError as exc:
            logger.warning("Technical indicator fetch failed", error=str(exc))
            return []

    sma_raw = _safe_fetch(client.sync_get_sma, symbol, window=50)
    ema_raw = _safe_fetch(client.sync_get_ema, symbol, window=20)
    macd_raw = _safe_fetch(client.sync_get_macd, symbol)
    rsi_raw = _safe_fetch(client.sync_get_rsi, symbol, window=14)

    indicators = TechnicalIndicators(
        symbol=symbol,
        sma_50=[_build_indicator_point(p) for p in sma_raw],
        ema_20=[_build_indicator_point(p) for p in ema_raw],
        macd=[_build_indicator_point(p) for p in macd_raw],
        rsi_14=[_build_indicator_point(p) for p in rsi_raw],
    )

    return _response(
        200,
        APIResponse(success=True, data=indicators.model_dump(mode="json")).model_dump(mode="json"),
    )


def get_ipos(days_ahead: int = 30) -> dict:
    """Return upcoming IPO calendar.

    GET /wall-street/ipos?daysAhead=30
    """
    if days_ahead < 0 or days_ahead > 365:
        raise ValidationError(
            "daysAhead must be between 0 and 365", field="daysAhead"
        )

    logger.info("Fetching IPO calendar", days_ahead=days_ahead)

    client = PolygonMarketClient()
    raw_list = client.sync_get_ipos(limit=50, days_ahead=days_ahead)

    events = [_build_ipo_event(r) for r in raw_list]

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "daysAhead": days_ahead,
                "count": len(events),
                "ipos": [e.model_dump(mode="json") for e in events],
            },
        ).model_dump(mode="json"),
    )


def get_market_status() -> dict:
    """Return current market open/close status.

    GET /wall-street/market-status
    """
    logger.info("Fetching market status")

    client = PolygonMarketClient()
    raw = client.sync_get_market_status()

    if raw is None:
        raise ExternalAPIError("Polygon", "Market status endpoint returned no data")

    status = _build_market_status(raw)

    return _response(
        200,
        APIResponse(success=True, data=status.model_dump(mode="json")).model_dump(mode="json"),
    )


def get_stock_filings(symbol: str, limit: int = 10) -> dict:
    """Return recent SEC filings for a stock.

    GET /wall-street/stocks/{symbol}/filings?limit=10
    """
    symbol = _validate_symbol(symbol)

    if limit < 1 or limit > 50:
        raise ValidationError("limit must be between 1 and 50", field="limit")

    logger.info("Fetching SEC filings", symbol=symbol, limit=limit)

    client = PolygonMarketClient()
    raw_list = client.sync_get_filings(symbol, limit=limit)

    filings = [_build_sec_filing(r) for r in raw_list]

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "symbol": symbol,
                "count": len(filings),
                "filings": [f.model_dump(mode="json") for f in filings],
            },
        ).model_dump(mode="json"),
    )
