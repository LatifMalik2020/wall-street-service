"""Earnings Predictions API handlers."""

from typing import Optional

from src.services.earnings import EarningsService
from src.models.base import APIResponse
from src.utils.logging import logger


def get_upcoming_earnings(
    user_id: Optional[str] = None,
    days_ahead: int = 14,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Get upcoming earnings events.

    GET /wall-street/earnings/upcoming
    """
    service = EarningsService()

    response = service.get_upcoming_events(
        user_id=user_id,
        days_ahead=days_ahead,
        page=page,
        page_size=page_size,
    )

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=response.model_dump(),
        ).model_dump(),
    }


def get_earnings_event_detail(event_id: str) -> dict:
    """Get specific earnings event.

    GET /wall-street/earnings/events/{eventId}
    """
    service = EarningsService()

    event = service.get_event_detail(event_id)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=event.model_dump(),
        ).model_dump(),
    }


def submit_earnings_prediction(
    user_id: str,
    ticker: str,
    prediction: str,
) -> dict:
    """Submit an earnings prediction.

    POST /wall-street/earnings/predict
    """
    service = EarningsService()

    result = service.submit_prediction(
        user_id=user_id,
        ticker=ticker,
        prediction_type=prediction,
    )

    return {
        "statusCode": 201,
        "body": APIResponse(
            success=True,
            data=result.model_dump(),
        ).model_dump(),
    }


def get_user_earnings_predictions(user_id: str, limit: int = 50) -> dict:
    """Get user's earnings predictions.

    GET /wall-street/earnings/predictions
    """
    service = EarningsService()

    predictions = service.get_user_predictions(user_id, limit=limit)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data={"predictions": [p.model_dump() for p in predictions]},
        ).model_dump(),
    }


def get_user_earnings_stats(user_id: str) -> dict:
    """Get user's earnings prediction statistics.

    GET /wall-street/earnings/stats
    """
    service = EarningsService()

    stats = service.get_user_stats(user_id)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=stats.model_dump(),
        ).model_dump(),
    }
