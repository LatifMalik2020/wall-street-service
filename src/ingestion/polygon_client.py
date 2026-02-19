"""Polygon.io API client for stock prices and earnings calendar."""

import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
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
