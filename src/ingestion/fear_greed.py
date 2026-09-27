"""CNN Fear & Greed Index API client."""

import httpx
from datetime import datetime

from src.models.mood import MarketMood, MoodSentiment, MoodIndicator
from src.utils.logging import logger
from src.utils.errors import ExternalAPIError


def _score(value, fallback: int) -> int:
    """CNN scores are floats (e.g. 35.23) — round, don't truncate."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return fallback


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
        current_score = _score(fear_and_greed.get("score"), 50)
        previous_close = _score(fear_and_greed.get("previous_close"), current_score)

        # Historical comparisons live on the same object as previous_1_week /
        # previous_1_month / previous_1_year (fear_and_greed_historical is the
        # chart series, not these). Fall back to the current score, never a fake 50.
        week_ago = _score(fear_and_greed.get("previous_1_week"), current_score)
        month_ago = _score(fear_and_greed.get("previous_1_month"), current_score)
        year_ago = _score(fear_and_greed.get("previous_1_year"), current_score)

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
            "market_momentum_sp500": (
                "Market Momentum (S&P 500)",
                "Comparing S&P 500 to its 125-day moving average",
            ),
            "market_momentum_sp125": (
                "Market Momentum (Breadth)",
                "Number of stocks hitting 52-week highs vs lows",
            ),
            "stock_price_strength": (
                "Stock Price Strength",
                "Stocks near 52-week highs vs lows",
            ),
            "stock_price_breadth": (
                "Stock Price Breadth",
                "Volume in advancing vs declining stocks",
            ),
            "put_call_options": (
                "Put/Call Ratio",
                "Put option trading vs call option trading",
            ),
            "market_volatility_vix": (
                "Market Volatility (VIX)",
                "CBOE Volatility Index",
            ),
            "safe_haven_demand": (
                "Safe Haven Demand",
                "Relative bond vs stock performance",
            ),
            "junk_bond_demand": (
                "Junk Bond Demand",
                "Spread between junk and investment-grade bonds",
            ),
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
