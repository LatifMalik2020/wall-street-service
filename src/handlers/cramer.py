"""Cramer Tracker API handlers."""

from typing import Optional

from src.services.cramer import CramerService
from src.models.base import APIResponse
from src.utils.logging import logger


def get_cramer_picks(
    page: int = 1,
    page_size: int = 20,
    recommendation: Optional[str] = None,
    days_back: int = 90,
) -> dict:
    """Get paginated Cramer picks.

    GET /wall-street/cramer/picks
    """
    service = CramerService()

    response = service.get_picks(
        page=page,
        page_size=page_size,
        recommendation=recommendation,
        days_back=days_back,
    )

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=response.model_dump(),
        ).model_dump(),
    }


def get_cramer_pick_detail(ticker: str) -> dict:
    """Get latest Cramer pick for a ticker.

    GET /wall-street/cramer/picks/{ticker}
    """
    service = CramerService()

    pick = service.get_pick_detail(ticker)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=pick.model_dump(),
        ).model_dump(),
    }


def get_cramer_stats(days_back: int = 30) -> dict:
    """Get Cramer performance statistics.

    GET /wall-street/cramer/stats
    """
    service = CramerService()

    stats = service.get_stats(days_back=days_back)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=stats.model_dump(),
        ).model_dump(),
    }
