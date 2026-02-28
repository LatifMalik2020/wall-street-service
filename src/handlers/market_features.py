"""Market features API handlers: indices comparison, featured ETFs, and daily buzz.

Endpoints:
    GET /wall-street/indices/comparison?symbols=SPX,NDX&period=1M
    GET /wall-street/etfs/featured
    GET /wall-street/daily-buzz

Data source: Polygon.io (aggregates, bulk snapshots, market movers).
AI summary: AWS Bedrock Claude Haiku (falls back to template on failure).
"""

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from src.ingestion.polygon_client import PolygonMarketClient
from src.models.base import APIResponse
from src.utils.errors import ExternalAPIError, ValidationError
from src.utils.logging import logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Polygon uses "I:" prefix for index tickers
_INDEX_TICKER_MAP: dict[str, dict] = {
    "SPX": {"polygonTicker": "I:SPX", "name": "S&P 500"},
    "NDX": {"polygonTicker": "I:NDX", "name": "Nasdaq-100"},
    "DJI": {"polygonTicker": "I:DJI", "name": "Dow Jones Industrial Average"},
    "RUT": {"polygonTicker": "I:RUT", "name": "Russell 2000"},
    "VIX": {"polygonTicker": "I:VIX", "name": "CBOE Volatility Index"},
}

_VALID_PERIODS = frozenset({"5D", "1M", "3M", "YTD", "1Y", "5Y"})

_ETF_CATALOG: list[dict] = [
    {"symbol": "SPY",  "name": "SPDR S&P 500 ETF Trust",          "category": "Large Cap"},
    {"symbol": "QQQ",  "name": "Invesco QQQ Trust",               "category": "Technology"},
    {"symbol": "DIA",  "name": "SPDR Dow Jones Industrial Avg",    "category": "Large Cap"},
    {"symbol": "IWM",  "name": "iShares Russell 2000 ETF",         "category": "Small Cap"},
    {"symbol": "VTI",  "name": "Vanguard Total Stock Market ETF",  "category": "Broad Market"},
    {"symbol": "ARKK", "name": "ARK Innovation ETF",               "category": "Innovation"},
    {"symbol": "XLF",  "name": "Financial Select Sector SPDR",     "category": "Financials"},
    {"symbol": "XLK",  "name": "Technology Select Sector SPDR",    "category": "Technology"},
    {"symbol": "GLD",  "name": "SPDR Gold Trust",                  "category": "Commodities"},
    {"symbol": "TLT",  "name": "iShares 20+ Year Treasury Bond",   "category": "Fixed Income"},
    {"symbol": "VNQ",  "name": "Vanguard Real Estate ETF",         "category": "Real Estate"},
    {"symbol": "EEM",  "name": "iShares MSCI Emerging Markets",    "category": "International"},
]

_ETF_SPOTLIGHT_SYMBOL = "QQQ"
_ETF_SPOTLIGHT_DESCRIPTION = (
    "Tracks the Nasdaq-100 Index, focusing on large-cap technology companies "
    "across sectors such as software, semiconductors, and e-commerce."
)

_BEDROCK_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
_BEDROCK_MAX_TOKENS = 300


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


def _period_to_date_range(period: str) -> tuple[str, str, str, int]:
    """Map a period string to (from_date, to_date, timespan, multiplier).

    Returns:
        from_date: ISO date string (YYYY-MM-DD)
        to_date: ISO date string (YYYY-MM-DD)
        timespan: Polygon timespan ('minute', 'hour', 'day', 'week')
        multiplier: Polygon bar multiplier (integer)
    """
    today = date.today()

    if period == "5D":
        from_date = (today - timedelta(days=7)).isoformat()  # +buffer for weekends
        return from_date, today.isoformat(), "hour", 1

    if period == "1M":
        from_date = (today - timedelta(days=30)).isoformat()
        return from_date, today.isoformat(), "day", 1

    if period == "3M":
        from_date = (today - timedelta(days=90)).isoformat()
        return from_date, today.isoformat(), "day", 1

    if period == "YTD":
        from_date = date(today.year, 1, 1).isoformat()
        return from_date, today.isoformat(), "day", 1

    if period == "1Y":
        from_date = (today - timedelta(days=365)).isoformat()
        return from_date, today.isoformat(), "day", 1

    if period == "5Y":
        from_date = (today - timedelta(days=5 * 365)).isoformat()
        return from_date, today.isoformat(), "week", 1

    raise ValidationError(
        f"Invalid period {period!r}. Must be one of: {', '.join(sorted(_VALID_PERIODS))}",
        field="period",
    )


