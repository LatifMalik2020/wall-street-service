"""Beat Congress Game API handlers."""

import json
from typing import Optional

from src.services.beat_congress import BeatCongressService
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


def get_beat_congress_games(
    user_id: str,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Get user's Beat Congress games.

    GET /wall-street/beat-congress/games
    """
    service = BeatCongressService()

    response = service.get_user_games(
        user_id=user_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    return _response(200, APIResponse(
        success=True,
        data=response.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_beat_congress_game_detail(user_id: str, game_id: str) -> dict:
    """Get specific Beat Congress game.

    GET /wall-street/beat-congress/games/{gameId}
    """
    service = BeatCongressService()

    game = service.get_game_detail(user_id, game_id)

    return _response(200, APIResponse(
        success=True,
        data=game.model_dump(mode="json"),
    ).model_dump(mode="json"))


def create_beat_congress_game(
    user_id: str,
    congress_member_id: str,
    duration_days: int = 30,
) -> dict:
    """Create a new Beat Congress game.

    POST /wall-street/beat-congress/games
    """
    service = BeatCongressService()

    game = service.create_game(
        user_id=user_id,
        congress_member_id=congress_member_id,
        duration_days=duration_days,
    )

    return _response(201, APIResponse(
        success=True,
        data=game.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_beat_congress_leaderboard(
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get Beat Congress leaderboard.

    GET /wall-street/beat-congress/leaderboard
    """
    service = BeatCongressService()

    response = service.get_leaderboard(
        user_id=user_id,
        page=page,
        page_size=page_size,
    )

    return _response(200, APIResponse(
        success=True,
        data=response.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_challengeable_members(user_id: str, limit: int = 10) -> dict:
    """Get Congress members the user can challenge.

    GET /wall-street/beat-congress/members
    """
    service = BeatCongressService()

    members = service.get_challengeable_members(user_id, limit=limit)

    return _response(200, APIResponse(
        success=True,
        data={"members": [m.model_dump(mode="json") for m in members]},
    ).model_dump(mode="json"))
