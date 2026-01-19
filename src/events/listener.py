"""EventBridge event listener for scheduled tasks."""

import asyncio
from typing import Any, Dict

from src.ingestion.scheduler import DataIngestionScheduler
from src.services.beat_congress import BeatCongressService
from src.services.mood import MoodService
from src.utils.logging import logger


def handle_event(event: dict) -> dict:
    """Handle EventBridge scheduled events.

    Supported event types:
    - wall-street.ingest.congress-trades
    - wall-street.ingest.congress-members
    - wall-street.ingest.market-mood
    - wall-street.ingest.earnings
    - wall-street.process.beat-congress-games
    - wall-street.process.mood-predictions
    """
    detail_type = event.get("detail-type", "")
    detail = event.get("detail", {})

    logger.info("Received EventBridge event", detail_type=detail_type)

    # Run async handler
    result = asyncio.get_event_loop().run_until_complete(
        _handle_event_async(detail_type, detail)
    )

    return {
        "statusCode": 200,
        "body": result,
    }


async def _handle_event_async(detail_type: str, detail: dict) -> dict:
    """Async event handler."""

    # Ingestion events
    if detail_type == "wall-street.ingest.congress-trades":
        return await _ingest_congress_trades()

    elif detail_type == "wall-street.ingest.congress-members":
        return await _ingest_congress_members()

    elif detail_type == "wall-street.ingest.market-mood":
        return await _ingest_market_mood()

    elif detail_type == "wall-street.ingest.earnings":
        return await _ingest_earnings()

    elif detail_type == "wall-street.ingest.stock-prices":
        symbols = detail.get("symbols")
        return await _update_stock_prices(symbols)

    elif detail_type == "wall-street.ingest.all":
        return await _ingest_all()

    # Processing events
    elif detail_type == "wall-street.process.beat-congress-games":
        return await _process_beat_congress_games()

    elif detail_type == "wall-street.process.mood-predictions":
        target_date = detail.get("targetDate")
        return await _process_mood_predictions(target_date)

    else:
        logger.warning("Unknown event type", detail_type=detail_type)
        return {"success": False, "error": f"Unknown event type: {detail_type}"}


async def _ingest_congress_trades() -> dict:
    """Ingest Congress trades."""
    scheduler = DataIngestionScheduler()
    try:
        return await scheduler.ingest_congress_trades()
    finally:
        await scheduler.close()


async def _ingest_congress_members() -> dict:
    """Ingest Congress members."""
    scheduler = DataIngestionScheduler()
    try:
        return await scheduler.ingest_congress_members()
    finally:
        await scheduler.close()


async def _ingest_market_mood() -> dict:
    """Ingest market mood."""
    scheduler = DataIngestionScheduler()
    try:
        return await scheduler.ingest_market_mood()
    finally:
        await scheduler.close()


async def _ingest_earnings() -> dict:
    """Ingest earnings calendar."""
    scheduler = DataIngestionScheduler()
    try:
        return await scheduler.ingest_earnings_calendar()
    finally:
        await scheduler.close()


async def _update_stock_prices(symbols: list = None) -> dict:
    """Update stock prices."""
    scheduler = DataIngestionScheduler()
    try:
        return await scheduler.update_stock_prices(symbols)
    finally:
        await scheduler.close()


async def _ingest_all() -> dict:
    """Run all ingestion tasks."""
    scheduler = DataIngestionScheduler()
    try:
        return await scheduler.run_all()
    finally:
        await scheduler.close()


async def _process_beat_congress_games() -> dict:
    """Process expired Beat Congress games."""
    service = BeatCongressService()
    count = service.process_expired_games()
    return {
        "success": True,
        "gamesProcessed": count,
    }


async def _process_mood_predictions(target_date: str = None) -> dict:
    """Process mood predictions for a date."""
    from datetime import datetime, timedelta

    service = MoodService()

    # Default to 7 days ago (predictions from a week ago)
    if target_date:
        date = datetime.fromisoformat(target_date)
    else:
        date = datetime.utcnow() - timedelta(days=7)

    count = service.resolve_predictions(date)
    return {
        "success": True,
        "predictionsResolved": count,
        "targetDate": date.isoformat(),
    }