def _normalize_series(bars: list[dict]) -> list[float]:
    """Convert a list of Polygon aggregate bars to percent-change-from-first values."""
    if not bars:
        return []

    base_close = bars[0].get("c")
    if not base_close:
        return [0.0] * len(bars)

    normalized: list[float] = []
    for bar in bars:
        close = bar.get("c", base_close)
        pct = round(((close - base_close) / base_close) * 100, 4)
        normalized.append(pct)

    return normalized


def _bar_date_label(bar: dict, timespan: str) -> str:
    """Return a human-readable date/time label for a Polygon aggregate bar."""
    ts_ms: int = bar.get("t", 0)
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    if timespan == "hour":
        return dt.strftime("%Y-%m-%dT%H:%M")
    return dt.strftime("%Y-%m-%d")


def _parse_symbols(symbols_param: Optional[str]) -> list[str]:
    """Parse and validate the ?symbols= query parameter."""
    if not symbols_param:
        # Default to the two most common indices
        return ["SPX", "NDX"]

    raw_symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]

    if not raw_symbols:
        raise ValidationError("At least one symbol is required", field="symbols")

    if len(raw_symbols) > 5:
        raise ValidationError(
            "Maximum 5 symbols allowed per request", field="symbols"
        )

    invalid = [s for s in raw_symbols if s not in _INDEX_TICKER_MAP]
    if invalid:
        valid_keys = ", ".join(sorted(_INDEX_TICKER_MAP.keys()))
        raise ValidationError(
            f"Unknown index symbol(s): {', '.join(invalid)}. Valid options: {valid_keys}",
            field="symbols",
        )

    return raw_symbols


