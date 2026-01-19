"""Congress Trading API handlers."""

from typing import Optional

from src.services.congress import CongressService
from src.models.base import APIResponse
from src.utils.logging import logger


def get_congress_trades(
    page: int = 1,
    page_size: int = 20,
    party: Optional[str] = None,
    chamber: Optional[str] = None,
    transaction_type: Optional[str] = None,
    ticker: Optional[str] = None,
    member_id: Optional[str] = None,
    days_back: int = 30,
) -> dict:
    """Get paginated Congress trades with filters.

    GET /wall-street/congress/trades
    """
    service = CongressService()

    response = service.get_trades(
        page=page,
        page_size=page_size,
        party=party,
        chamber=chamber,
        transaction_type=transaction_type,
        ticker=ticker,
        member_id=member_id,
        days_back=days_back,
    )

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=response.model_dump(),
        ).model_dump(),
    }


def get_congress_trade_detail(trade_id: str) -> dict:
    """Get specific Congress trade.

    GET /wall-street/congress/trades/{tradeId}
    """
    service = CongressService()

    trade = service.get_trade_detail(trade_id)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=trade.model_dump(),
        ).model_dump(),
    }


def get_congress_members(page: int = 1, page_size: int = 50) -> dict:
    """Get Congress members with trading activity.

    GET /wall-street/congress/members
    """
    service = CongressService()

    response = service.get_members(page=page, page_size=page_size)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=response.model_dump(),
        ).model_dump(),
    }


def get_congress_member_detail(member_id: str) -> dict:
    """Get specific Congress member.

    GET /wall-street/congress/members/{memberId}
    """
    service = CongressService()

    member = service.get_member_detail(member_id)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data=member.model_dump(),
        ).model_dump(),
    }


def get_congress_member_trades(member_id: str, limit: int = 50) -> dict:
    """Get trades for a specific Congress member.

    GET /wall-street/congress/members/{memberId}/trades
    """
    service = CongressService()

    trades = service.get_member_trades(member_id, limit=limit)

    return {
        "statusCode": 200,
        "body": APIResponse(
            success=True,
            data={"trades": [t.model_dump() for t in trades]},
        ).model_dump(),
    }
