"""Base models and utilities."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class BaseEntity(BaseModel):
    """Base entity with common configuration."""

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )


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
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        super().__init__(**data)
