"""Alpha Vantage API client for stock prices and earnings."""

import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import uuid

from src.models.earnings import EarningsEvent
from src.utils.config import get_settings
from src.utils.logging import logger
from src.utils.errors import ExternalAPIError


class AlphaVantageClient:
    """Client for Alpha Vantage stock data API.

    Free tier: 25 requests/day, 5 requests/minute
    Documentation: https://www.alphavantage.co/documentation/
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.alpha_vantage_api_key
        self._client = None
        self._request_count = 0
        self._last_request_time = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self):
        """Implement rate limiting for Alpha Vantage free tier."""
        import asyncio

        now = datetime.utcnow()

        # Reset counter after 24 hours
        if self._last_request_time and (now - self._last_request_time).total_seconds() > 86400:
            self._request_count = 0

        # Check daily limit
        if self._request_count >= 25:
            logger.warning("Alpha Vantage daily rate limit reached")
            raise ExternalAPIError("Alpha Vantage", "Daily rate limit exceeded (25 requests)")

        # Enforce 12 second delay between requests (5 per minute)
        if self._last_request_time:
            elapsed = (now - self._last_request_time).total_seconds()
            if elapsed < 12:
                await asyncio.sleep(12 - elapsed)

        self._request_count += 1
        self._last_request_time = datetime.utcnow()

    async def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get current stock quote."""
        if not self.api_key:
            logger.warning("Alpha Vantage API key not configured")
            return None

        await self._rate_limit()

        try:
            response = await self.client.get(
                "",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol.upper(),
                    "apikey": self.api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            quote = data.get("Global Quote", {})
            if not quote:
                logger.warning("No quote data for symbol", symbol=symbol)
                return None

            return {
                "symbol": quote.get("01. symbol"),
                "price": float(quote.get("05. price", 0)),
                "change": float(quote.get("09. change", 0)),
                "changePercent": float(quote.get("10. change percent", "0%").replace("%", "")),
                "volume": int(quote.get("06. volume", 0)),
                "latestTradingDay": quote.get("07. latest trading day"),
            }

        except httpx.HTTPError as e:
            logger.error("Alpha Vantage quote error", symbol=symbol, error=str(e))
            raise ExternalAPIError("Alpha Vantage", str(e))

    async def get_earnings_calendar(self, horizon: str = "3month") -> List[EarningsEvent]:
        """Get upcoming earnings calendar.

        Args:
            horizon: Time horizon - "3month", "6month", or "12month"
        """
        if not self.api_key:
            logger.warning("Alpha Vantage API key not configured")
            return []

        await self._rate_limit()

        try:
            response = await self.client.get(
                "",
                params={
                    "function": "EARNINGS_CALENDAR",
                    "horizon": horizon,
                    "apikey": self.api_key,
                },
            )
            response.raise_for_status()

            # Earnings calendar returns CSV
            csv_data = response.text
            events = self._parse_earnings_csv(csv_data)

            logger.info("Fetched earnings calendar", count=len(events))
            return events

        except httpx.HTTPError as e:
            logger.error("Alpha Vantage earnings error", error=str(e))
            raise ExternalAPIError("Alpha Vantage", str(e))

    def _parse_earnings_csv(self, csv_data: str) -> List[EarningsEvent]:
        """Parse Alpha Vantage earnings CSV response."""
        events = []
        lines = csv_data.strip().split("\n")

        if len(lines) < 2:
            return events

        # Skip header
        for line in lines[1:]:
            try:
                parts = line.split(",")
                if len(parts) < 5:
                    continue

                symbol = parts[0].strip()
                name = parts[1].strip()
                report_date_str = parts[2].strip()
                fiscal_date = parts[3].strip()
                estimate_str = parts[4].strip() if len(parts) > 4 else ""

                # Parse date
                try:
                    report_date = datetime.strptime(report_date_str, "%Y-%m-%d")
                except ValueError:
                    continue

                # Skip past events
                if report_date < datetime.utcnow():
                    continue

                # Parse estimate
                estimated_eps = None
                if estimate_str and estimate_str != "":
                    try:
                        estimated_eps = float(estimate_str)
                    except ValueError:
                        pass

                event = EarningsEvent(
                    id=f"{report_date.strftime('%Y%m%d')}_{symbol}",
                    ticker=symbol,
                    companyName=name,
                    earningsDate=report_date,
                    earningsTime="Unknown",  # Alpha Vantage doesn't provide this
                    estimatedEPS=estimated_eps,
                )
                events.append(event)

            except Exception as e:
                logger.warning("Failed to parse earnings row", error=str(e), line=line)
                continue

        return events

    async def batch_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get quotes for multiple symbols (with rate limiting)."""
        quotes = {}
        for symbol in symbols:
            try:
                quote = await self.get_quote(symbol)
                if quote:
                    quotes[symbol] = quote
            except ExternalAPIError:
                # Skip failed quotes but continue
                continue

        return quotes


class AlphaVantageClientMock:
    """Mock client for development/testing."""

    async def get_quote(self, symbol: str) -> Dict:
        """Return mock quote data."""
        import random

        base_price = random.uniform(50, 500)
        change = random.uniform(-5, 5)

        return {
            "symbol": symbol.upper(),
            "price": round(base_price, 2),
            "change": round(change, 2),
            "changePercent": round((change / base_price) * 100, 2),
            "volume": random.randint(1000000, 50000000),
            "latestTradingDay": datetime.utcnow().strftime("%Y-%m-%d"),
        }

    async def get_earnings_calendar(self, horizon: str = "3month") -> List[EarningsEvent]:
        """Return mock earnings calendar."""
        events = []
        tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA"]

        for i, ticker in enumerate(tickers):
            event = EarningsEvent(
                id=f"mock_{ticker}_{i}",
                ticker=ticker,
                companyName=f"{ticker} Inc.",
                earningsDate=datetime.utcnow() + timedelta(days=i * 3 + 1),
                earningsTime="After" if i % 2 == 0 else "Before",
                estimatedEPS=round(random.uniform(0.5, 5.0), 2),
            )
            events.append(event)

        return events

    async def batch_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Return mock quotes for multiple symbols."""
        quotes = {}
        for symbol in symbols:
            quotes[symbol] = await self.get_quote(symbol)
        return quotes

    async def close(self):
        pass


# Import random for mock clients
import random