def _generate_bedrock_summary(
    gainers: list[dict],
    losers: list[dict],
    index_summary: dict,
) -> Optional[str]:
    """Call AWS Bedrock Claude Haiku to generate a market recap.

    Returns None if Bedrock is not configured or the call fails.
    """
    try:
        bedrock = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

        # Build a compact context string for the prompt
        gainer_lines = "; ".join(
            f"{g.get('symbol', '')} +{g.get('changePercent', 0):.2f}%"
            for g in gainers[:5]
        )
        loser_lines = "; ".join(
            f"{l.get('symbol', '')} {l.get('changePercent', 0):.2f}%"
            for l in losers[:5]
        )

        index_lines = "; ".join(
            f"{sym}: {info.get('changePercent', 0):+.2f}%"
            for sym, info in index_summary.items()
        )

        today_str = date.today().strftime("%B %d, %Y")

        prompt = (
            f"Today is {today_str}. Write a 2-3 sentence US stock market daily recap "
            f"suitable for a retail investing app. Be concise, factual, and informative.\n\n"
            f"Market indices: {index_lines or 'data unavailable'}.\n"
            f"Top gainers: {gainer_lines or 'none'}.\n"
            f"Top losers: {loser_lines or 'none'}.\n\n"
            f"Write ONLY the recap paragraph. No headlines, no bullet points."
        )

        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": _BEDROCK_MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            }
        )

        response = bedrock.invoke_model(
            modelId=_BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        result = json.loads(response["body"].read())
        content_blocks = result.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                return block["text"].strip()

        return None

    except (ClientError, NoCredentialsError) as exc:
        logger.warning("Bedrock unavailable, using template summary", error=str(exc))
        return None
    except Exception as exc:
        logger.warning("Bedrock call failed", error=str(exc))
        return None


def _template_summary(
    gainers: list[dict],
    losers: list[dict],
    index_summary: dict,
) -> str:
    """Generate a rule-based summary when Bedrock is unavailable."""
    today_str = date.today().strftime("%B %d, %Y")

    # Determine overall market direction from index data
    positive_indices = sum(
        1 for info in index_summary.values() if info.get("changePercent", 0) > 0
    )
    total_indices = len(index_summary) or 1
    market_direction = "mixed" if positive_indices < total_indices else "higher"
    if positive_indices == 0:
        market_direction = "lower"

    top_gainer = gainers[0] if gainers else None
    top_loser = losers[0] if losers else None

    parts: list[str] = [
        f"U.S. equities traded {market_direction} on {today_str}."
    ]

    if top_gainer:
        sym = top_gainer.get("symbol", "")
        pct = top_gainer.get("changePercent", 0)
        parts.append(
            f"{sym} led the session's gainers, advancing {pct:.2f}%."
        )

    if top_loser:
        sym = top_loser.get("symbol", "")
        pct = abs(top_loser.get("changePercent", 0))
        parts.append(
            f"{sym} was among the notable decliners, falling {pct:.2f}%."
        )

    return " ".join(parts)


def _extract_headline(summary: str) -> str:
    """Derive a short headline from the summary text (first sentence, max 80 chars)."""
    if not summary:
        return "Daily Market Summary"
    first_sentence = summary.split(".")[0].strip()
    if len(first_sentence) > 80:
        return first_sentence[:77] + "..."
    return first_sentence


def _format_mover(ticker_snapshot: dict) -> dict:
    """Extract mover fields from a Polygon ticker snapshot."""
    day = ticker_snapshot.get("day", {})
    prev_day = ticker_snapshot.get("prevDay", {})

    symbol = ticker_snapshot.get("ticker", "")
    current_price = day.get("c") or ticker_snapshot.get("lastTrade", {}).get("p", 0)
    previous_close = prev_day.get("c", 0)
    change_pct = ticker_snapshot.get("todaysChangePerc", 0)

    return {
        "symbol": symbol,
        "companyName": ticker_snapshot.get("name", symbol),
        "price": float(current_price) if current_price else None,
        "changePercent": round(float(change_pct), 2),
    }


# ---------------------------------------------------------------------------
# Public handlers
# ---------------------------------------------------------------------------


def get_indices_comparison(
    symbols_param: Optional[str] = None,
    period: str = "1M",
) -> dict:
    """Return normalized historical bars for major indices.

    GET /wall-street/indices/comparison?symbols=SPX,NDX&period=1M

    Each index is normalized to percent change from the period start.
    The response includes per-index current value and change percent,
    plus an aligned list of data points for charting.
    """
    if period not in _VALID_PERIODS:
        raise ValidationError(
            f"Invalid period {period!r}. Must be one of: {', '.join(sorted(_VALID_PERIODS))}",
            field="period",
        )

    symbols = _parse_symbols(symbols_param)
    from_date, to_date, timespan, multiplier = _period_to_date_range(period)

    logger.info(
        "Fetching index comparison",
        symbols=symbols,
        period=period,
        from_date=from_date,
        to_date=to_date,
    )

    client = PolygonMarketClient()

    # Fetch aggregates for all requested symbols
    all_bars: dict[str, list[dict]] = {}
    for symbol in symbols:
        polygon_ticker = _INDEX_TICKER_MAP[symbol]["polygonTicker"]
        try:
            bars = client.sync_get_index_aggregates(
                ticker=polygon_ticker,
                multiplier=multiplier,
                timespan=timespan,
                from_date=from_date,
                to_date=to_date,
            )
            all_bars[symbol] = bars
        except ExternalAPIError as exc:
            logger.warning(
                "Index aggregates fetch failed",
                symbol=symbol,
                error=str(exc),
            )
            all_bars[symbol] = []

    # Compute per-index summary (current value and total change percent)
    indices_meta: dict[str, dict] = {}
    for symbol in symbols:
        bars = all_bars[symbol]
        index_name = _INDEX_TICKER_MAP[symbol]["name"]

        current_value: Optional[float] = None
        change_percent: Optional[float] = None

        if bars:
            first_close = bars[0].get("c")
            last_close = bars[-1].get("c")
            if first_close and last_close and first_close != 0:
                change_percent = round(
                    ((last_close - first_close) / first_close) * 100, 4
                )
            current_value = float(last_close) if last_close else None

        indices_meta[symbol] = {
            "name": index_name,
            "currentValue": current_value,
            "changePercent": change_percent,
        }

    # Build aligned data points using the union of all timestamps.
    # Use the symbol with the most bars as the reference timeline.
    reference_symbol = max(symbols, key=lambda s: len(all_bars.get(s, [])))
    reference_bars = all_bars.get(reference_symbol, [])

    # Normalise each series independently
    normalized: dict[str, list[float]] = {
        sym: _normalize_series(all_bars.get(sym, []))
        for sym in symbols
    }

    data_points: list[dict] = []
    for i, bar in enumerate(reference_bars):
        point: dict = {"date": _bar_date_label(bar, timespan)}
        for sym in symbols:
            series = normalized.get(sym, [])
            point[sym] = series[i] if i < len(series) else None
        data_points.append(point)

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "period": period,
                "indices": indices_meta,
                "dataPoints": data_points,
            },
        ).model_dump(mode="json"),
    )


