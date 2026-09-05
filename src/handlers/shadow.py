"""Shadow-portfolio API handlers.

  GET  /wall-street/shadow/roster          — followable filers + staleness
  POST /wall-street/shadow/follow          — {cik, allocation} start a shadow
  GET  /wall-street/shadow/{cik}           — a user's shadow (lazy-rebalanced)
  GET  /wall-street/shadow/trades          — user's shadow trade feed
"""

import asyncio
import json
from typing import Dict, List

from src.services.shadow import ShadowService, shadow_engine_filers
from src.utils.logging import logger


def _response(status_code: int, body: dict) -> dict:
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


def _live_prices(tickers: List[str]) -> Dict[str, float]:
    """Batch quotes via the existing Polygon client; missing quotes just mean
    the engine values those positions at avg cost (honest degradation)."""
    if not tickers:
        return {}
    try:
        from src.ingestion.polygon_client import PolygonClient
        client = PolygonClient()
        quotes = asyncio.run(client.batch_quotes(tickers))
        return {sym: q["price"] for sym, q in quotes.items() if q.get("price", 0) > 0}
    except Exception as e:
        logger.error("shadow price lookup failed", error=str(e))
        return {}


def _service() -> ShadowService:
    return ShadowService(price_lookup=_live_prices)


def get_shadow_roster() -> dict:
    return _response(200, {"filers": _service().get_roster()})


def follow_shadow_filer(user_id: str, body: dict) -> dict:
    try:
        cik = int(body.get("cik", 0))
        allocation = float(body.get("allocation", 10_000))
    except (TypeError, ValueError):
        return _response(400, {"error": "cik and allocation must be numeric"})
    if cik <= 0 or not 100 <= allocation <= 10_000_000:
        return _response(400, {"error": "invalid cik or allocation"})
    try:
        shadow = _service().follow(user_id, cik, allocation)
    except ValueError as e:
        return _response(404, {"error": str(e)})
    return _response(201, {"shadow": shadow})


def get_user_shadow(user_id: str, cik: str) -> dict:
    try:
        cik_num = int(cik)
    except (TypeError, ValueError):
        return _response(400, {"error": "invalid cik"})
    shadow = _service().get_shadow(user_id, cik_num)
    if shadow is None:
        return _response(404, {"error": "not following this filer"})
    return _response(200, {"shadow": shadow})


def get_user_shadow_trades(user_id: str, limit: int = 50) -> dict:
    service = _service()
    trades = service._repo.list_shadow_trades(user_id, limit=min(limit, 200))
    return _response(200, {"trades": trades})


def refresh_shadow_filers() -> dict:
    """EventBridge daily job — check all roster filers for new filings."""
    service = _service()
    results = [service.refresh_filer(cik)
               for cik in sorted(set(shadow_engine_filers().values()))]
    updated = [r for r in results if r.get("status") == "updated"]
    logger.info("shadow filer refresh", updated=len(updated), total=len(results))
    return _response(200, {"results": results})
