"""Market Mood API handlers."""

import json
from typing import Optional

from src.services.mood import MoodService
from src.models.base import APIResponse
from src.utils.logging import logger


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


def get_market_mood() -> dict:
    """Get current market mood.

    GET /wall-street/mood
    """
    service = MoodService()

    mood = service.get_current_mood()

    return _response(200, APIResponse(
        success=True,
        data=mood.model_dump(mode="json"),
    ).model_dump(mode="json"))


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

    return _response(201, APIResponse(
        success=True,
        data=result.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_user_mood_predictions(user_id: str, limit: int = 30) -> dict:
    """Get user's mood predictions.

    GET /wall-street/mood/predictions
    """
    service = MoodService()

    predictions = service.get_user_predictions(user_id, limit=limit)

    return _response(200, APIResponse(
        success=True,
        data={"predictions": [p.model_dump(mode="json") for p in predictions]},
    ).model_dump(mode="json"))