def get_featured_etfs() -> dict:
    """Return curated ETF list with live Polygon snapshot data.

    GET /wall-street/etfs/featured

    Uses the Polygon bulk snapshot endpoint to retrieve all ETFs in one call.
    """
    logger.info("Fetching featured ETFs", count=len(_ETF_CATALOG))

    etf_symbols = [etf["symbol"] for etf in _ETF_CATALOG]
    client = PolygonMarketClient()

    snapshots: dict[str, dict] = {}
    try:
        raw_snapshots = client.sync_get_bulk_snapshot(etf_symbols)
        for snap in raw_snapshots:
            ticker = snap.get("ticker", "")
            if ticker:
                snapshots[ticker] = snap
    except ExternalAPIError as exc:
        logger.warning("Bulk ETF snapshot failed", error=str(exc))
        # Continue with empty snapshots; ETF list will still return with null prices

    featured: list[dict] = []
    for etf_meta in _ETF_CATALOG:
        symbol = etf_meta["symbol"]
        snap = snapshots.get(symbol, {})

        day = snap.get("day", {})
        prev_day = snap.get("prevDay", {})
        last_trade = snap.get("lastTrade", {})

        current_price = day.get("c") or last_trade.get("p")
        previous_close = prev_day.get("c")
        change_pct = snap.get("todaysChangePerc", None)

        if current_price and previous_close and change_pct is None:
            change_pct = ((current_price - previous_close) / previous_close) * 100

        featured.append(
            {
                "symbol": symbol,
                "name": etf_meta["name"],
                "category": etf_meta["category"],
                "price": round(float(current_price), 2) if current_price else None,
                "changePercent": round(float(change_pct), 4) if change_pct is not None else None,
                "volume": int(day.get("v", 0)),
            }
        )

    # Spotlight card — use the configured symbol, with a static description
    spotlight_snap = snapshots.get(_ETF_SPOTLIGHT_SYMBOL, {})
    spotlight_meta = next(
        (e for e in _ETF_CATALOG if e["symbol"] == _ETF_SPOTLIGHT_SYMBOL),
        {"symbol": _ETF_SPOTLIGHT_SYMBOL, "name": "Invesco QQQ Trust"},
    )

    spotlight = {
        "symbol": _ETF_SPOTLIGHT_SYMBOL,
        "name": spotlight_meta["name"],
        "description": _ETF_SPOTLIGHT_DESCRIPTION,
        "price": None,
        "changePercent": None,
    }
    if spotlight_snap:
        sp_day = spotlight_snap.get("day", {})
        sp_price = sp_day.get("c") or spotlight_snap.get("lastTrade", {}).get("p")
        sp_change = spotlight_snap.get("todaysChangePerc")
        spotlight["price"] = round(float(sp_price), 2) if sp_price else None
        spotlight["changePercent"] = (
            round(float(sp_change), 4) if sp_change is not None else None
        )

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "featured": featured,
                "spotlight": spotlight,
            },
        ).model_dump(mode="json"),
    )


def get_daily_buzz() -> dict:
    """Return AI-generated daily market recap with movers.

    GET /wall-street/daily-buzz

    Step 1: Fetch top gainers/losers from Polygon.
    Step 2: Attempt to get index data for context.
    Step 3: Generate summary via Bedrock; fall back to template on failure.
    """
    logger.info("Generating daily buzz")

    client = PolygonMarketClient()

    # Fetch market movers
    gainers_raw: list[dict] = []
    losers_raw: list[dict] = []
    try:
        gainers_raw, losers_raw = client.sync_get_market_movers()
    except ExternalAPIError as exc:
        logger.warning("Market movers fetch failed", error=str(exc))

    # Format movers for the response (top 5 each)
    gainers = [_format_mover(snap) for snap in gainers_raw[:5]]
    losers = [_format_mover(snap) for snap in losers_raw[:5]]

    # Lightweight index context for the AI prompt
    index_summary: dict = {}
    for symbol in ("SPX", "NDX"):
        try:
            bars = client.sync_get_index_aggregates(
                ticker=_INDEX_TICKER_MAP[symbol]["polygonTicker"],
                multiplier=1,
                timespan="day",
                from_date=(date.today() - timedelta(days=5)).isoformat(),
                to_date=date.today().isoformat(),
            )
            if bars and len(bars) >= 2:
                first = bars[0]["c"]
                last = bars[-1]["c"]
                if first:
                    change_pct = ((last - first) / first) * 100
                    index_summary[symbol] = {
                        "name": _INDEX_TICKER_MAP[symbol]["name"],
                        "currentValue": round(float(last), 2),
                        "changePercent": round(float(change_pct), 4),
                    }
        except ExternalAPIError:
            pass  # Non-fatal — index context is best-effort for the AI prompt

    # Generate AI summary (falls back to template automatically)
    ai_summary = _generate_bedrock_summary(gainers, losers, index_summary)
    summary_text = ai_summary if ai_summary else _template_summary(gainers, losers, index_summary)
    headline = _extract_headline(summary_text)

    # Headlines section — placeholder sourced from mover tickers
    headlines: list[dict] = []
    for mover in (gainers + losers)[:3]:
        sym = mover.get("symbol", "")
        pct = mover.get("changePercent", 0)
        direction = "surges" if pct > 0 else "falls"
        headlines.append(
            {
                "title": f"{sym} {direction} {abs(pct):.1f}% in today's session",
                "source": "Market Data",
            }
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "headline": headline,
                "body": summary_text,
                "generatedAt": generated_at,
                "generatedByAI": ai_summary is not None,
                "gainers": gainers,
                "losers": losers,
                "headlines": headlines,
                "indices": index_summary,
            },
        ).model_dump(mode="json"),
    )
