"""Market Mood API handlers."""

import json
from datetime import datetime
from typing import Optional

from src.services.mood import MoodService
from src.models.mood import MarketMood, MoodSentiment
from src.models.base import APIResponse
from src.utils.logging import logger


def _response(status_code: int, body: dict) -> dict:
    """Format API response with JSON string body and CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "https://tradestreak.net",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def _neutral_mood() -> MarketMood:
    """A safe, always-decodable mood used when no data is available.

    The Market Mood screen treats any failure to load as fatal ("Unable to
    load market mood"), so the GET endpoint must never 500 — it degrades to a
    neutral reading instead (mirrors the graceful-200 pattern used by movers /
    indices comparison).
    """
    return MarketMood(
        fearGreedIndex=50,
        sentiment=MoodSentiment.NEUTRAL,
        previousClose=50,
        weekAgo=50,
        monthAgo=50,
        yearAgo=50,
        updatedAt=datetime.utcnow(),
        indicators=[],
    )


def get_market_mood() -> dict:
    """Get current market mood.

    GET /wall-street/mood

    Always returns 200 with a valid mood payload. On any backend failure
    (DynamoDB throttling, a malformed stored item, a bad timestamp, etc.) we
    fall back to a neutral reading rather than letting the exception escape to
    API Gateway as a 500 — a 500 makes the iOS client show "Unable to load
    market mood".
    """
    try:
        service = MoodService()
        mood = service.get_current_mood()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.error("Market mood load failed, serving neutral", error=str(exc))
        mood = _neutral_mood()

    return _response(
        200,
        APIResponse(
            success=True,
            data=mood.model_dump(mode="json"),
        ).model_dump(mode="json"),
    )


def submit_mood_prediction(
    user_id: str,
    predicted_sentiment: str,
    predicted_index: Optional[int] = None,
) -> dict:
    """Submit a mood prediction.

    POST /wall-street/mood/predict
    """
    service = MoodService()

    result = service.submit_prediction(
        user_id=user_id,
        predicted_sentiment=predicted_sentiment,
        predicted_index=predicted_index,
    )

    return _response(
        201,
        APIResponse(
            success=True,
            data=result.model_dump(mode="json"),
        ).model_dump(mode="json"),
    )


def get_user_mood_predictions(user_id: str, limit: int = 30) -> dict:
    """Get user's mood predictions.

    GET /wall-street/mood/predictions
    """
    service = MoodService()

    predictions = service.get_user_predictions(user_id, limit=limit)

    return _response(
        200,
        APIResponse(
            success=True,
            data={"predictions": [p.model_dump(mode="json") for p in predictions]},
        ).model_dump(mode="json"),
    )
