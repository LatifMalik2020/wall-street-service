"""Base models and utilities."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class BaseEntity(BaseModel):
    """Base entity with common configuration."""

    # use_enum_values=True means enum fields are stored as their plain values
    # after validation (e.g. trade.party == "R", not PoliticalParty.REPUBLICAN).
    # Never call `.value` on these fields directly -- use enum_value() below.
    # (json_encoders was removed: pydantic v2 already serializes datetime as
    # ISO-8601 in JSON mode, and the option is deleted in pydantic v3.)
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )


def enum_value(value: Any) -> Any:
    """Return the raw value of an Enum, or the value itself if already plain.

    Models based on BaseEntity use ``use_enum_values=True`` so validated fields
    are plain str; model_construct()/manual assignment can still hold Enum
    members. This makes repositories safe for both.
    """
    return value.value if isinstance(value, Enum) else value


class PaginatedResponse(BaseModel):
    """Base paginated response."""

    page: int = 1
    pageSize: int = 20
    totalItems: int = 0
    totalPages: int = 0
    hasMore: bool = False


class APIResponse(BaseModel):
    """Standard API response wrapper."""

    success: bool = True
    data: Optional[Any] = None
    error: Optional[dict] = None
    timestamp: str = ""

    def __init__(self, **data):
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        super().__init__(**data)
