"""Lambda entry point for Wall Street Service."""

import json
from typing import Any

from src.handlers import (
    # Cramer
    get_cramer_picks,
    get_cramer_pick_detail,
    get_cramer_stats,
    # Congress
    get_congress_trades,
    get_congress_trade_detail,
    get_congress_members,
    get_congress_member_detail,
    get_congress_member_trades,
    # Mood
    get_market_mood,
    submit_mood_prediction,
    get_user_mood_predictions,
    # Earnings
    get_upcoming_earnings,
    get_earnings_event_detail,
    submit_earnings_prediction,
    get_user_earnings_predictions,
    get_user_earnings_stats,
    # Beat Congress
    get_beat_congress_games,
    get_beat_congress_game_detail,
    create_beat_congress_game,
    get_beat_congress_leaderboard,
    get_challengeable_members,
    # Market Talk
    get_market_talk_episodes,
    get_market_talk_episode_detail,
    get_market_talk_latest,
    generate_market_talk,
)
from src.events.listener import handle_event
from src.utils.errors import WallStreetError
from src.utils.logging import logger, set_request_context, clear_request_context


def lambda_handler(event: dict, context: Any) -> dict:
    """Main Lambda handler.

    Supports:
    - API Gateway HTTP events
    - EventBridge events
    - SQS events
    """
    request_id = context.aws_request_id if context else "local"
    set_request_context(request_id)

    try:
        # EventBridge event
        if "detail-type" in event:
            return handle_event(event)

        # SQS event
        if "Records" in event:
            return _handle_sqs(event)

        # HTTP event (API Gateway)
        return _handle_http(event)

    except WallStreetError as e:
        logger.warning("Wall Street error", error=e.message, code=e.error_code)
        return _error_response(e.status_code, e.to_dict())
    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        return _error_response(
            500, {"code": "INTERNAL_ERROR", "message": "Internal server error"}
        )
    finally:
        clear_request_context()


