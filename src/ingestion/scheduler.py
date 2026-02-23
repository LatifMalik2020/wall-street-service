"""Data ingestion scheduler for periodic updates."""

from datetime import datetime
from typing import Optional

from src.ingestion.quiver_quant import QuiverQuantClient
from src.ingestion.fmp import FMPClient
from src.ingestion.fear_greed import FearGreedClient
from src.ingestion.polygon_client import PolygonMarketClient
from src.services.congress import CongressService
from src.services.mood import MoodService
from src.services.earnings import EarningsService
from src.utils.config import get_settings
from src.utils.logging import logger


class DataIngestionScheduler:
    """Orchestrates data ingestion from external APIs.

    This class is designed to be called by EventBridge scheduled events.
    """

    def __init__(self):
        """Initialize scheduler with real API clients."""
        self.settings = get_settings()

        # Initialize clients
        self.fmp_client = FMPClient()
        self.quiver_client = QuiverQuantClient()
        self.fear_greed_client = FearGreedClient()
        self.polygon_client = PolygonMarketClient()

        # Initialize services
        self.congress_service = CongressService()
        self.mood_service = MoodService()
        self.earnings_service = EarningsService()

    async def close(self):
        """Close all API clients."""
        await self.fmp_client.close()
        await self.quiver_client.close()
        await self.fear_greed_client.close()
        await self.polygon_client.close()

    async def ingest_congress_trades(self) -> dict:
        """Ingest Congress trading data.

        Uses FMP as primary source, falls back to QuiverQuant.
        Should be scheduled to run daily.
        """
        try:
            logger.info("Starting Congress trades ingestion")

            trades = []

            # Try FMP first (primary source)
            try:
                trades = await self.fmp_client.fetch_all_latest(limit=200)
                logger.info("Fetched Congress trades from FMP", count=len(trades))
            except Exception as fmp_err:
                logger.warning("FMP fetch failed, falling back to QuiverQuant", error=str(fmp_err))

            # Fall back to QuiverQuant if FMP returned nothing
            if not trades:
                try:
                    trades = await self.quiver_client.fetch_congress_trades(days_back=7)
                    logger.info("Fetched Congress trades from QuiverQuant", count=len(trades))
                except Exception as qv_err:
                    logger.error("QuiverQuant fetch also failed", error=str(qv_err))

            # Save each trade
            saved_count = 0
            for trade in trades:
                try:
                    self.congress_service.save_trade(trade)
                    saved_count += 1
                except Exception as e:
                    logger.warning("Failed to save trade", error=str(e), trade_id=trade.id)

            # Auto-create member profiles from trades with accurate trade counts
            member_trades_count: dict = {}
            for trade in trades:
                mid = trade.memberId
                if mid not in member_trades_count:
                    member_trades_count[mid] = {"trade": trade, "count": 0}
                member_trades_count[mid]["count"] += 1

            members_created = 0
            for mid, info in member_trades_count.items():
                try:
                    from src.models.congress import CongressMember
                    t = info["trade"]
                    member = CongressMember(
                        id=t.memberId,
                        name=t.memberName,
                        party=t.party,
                        chamber=t.chamber,
                        state=t.state,
                        totalTrades=info["count"],
                    )
                    self.congress_service.save_member(member)
                    members_created += 1
                except Exception:
                    pass

            logger.info(
                "Congress trades ingestion complete",
                saved=saved_count,
                total=len(trades),
                members_created=members_created,
            )

            return {
                "success": True,
                "tradesIngested": saved_count,
                "totalFetched": len(trades),
                "membersCreated": members_created,
            }

        except Exception as e:
            logger.error("Congress trades ingestion failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def ingest_congress_members(self) -> dict:
        """Ingest Congress member profiles and their trades.

        Fetches trade data to build member profiles AND saves individual
        trades under member partition keys for efficient lookups.
        Should be scheduled to run weekly.
        """
        try:
            logger.info("Starting Congress members ingestion")

            # Fetch trades from QuiverQuant (used to build member profiles)
            trades = await self.quiver_client.fetch_congress_trades(days_back=365)

            # Save individual trades (ensures member partition keys are populated)
            trades_saved = 0
            for trade in trades:
                try:
                    self.congress_service.save_trade(trade)
                    trades_saved += 1
                except Exception:
                    pass  # Skip duplicates / errors

            # Build and save member profiles from trades
            members = await self.quiver_client.fetch_congress_members()
            members_saved = 0
            for member in members:
                try:
                    self.congress_service.save_member(member)
                    members_saved += 1
                except Exception as e:
                    logger.warning("Failed to save member", error=str(e), member_id=member.id)

            logger.info(
                "Congress members ingestion complete",
                members_saved=members_saved,
                trades_saved=trades_saved,
                total_members=len(members),
            )

            return {
                "success": True,
                "membersIngested": members_saved,
                "tradesIngested": trades_saved,
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
                "sentiment": mood.sentiment if isinstance(mood.sentiment, str) else mood.sentiment.value,
            }

        except Exception as e:
            logger.error("Market mood ingestion failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def ingest_earnings_calendar(self) -> dict:
        """Ingest upcoming earnings calendar.

        Uses FMP as primary data source for earnings dates.
        Should be scheduled to run daily.
        """
        try:
            logger.info("Starting earnings calendar ingestion")

            # Use FMP for earnings calendar data (more reliable for this)
            # Polygon's earnings data is accessed via financials endpoint
            events = []

            # Try Polygon first
            try:
                events = await self.polygon_client.get_earnings_calendar(horizon="3month")
            except Exception as poly_err:
                logger.warning("Polygon earnings fetch returned empty, using FMP", error=str(poly_err))

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
        Uses Polygon.io unlimited plan - no rate limit concerns.
        """
        try:
            logger.info("Starting stock price update")

            # Default symbols to update (Cramer picks, Congress trades)
            if not symbols:
                symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA"]

            # Fetch quotes from Polygon (unlimited calls)
            quotes = await self.polygon_client.batch_quotes(symbols)

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
