"""Market Talk AI Podcast API handlers."""

import json
from typing import Optional

from src.services.market_talk import MarketTalkService
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


def get_market_talk_episodes(page: int = 1, page_size: int = 20) -> dict:
    """Get Market Talk episodes.

    GET /wall-street/market-talk/episodes
    """
    service = MarketTalkService()

    response = service.get_episodes(page=page, page_size=page_size)

    return _response(200, APIResponse(
        success=True,
        data=response.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_market_talk_episode_detail(episode_id: str) -> dict:
    """Get specific Market Talk episode.

    GET /wall-street/market-talk/episodes/{episodeId}
    """
    service = MarketTalkService()

    episode = service.get_episode_detail(episode_id)

    return _response(200, APIResponse(
        success=True,
        data=episode.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_market_talk_latest() -> dict:
    """Get latest Market Talk exchange for home card.

    GET /wall-street/market-talk/latest
    """
    service = MarketTalkService()

    response = service.get_latest()

    return _response(200, APIResponse(
        success=True,
        data=response.model_dump(mode="json"),
    ).model_dump(mode="json"))


def generate_market_talk(
    topic: str,
    ticker: Optional[str] = None,
    message_count: int = 4,
) -> dict:
    """Generate a new Market Talk episode.

    POST /wall-street/market-talk/generate
    """
    service = MarketTalkService()

    episode = service.generate_episode(
        topic=topic,
        ticker=ticker,
        message_count=message_count,
    )

    return _response(201, APIResponse(
        success=True,
        data=episode.model_dump(mode="json"),
    ).model_dump(mode="json"))
