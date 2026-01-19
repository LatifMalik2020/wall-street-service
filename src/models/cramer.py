"""Cramer Tracker models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from src.models.base import BaseEntity, PaginatedResponse


class CramerRecommendation(str, Enum):
    """Cramer recommendation type."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class CramerPick(BaseEntity):
    """A single Cramer stock pick."""

    id: str = Field(..., description="Unique pick ID")
    ticker: str = Field(..., description="Stock ticker symbol")
    companyName: str = Field(..., description="Company name")
    recommendation: CramerRecommendation = Field(..., description="BUY/SELL/HOLD")
    priceAtPick: float = Field(..., description="Stock price when pick was made")
    currentPrice: float = Field(..., description="Current stock price")
    returnPercent: float = Field(..., description="Return since pick")
    inverseReturnPercent: float = Field(..., description="Return if you did opposite")
    pickDate: datetime = Field(..., description="Date of the pick")
    showName: Optional[str] = Field(None, description="Name of the show")
    notes: Optional[str] = Field(None, description="Additional notes")

    @property
    def is_winning(self) -> bool:
        """Check if following the pick would be profitable."""
        if self.recommendation == CramerRecommendation.BUY:
            return self.returnPercent > 0
        elif self.recommendation == CramerRecommendation.SELL:
            return self.returnPercent < 0
        return True  # HOLD is neutral


class CramerStats(BaseModel):
    """Aggregate Cramer performance statistics."""

    totalPicks: int = Field(0, description="Total number of picks")
    followWinRate: float = Field(0.0, description="Win rate following picks")
    inverseWinRate: float = Field(0.0, description="Win rate doing opposite")
    avgFollowReturn: float = Field(0.0, description="Average return following")
    avgInverseReturn: float = Field(0.0, description="Average return inversing")
    bestFollowPick: Optional[CramerPick] = Field(None, description="Best performing follow")
    worstFollowPick: Optional[CramerPick] = Field(None, description="Worst performing follow")
    periodDays: int = Field(30, description="Statistics period in days")


class CramerPicksResponse(PaginatedResponse):
    """Response for Cramer picks list."""

    picks: List[CramerPick] = Field(default_factory=list)
    stats: Optional[CramerStats] = None
