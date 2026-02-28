"""Polygon.io API client for stock prices and earnings calendar."""

import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List, Dict
import uuid

from src.models.earnings import EarningsEvent
from src.utils.config import get_settings
from src.utils.logging import logger
from src.utils.errors import ExternalAPIError


POLYGON_BASE_URL = "https://api.massive.com"


class PolygonMarketClient:
    """Client for Polygon.io stock data API (unlimited plan).

    Documentation: https://polygon.io/docs
    """

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.polygon_api_key
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=POLYGON_BASE_URL,
                timeout=30.0,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get current stock quote via Polygon snapshot."""
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return None

        try:
            response = await self.client.get(
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}"
            )
            response.raise_for_status()
            data = response.json()

            ticker_data = data.get("ticker", {})
            if not ticker_data:
                logger.warning("No snapshot data for symbol", symbol=symbol)
                return None

            day = ticker_data.get("day", {})
            prev_day = ticker_data.get("prevDay", {})
            last_trade = ticker_data.get("lastTrade", {})

            current_price = day.get("c", 0) or last_trade.get("p", 0)
            previous_close = prev_day.get("c", 0)
            change = current_price - previous_close if previous_close else 0
            change_pct = (change / previous_close * 100) if previous_close else 0

            return {
                "symbol": symbol.upper(),
                "price": float(current_price),
                "change": float(change),
                "changePercent": round(float(change_pct), 2),
                "volume": int(day.get("v", 0)),
                "latestTradingDay": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }

        except httpx.HTTPError as e:
            logger.error("Polygon quote error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_earnings_calendar(self, horizon: str = "3month") -> List[EarningsEvent]:
        """Get upcoming earnings calendar from Polygon.

        Uses the /v3/reference/tickers/types and vX/reference/financials endpoints.
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            # Calculate date range based on horizon
            now = datetime.now(timezone.utc)
            if horizon == "3month":
                end_date = now + timedelta(days=90)
            elif horizon == "6month":
                end_date = now + timedelta(days=180)
            else:
                end_date = now + timedelta(days=365)

            # Use Polygon's stock financials endpoint for earnings dates
            # Note: Polygon doesn't have a direct "earnings calendar" like Alpha Vantage
            # but we can get upcoming earnings from the ticker events endpoint
            response = await self.client.get(
                "/v3/reference/tickers",
                params={
                    "market": "stocks",
                    "active": "true",
                    "limit": 100,
                    "sort": "ticker",
                },
            )
            response.raise_for_status()

            # For now, return empty list - earnings data will come from FMP
            # which is already configured as a data source in the scheduler
            logger.info("Earnings calendar: using FMP as primary source")
            return []

        except httpx.HTTPError as e:
            logger.error("Polygon earnings error", error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def batch_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get quotes for multiple symbols (no rate limiting needed - unlimited plan)."""
        quotes = {}
        for symbol in symbols:
            try:
                quote = await self.get_quote(symbol)
                if quote:
                    quotes[symbol] = quote
            except ExternalAPIError:
                continue

        return quotes

    async def get_snapshot_all(self) -> List[Dict]:
        """Get snapshots for all US tickers at once (efficient for batch updates)."""
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"include_otc": "false"},
            )
            response.raise_for_status()
            data = response.json()

            return data.get("tickers", [])

        except httpx.HTTPError as e:
            logger.error("Polygon snapshot all error", error=str(e))
            return []

    # ------------------------------------------------------------------
    # Fundamentals & technicals
    # ------------------------------------------------------------------

    async def get_ratios(self, symbol: str) -> Optional[Dict]:
        """Get financial ratios for a ticker.

        GET /stocks/financials/v1/ratios?ticker={symbol}&limit=1
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return None

        try:
            response = await self.client.get(
                "/stocks/financials/v1/ratios",
                params={"ticker": symbol.upper(), "limit": 1},
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return results[0] if results else None

        except httpx.HTTPError as e:
            logger.error("Polygon ratios error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_income_statements(
        self, symbol: str, timeframe: str = "annual", limit: int = 4
    ) -> List[Dict]:
        """Get income statements for a ticker.

        GET /stocks/financials/v1/income-statements?tickers.any_of={symbol}&timeframe={timeframe}&limit={limit}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                "/stocks/financials/v1/income-statements",
                params={
                    "tickers.any_of": symbol.upper(),
                    "timeframe": timeframe,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except httpx.HTTPError as e:
            logger.error("Polygon income statements error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_short_interest(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get short interest data for a ticker.

        GET /stocks/v1/short-interest?ticker={symbol}&limit={limit}&sort=settlement_date.desc
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                "/stocks/v1/short-interest",
                params={
                    "ticker": symbol.upper(),
                    "limit": limit,
                    "sort": "settlement_date.desc",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except httpx.HTTPError as e:
            logger.error("Polygon short interest error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_short_volume(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get short volume data for a ticker.

        GET /stocks/v1/short-volume?ticker={symbol}&limit={limit}&sort=date.desc
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                "/stocks/v1/short-volume",
                params={
                    "ticker": symbol.upper(),
                    "limit": limit,
                    "sort": "date.desc",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except httpx.HTTPError as e:
            logger.error("Polygon short volume error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_float(self, symbol: str) -> Optional[Dict]:
        """Get float data for a ticker.

        GET /stocks/vX/float?ticker={symbol}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return None

        try:
            response = await self.client.get(
                "/stocks/vX/float",
                params={"ticker": symbol.upper()},
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return results[0] if results else None

        except httpx.HTTPError as e:
            logger.error("Polygon float error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    # ------------------------------------------------------------------
    # Technical indicators
    # ------------------------------------------------------------------

    async def get_sma(
        self,
        symbol: str,
        window: int = 50,
        timespan: str = "day",
        limit: int = 100,
    ) -> List[Dict]:
        """Get Simple Moving Average indicator values.

        GET /v1/indicators/sma/{symbol}?timespan={timespan}&adjusted=true&window={window}&series_type=close&limit={limit}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                f"/v1/indicators/sma/{symbol.upper()}",
                params={
                    "timespan": timespan,
                    "adjusted": "true",
                    "window": window,
                    "series_type": "close",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", {}).get("values", [])

        except httpx.HTTPError as e:
            logger.error("Polygon SMA error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_ema(
        self,
        symbol: str,
        window: int = 20,
        timespan: str = "day",
        limit: int = 100,
    ) -> List[Dict]:
        """Get Exponential Moving Average indicator values.

        GET /v1/indicators/ema/{symbol}?timespan={timespan}&adjusted=true&window={window}&series_type=close&limit={limit}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                f"/v1/indicators/ema/{symbol.upper()}",
                params={
                    "timespan": timespan,
                    "adjusted": "true",
                    "window": window,
                    "series_type": "close",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", {}).get("values", [])

        except httpx.HTTPError as e:
            logger.error("Polygon EMA error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_macd(
        self,
        symbol: str,
        timespan: str = "day",
        short_window: int = 12,
        long_window: int = 26,
        signal_window: int = 9,
        limit: int = 100,
    ) -> List[Dict]:
        """Get MACD indicator values.

        GET /v1/indicators/macd/{symbol}?timespan={timespan}&adjusted=true&short_window=12&long_window=26&signal_window=9&series_type=close&limit={limit}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                f"/v1/indicators/macd/{symbol.upper()}",
                params={
                    "timespan": timespan,
                    "adjusted": "true",
                    "short_window": short_window,
                    "long_window": long_window,
                    "signal_window": signal_window,
                    "series_type": "close",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", {}).get("values", [])

        except httpx.HTTPError as e:
            logger.error("Polygon MACD error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_rsi(
        self,
        symbol: str,
        window: int = 14,
        timespan: str = "day",
        limit: int = 100,
    ) -> List[Dict]:
        """Get Relative Strength Index indicator values.

        GET /v1/indicators/rsi/{symbol}?timespan={timespan}&adjusted=true&window={window}&series_type=close&limit={limit}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                f"/v1/indicators/rsi/{symbol.upper()}",
                params={
                    "timespan": timespan,
                    "adjusted": "true",
                    "window": window,
                    "series_type": "close",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", {}).get("values", [])

        except httpx.HTTPError as e:
            logger.error("Polygon RSI error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    # ------------------------------------------------------------------
    # Market-level data
    # ------------------------------------------------------------------

    async def get_ipos(self, limit: int = 50, days_ahead: int = 30) -> List[Dict]:
        """Get upcoming IPO calendar.

        GET /vX/reference/ipos?order=desc&limit={limit}&listing_date.gte={today}
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            response = await self.client.get(
                "/vX/reference/ipos",
                params={
                    "order": "desc",
                    "limit": limit,
                    "listing_date.gte": from_date,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except httpx.HTTPError as e:
            logger.error("Polygon IPOs error", error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_market_status(self) -> Optional[Dict]:
        """Get current market open/close status.

        GET /v1/marketstatus/now
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return None

        try:
            response = await self.client.get("/v1/marketstatus/now")
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error("Polygon market status error", error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_filings(self, symbol: str, limit: int = 10) -> List[Dict]:
        """Get SEC filings for a ticker.

        GET /stocks/filings/vX/index?ticker={symbol}&limit={limit}&sort=filing_date.desc
        """
        if not self.api_key:
            logger.warning("Polygon API key not configured")
            return []

        try:
            response = await self.client.get(
                "/stocks/filings/vX/index",
                params={
                    "ticker": symbol.upper(),
                    "limit": limit,
                    "sort": "filing_date.desc",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except httpx.HTTPError as e:
            logger.error("Polygon filings error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Polygon", str(e))

    async def get_stock_detail(self, symbol: str) -> Dict[str, Any]:
        """Combined call: snapshot + ratios + short interest for a stock detail page.

        Runs all three requests concurrently for latency efficiency.
        """
        snapshot_task = self.get_quote(symbol)
        ratios_task = self.get_ratios(symbol)
        short_interest_task = self.get_short_interest(symbol, limit=1)

        snapshot, ratios, short_interest_list = await asyncio.gather(
            snapshot_task,
            ratios_task,
            short_interest_task,
            return_exceptions=False,
        )

        latest_short_interest = short_interest_list[0] if short_interest_list else None

        return {
            "snapshot": snapshot,
            "ratios": ratios,
            "shortInterest": latest_short_interest,
        }

    # ------------------------------------------------------------------
    # Synchronous wrappers for use from synchronous Lambda handlers
    # ------------------------------------------------------------------

    def _run(self, coro: Any) -> Any:
        """Run an async coroutine synchronously.

        Lambda handlers are synchronous; this bridge allows them to call
        the async httpx-based methods without restructuring the whole service.
        A new event loop is created per call to avoid conflicts.
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def sync_get_quote(self, symbol: str) -> Optional[Dict]:
        return self._run(self.get_quote(symbol))

    def sync_get_ratios(self, symbol: str) -> Optional[Dict]:
        return self._run(self.get_ratios(symbol))

    def sync_get_income_statements(
        self, symbol: str, timeframe: str = "annual", limit: int = 4
    ) -> List[Dict]:
        return self._run(self.get_income_statements(symbol, timeframe, limit))

    def sync_get_short_interest(self, symbol: str, limit: int = 5) -> List[Dict]:
        return self._run(self.get_short_interest(symbol, limit))

    def sync_get_short_volume(self, symbol: str, limit: int = 5) -> List[Dict]:
        return self._run(self.get_short_volume(symbol, limit))

    def sync_get_float(self, symbol: str) -> Optional[Dict]:
        return self._run(self.get_float(symbol))

    def sync_get_sma(
        self, symbol: str, window: int = 50, timespan: str = "day", limit: int = 100
    ) -> List[Dict]:
        return self._run(self.get_sma(symbol, window, timespan, limit))

    def sync_get_ema(
        self, symbol: str, window: int = 20, timespan: str = "day", limit: int = 100
    ) -> List[Dict]:
        return self._run(self.get_ema(symbol, window, timespan, limit))

    def sync_get_macd(self, symbol: str, timespan: str = "day", limit: int = 100) -> List[Dict]:
        return self._run(self.get_macd(symbol, timespan=timespan, limit=limit))

    def sync_get_rsi(
        self, symbol: str, window: int = 14, timespan: str = "day", limit: int = 100
    ) -> List[Dict]:
        return self._run(self.get_rsi(symbol, window, timespan, limit))

    def sync_get_ipos(self, limit: int = 50, days_ahead: int = 30) -> List[Dict]:
        return self._run(self.get_ipos(limit, days_ahead))

    def sync_get_market_status(self) -> Optional[Dict]:
        return self._run(self.get_market_status())

    def sync_get_filings(self, symbol: str, limit: int = 10) -> List[Dict]:
        return self._run(self.get_filings(symbol, limit))

    def sync_get_stock_detail(self, symbol: str) -> Dict[str, Any]:
        return self._run(self.get_stock_detail(symbol))
