"""Congress Trading API handlers."""

import json
from typing import Optional

from src.services.congress import CongressService
from src.models.base import APIResponse
from src.utils.logging import logger
from src.utils.normalize import normalize_member_id


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

    return _response(200, APIResponse(
        success=True,
        data=response.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_congress_trade_detail(trade_id: str) -> dict:
    """Get specific Congress trade.

    GET /wall-street/congress/trades/{tradeId}
    """
    service = CongressService()

    trade = service.get_trade_detail(trade_id)

    return _response(200, APIResponse(
        success=True,
        data=trade.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_congress_members(page: int = 1, page_size: int = 50) -> dict:
    """Get Congress members with trading activity.

    GET /wall-street/congress/members
    """
    service = CongressService()

    response = service.get_members(page=page, page_size=page_size)

    return _response(200, APIResponse(
        success=True,
        data=response.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_congress_member_detail(member_id: str) -> dict:
    """Get specific Congress member.

    GET /wall-street/congress/members/{memberId}
    """
    service = CongressService()

    member = service.get_member_detail(member_id)

    return _response(200, APIResponse(
        success=True,
        data=member.model_dump(mode="json"),
    ).model_dump(mode="json"))


def get_congress_member_trades(member_id: str, limit: int = 50) -> dict:
    """Get trades for a specific Congress member.

    GET /wall-street/congress/members/{memberId}/trades
    """
    service = CongressService()

    trades = service.get_member_trades(member_id, limit=limit)

    return _response(200, APIResponse(
        success=True,
        data={"trades": [t.model_dump(mode="json") for t in trades]},
    ).model_dump(mode="json"))


def backfill_member_trades() -> dict:
    """Backfill member partition keys from global trades.

    POST /wall-street/congress/admin/backfill

    Scans all trades in the global CONGRESS partition and re-saves them
    under normalized CONGRESS_MEMBER# partition keys. This fixes the
    member detail page showing empty trades when partition keys are
    missing or used inconsistent ID formats.
    """
    service = CongressService()
    repo = service.repo

    logger.info("Starting member trades backfill")

    # Scan all global trades
    items = repo._query(
        pk=repo.PK_CONGRESS,
        sk_begins_with=repo.SK_TRADE_PREFIX,
        limit=5000,
        scan_index_forward=False,
    )

    backfilled = 0
    errors = 0
    members_seen = set()

    for item in items:
        try:
            trade = repo._item_to_trade(item)

            # Normalize the member ID
            normalized_id = normalize_member_id(trade.memberName)
            trade.memberId = normalized_id
            members_seen.add(normalized_id)

            # Re-save with dual-write (updates member partition key)
            repo.save_trade(trade)
            backfilled += 1
        except Exception as e:
            errors += 1
            logger.warning("Backfill error", error=str(e))

    logger.info(
        "Member trades backfill complete",
        backfilled=backfilled,
        errors=errors,
        unique_members=len(members_seen),
    )

    return _response(200, APIResponse(
        success=True,
        data={
            "backfilled": backfilled,
            "errors": errors,
            "uniqueMembers": len(members_seen),
        },
    ).model_dump(mode="json"))
