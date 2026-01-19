"""CNN Fear & Greed Index API client."""

import httpx
from datetime import datetime
from typing import Optional

from src.models.mood import MarketMood, MoodSentiment, MoodIndicator
from src.utils.logging import logger
from src.utils.errors import ExternalAPIError


class FearGreedClient:
    """Client for CNN Fear & Greed Index.

    Uses the unofficial CNN API endpoint for fear/greed data.
    """

    # CNN Fear & Greed API endpoint
    BASE_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

    def __init__(self):
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TradeStreak/1.0)",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_current_mood(self) -> MarketMood:
        """Fetch current Fear & Greed index."""
        try:
            response = await self.client.get(self.BASE_URL)
            response.raise_for_status()
            data = response.json()

            mood = self._parse_mood_data(data)
            logger.info("Fetched Fear & Greed index", index=mood.fearGreedIndex)
            return mood

        except httpx.HTTPError as e:
            logger.error("CNN Fear & Greed API error", error=str(e))
            raise ExternalAPIError("CNN Fear & Greed", str(e))
        except Exception as e:
            logger.error("Failed to parse Fear & Greed data", error=str(e))
            raise ExternalAPIError("CNN Fear & Greed", str(e))

    def _parse_mood_data(self, data: dict) -> MarketMood:
        """Parse CNN API response to MarketMood model."""
        # Extract fear/greed scores
        fear_and_greed = data.get("fear_and_greed", {})
        current_score = int(fear_and_greed.get("score", 50))
        previous_close = int(fear_and_greed.get("previous_close", 50))

        # Historical comparisons
        week_ago = int(data.get("fear_and_greed_historical", {}).get("one_week_ago", 50))
        month_ago = int(data.get("fear_and_greed_historical", {}).get("one_month_ago", 50))
        year_ago = int(data.get("fear_and_greed_historical", {}).get("one_year_ago", 50))

        # Determine sentiment
        sentiment = MoodSentiment.from_index(current_score)

        # Parse individual indicators
        indicators = self._parse_indicators(data)

        return MarketMood(
            fearGreedIndex=current_score,
            sentiment=sentiment,
            previousClose=previous_close,
            weekAgo=week_ago,
            monthAgo=month_ago,
            yearAgo=year_ago,
            updatedAt=datetime.utcnow(),
            indicators=indicators,
        )

    def _parse_indicators(self, data: dict) -> list:
        """Parse individual indicator components."""
        indicators = []

        # Map of CNN indicator names to our display names
        indicator_map = {
            "market_momentum_sp500": ("Market Momentum (S&P 500)", "Comparing S&P 500 to its 125-day moving average"),
            "market_momentum_sp125": ("Market Momentum (Breadth)", "Number of stocks hitting 52-week highs vs lows"),
            "stock_price_strength": ("Stock Price Strength", "Stocks near 52-week highs vs lows"),
            "stock_price_breadth": ("Stock Price Breadth", "Volume in advancing vs declining stocks"),
            "put_call_options": ("Put/Call Ratio", "Put option trading vs call option trading"),
            "market_volatility_vix": ("Market Volatility (VIX)", "CBOE Volatility Index"),
            "safe_haven_demand": ("Safe Haven Demand", "Relative bond vs stock performance"),
            "junk_bond_demand": ("Junk Bond Demand", "Spread between junk and investment-grade bonds"),
        }

        for key, (name, description) in indicator_map.items():
            indicator_data = data.get(key, {})
            if indicator_data:
                value = float(indicator_data.get("score", 50))
                rating = indicator_data.get("rating", "Neutral")

                indicators.append(
                    MoodIndicator(
                        name=name,
                        value=value,
                        contribution=rating,
                        description=description,
                    )
                )

        return indicators


class FearGreedClientMock:
    """Mock client for development/testing when CNN API is unavailable."""

    async def fetch_current_mood(self) -> MarketMood:
        """Return mock Fear & Greed data."""
        import random

        # Generate realistic mock data
        current_score = random.randint(20, 80)
        previous_close = current_score + random.randint(-5, 5)

        return MarketMood(
            fearGreedIndex=current_score,
            sentiment=MoodSentiment.from_index(current_score),
            previousClose=max(0, min(100, previous_close)),
            weekAgo=max(0, min(100, current_score + random.randint(-10, 10))),
            monthAgo=max(0, min(100, current_score + random.randint(-15, 15))),
            yearAgo=max(0, min(100, current_score + random.randint(-20, 20))),
            updatedAt=datetime.utcnow(),
            indicators=[
                MoodIndicator(
                    name="Market Momentum",
                    value=float(random.randint(30, 70)),
                    contribution="Neutral",
                    description="S&P 500 vs 125-day moving average",
                ),
                MoodIndicator(
                    name="Stock Price Strength",
                    value=float(random.randint(30, 70)),
                    contribution="Fear" if current_score < 50 else "Greed",
                    description="Stocks at 52-week highs vs lows",
                ),
                MoodIndicator(
                    name="VIX",
                    value=float(random.randint(15, 35)),
                    contribution="Fear" if random.random() > 0.5 else "Neutral",
                    description="CBOE Volatility Index",
                ),
            ],
        )

    async def close(self):
        pass
