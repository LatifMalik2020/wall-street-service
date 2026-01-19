"""Data ingestion scheduler for periodic updates."""

from datetime import datetime
from typing import Optional

from src.ingestion.quiver_quant import QuiverQuantClient
from src.ingestion.fear_greed import FearGreedClient, FearGreedClientMock
from src.ingestion.alpha_vantage import AlphaVantageClient, AlphaVantageClientMock
from src.services.congress import CongressService
from src.services.mood import MoodService
from src.services.earnings import EarningsService
from src.utils.config import get_settings
from src.utils.logging import logger


class DataIngestionScheduler:
    """Orchestrates data ingestion from external APIs.

    This class is designed to be called by EventBridge scheduled events.
    """

    def __init__(self, use_mock: bool = False):
        """Initialize scheduler.

        Args:
            use_mock: If True, use mock clients instead of real APIs.
                     Useful for development and testing.
        """
        self.settings = get_settings()
        self.use_mock = use_mock or self.settings.environment == "dev"

        # Initialize clients
        self.quiver_client = QuiverQuantClient()

        if self.use_mock:
            self.fear_greed_client = FearGreedClientMock()
            self.alpha_vantage_client = AlphaVantageClientMock()
        else:
            self.fear_greed_client = FearGreedClient()
            self.alpha_vantage_client = AlphaVantageClient()

        # Initialize services
        self.congress_service = CongressService()
        self.mood_service = MoodService()
        self.earnings_service = EarningsService()

    async def close(self):
        """Close all API clients."""
        await self.quiver_client.close()
        await self.fear_greed_client.close()
        await self.alpha_vantage_client.close()

    async def ingest_congress_trades(self) -> dict:
        """Ingest Congress trading data from QuiverQuant.

        Should be scheduled to run daily.
        """
        try:
            logger.info("Starting Congress trades ingestion")

            # Fetch trades from QuiverQuant
            trades = await self.quiver_client.fetch_congress_trades(days_back=7)

            # Save each trade
            saved_count = 0
            for trade in trades:
                try:
                    self.congress_service.save_trade(trade)
                    saved_count += 1
                except Exception as e:
                    logger.warning("Failed to save trade", error=str(e), trade_id=trade.id)

            logger.info("Congress trades ingestion complete", saved=saved_count, total=len(trades))

            return {
                "success": True,
                "tradesIngested": saved_count,
                "totalFetched": len(trades),
            }

        except Exception as e:
            logger.error("Congress trades ingestion failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def ingest_congress_members(self) -> dict:
        """Ingest Congress member profiles.

        Should be scheduled to run weekly.
        """
        try:
            logger.info("Starting Congress members ingestion")

            # Fetch members from QuiverQuant
            members = await self.quiver_client.fetch_congress_members()

            # Save each member
            saved_count = 0
            for member in members:
                try:
                    self.congress_service.save_member(member)
                    saved_count += 1
                except Exception as e:
                    logger.warning("Failed to save member", error=str(e), member_id=member.id)

            logger.info("Congress members ingestion complete", saved=saved_count, total=len(members))

            return {
                "success": True,
                "membersIngested": saved_count,
                "totalFetched": len(members),
            }

        except Exception as e:
            logger.error("Congress members ingestion failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def ingest_market_mood(self) -> dict:
        """Ingest Fear & Greed index.

        Should be scheduled to run every 15 minutes during market hours.
        """
        try:
            logger.info("Starting market mood ingestion")

            # Fetch current mood
            mood = await self.fear_greed_client.fetch_current_mood()

            # Save mood
            self.mood_service.save_mood(mood)

            logger.info("Market mood ingestion complete", index=mood.fearGreedIndex)

            return {
                "success": True,
                "fearGreedIndex": mood.fearGreedIndex,
                "sentiment": mood.sentiment.value,
            }

        except Exception as e:
            logger.error("Market mood ingestion failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def ingest_earnings_calendar(self) -> dict:
        """Ingest upcoming earnings calendar.

        Should be scheduled to run daily.
        """
        try:
            logger.info("Starting earnings calendar ingestion")

            # Fetch earnings calendar
            events = await self.alpha_vantage_client.get_earnings_calendar(horizon="3month")

            # Save each event
            saved_count = 0
            for event in events:
                try:
                    self.earnings_service.save_event(event)
                    saved_count += 1
                except Exception as e:
                    logger.warning("Failed to save earnings event", error=str(e), event_id=event.id)

            logger.info("Earnings calendar ingestion complete", saved=saved_count, total=len(events))

            return {
                "success": True,
                "eventsIngested": saved_count,
                "totalFetched": len(events),
            }

        except Exception as e:
            logger.error("Earnings calendar ingestion failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def update_stock_prices(self, symbols: Optional[list] = None) -> dict:
        """Update current stock prices for tracked tickers.

        Should be scheduled to run every 5 minutes during market hours.
        """
        try:
            logger.info("Starting stock price update")

            # Default symbols to update (Cramer picks, Congress trades)
            if not symbols:
                # Get unique tickers from recent data
                # For now, use a static list of popular tickers
                symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA"]

            # Fetch quotes
            quotes = await self.alpha_vantage_client.batch_quotes(symbols)

            logger.info("Stock prices updated", count=len(quotes))

            return {
                "success": True,
                "quotesUpdated": len(quotes),
                "symbols": list(quotes.keys()),
            }

        except Exception as e:
            logger.error("Stock price update failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def run_all(self) -> dict:
        """Run all ingestion tasks.

        Useful for initial data population or manual refresh.
        """
        results = {}

        results["congressTrades"] = await self.ingest_congress_trades()
        results["congressMembers"] = await self.ingest_congress_members()
        results["marketMood"] = await self.ingest_market_mood()
        results["earningsCalendar"] = await self.ingest_earnings_calendar()

        return results