def _handle_http(event: dict) -> dict:
    """Handle HTTP request from API Gateway."""
    # Support both REST and HTTP API formats
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get(
        "http", {}
    ).get("method", "GET")
    path = event.get("path") or event.get("rawPath", "/")
    body = _parse_body(event)
    query_params = event.get("queryStringParameters") or {}
    path_params = event.get("pathParameters") or {}

    # Get user ID from JWT claims
    user_id = _get_user_id(event)

    if user_id:
        set_request_context(
            event.get("requestContext", {}).get("requestId", "unknown"), user_id
        )

    logger.info("HTTP request", method=http_method, path=path)

    # Route mapping
    # Cramer routes
    if path == "/wall-street/cramer/picks" and http_method == "GET":
        return get_cramer_picks(
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 20)),
            recommendation=query_params.get("recommendation"),
            days_back=int(query_params.get("daysBack", 90)),
        )

    if path.startswith("/wall-street/cramer/picks/") and http_method == "GET":
        ticker = path_params.get("ticker") or path.split("/")[-1]
        return get_cramer_pick_detail(ticker)

    if path == "/wall-street/cramer/stats" and http_method == "GET":
        return get_cramer_stats(days_back=int(query_params.get("daysBack", 30)))

    # Congress routes
    if path == "/wall-street/congress/trades" and http_method == "GET":
        return get_congress_trades(
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 20)),
            party=query_params.get("party"),
            chamber=query_params.get("chamber"),
            transaction_type=query_params.get("transactionType"),
            ticker=query_params.get("ticker"),
            member_id=query_params.get("memberId"),
            days_back=int(query_params.get("daysBack", 30)),
        )

    if path.startswith("/wall-street/congress/trades/") and http_method == "GET":
        trade_id = path_params.get("tradeId") or path.split("/")[-1]
        return get_congress_trade_detail(trade_id)

    if path == "/wall-street/congress/members" and http_method == "GET":
        return get_congress_members(
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 50)),
        )

    if path.startswith("/wall-street/congress/members/") and path.endswith("/trades"):
        member_id = path.split("/")[-2]
        return get_congress_member_trades(
            member_id, limit=int(query_params.get("limit", 50))
        )

    if path.startswith("/wall-street/congress/members/") and http_method == "GET":
        member_id = path_params.get("memberId") or path.split("/")[-1]
        return get_congress_member_detail(member_id)

    # Mood routes
    if path == "/wall-street/mood" and http_method == "GET":
        return get_market_mood()

    if path == "/wall-street/mood/predict" and http_method == "POST":
        _require_auth(user_id)
        return submit_mood_prediction(
            user_id=user_id,
            predicted_sentiment=body.get("predictedSentiment"),
            predicted_index=body.get("predictedIndex"),
        )

    if path == "/wall-street/mood/predictions" and http_method == "GET":
        _require_auth(user_id)
        return get_user_mood_predictions(
            user_id, limit=int(query_params.get("limit", 30))
        )

    # Earnings routes
    if path == "/wall-street/earnings/upcoming" and http_method == "GET":
        return get_upcoming_earnings(
            user_id=user_id,
            days_ahead=int(query_params.get("daysAhead", 14)),
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 20)),
        )

    if path.startswith("/wall-street/earnings/events/") and http_method == "GET":
        event_id = path_params.get("eventId") or path.split("/")[-1]
        return get_earnings_event_detail(event_id)

    if path == "/wall-street/earnings/predict" and http_method == "POST":
        _require_auth(user_id)
        return submit_earnings_prediction(
            user_id=user_id,
            ticker=body.get("ticker"),
            prediction=body.get("prediction"),
        )

    if path == "/wall-street/earnings/predictions" and http_method == "GET":
        _require_auth(user_id)
        return get_user_earnings_predictions(
            user_id, limit=int(query_params.get("limit", 50))
        )

    if path == "/wall-street/earnings/stats" and http_method == "GET":
        _require_auth(user_id)
        return get_user_earnings_stats(user_id)

    # Beat Congress routes
    if path == "/wall-street/beat-congress/games" and http_method == "GET":
        _require_auth(user_id)
        return get_beat_congress_games(
            user_id=user_id,
            status=query_params.get("status"),
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 20)),
        )

    if path == "/wall-street/beat-congress/games" and http_method == "POST":
        _require_auth(user_id)
        return create_beat_congress_game(
            user_id=user_id,
            congress_member_id=body.get("congressMemberId"),
            duration_days=body.get("durationDays", 30),
        )

    if path.startswith("/wall-street/beat-congress/games/") and http_method == "GET":
        _require_auth(user_id)
        game_id = path_params.get("gameId") or path.split("/")[-1]
        return get_beat_congress_game_detail(user_id, game_id)

    if path == "/wall-street/beat-congress/leaderboard" and http_method == "GET":
        return get_beat_congress_leaderboard(
            user_id=user_id,
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 50)),
        )

    if path == "/wall-street/beat-congress/members" and http_method == "GET":
        _require_auth(user_id)
        return get_challengeable_members(
            user_id, limit=int(query_params.get("limit", 10))
        )

    # Market Talk routes
    if path == "/wall-street/market-talk/episodes" and http_method == "GET":
        return get_market_talk_episodes(
            page=int(query_params.get("page", 1)),
            page_size=int(query_params.get("pageSize", 20)),
        )

    if path == "/wall-street/market-talk/latest" and http_method == "GET":
        return get_market_talk_latest()

    if path.startswith("/wall-street/market-talk/episodes/") and http_method == "GET":
        episode_id = path_params.get("episodeId") or path.split("/")[-1]
        return get_market_talk_episode_detail(episode_id)

    if path == "/wall-street/market-talk/generate" and http_method == "POST":
        return generate_market_talk(
            topic=body.get("topic"),
            ticker=body.get("ticker"),
            message_count=body.get("messageCount", 4),
        )

    # Health check
    if path == "/wall-street/health" and http_method == "GET":
        return _success_response(200, {"status": "healthy", "service": "wall-street"})

    # Route not found
    return _error_response(
        404,
        {
            "code": "NOT_FOUND",
            "message": f"Route not found: {http_method} {path}",
        },
    )


def _handle_sqs(event: dict) -> dict:
    """Handle SQS event (batch of events)."""
    results = []

    for record in event.get("Records", []):
        body = json.loads(record.get("body", "{}"))
        result = handle_event(body)
        results.append(result)

    # Return batch item failures for partial retry
    return {"batchItemFailures": []}


def _get_user_id(event: dict) -> str | None:
    """Extract user ID from event."""
    # From Cognito JWT authorizer
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    if claims:
        return claims.get("sub")

    # From request body or query string (for testing)
    body = _parse_body(event)
    query_params = event.get("queryStringParameters") or {}
    return body.get("userId") or query_params.get("userId")


def _require_auth(user_id: str | None) -> None:
    """Raise error if user not authenticated."""
    if not user_id:
        raise WallStreetError(
            message="Authentication required",
            error_code="UNAUTHORIZED",
            status_code=401,
        )


def _parse_body(event: dict) -> dict:
    """Parse request body."""
    body = event.get("body")
    if not body:
        return {}

    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body


def _success_response(status_code: int, body: dict) -> dict:
    """Format success response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Idempotency-Key",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def _error_response(status_code: int, error: dict) -> dict:
    """Format error response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": error}),
    }
