"""EventBridge event publisher for Wall Street Service."""

import json
import os
from datetime import datetime, timezone

import boto3

from src.utils.logging import logger

_client = None


def _get_client():
    """Lazy-init EventBridge client."""
    global _client
    if _client is None:
        _client = boto3.client(
            "events",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    return _client


def publish_xp_earned(user_id: str, xp_amount: int, source: str) -> None:
    """Publish an XP_EARNED event (fire-and-forget)."""
    bus_name = os.environ.get("EVENTBRIDGE_BUS_NAME", "tradestreak-events")

    try:
        _get_client().put_events(
            Entries=[
                {
                    "Source": "tradestreak.wall-street",
                    "DetailType": "XP_EARNED",
                    "Detail": json.dumps({
                        "userId": user_id,
                        "xpAmount": xp_amount,
                        "source": source,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }),
                    "EventBusName": bus_name,
                }
            ]
        )
        logger.info("Published XP_EARNED event", user=user_id, xp=xp_amount, source=source)
    except Exception:
        logger.exception("Failed to publish XP_EARNED event (non-fatal)", user=user_id, xp=xp_amount, source=source)
