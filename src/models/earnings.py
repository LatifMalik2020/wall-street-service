"""Earnings Predictions models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from src.models.base import BaseEntity, PaginatedResponse


class EarningsPredictionType(str, Enum):
    """Earnings prediction type."""

    BEAT = "BEAT"
    MEET = "MEET"
    MISS = "MISS"


class EarningsEvent(BaseEntity):
    """Upcoming earnings event."""

    id: str = Field(..., description="Unique event ID")
    ticker: str = Field(..., description="Stock ticker")
    companyName: str = Field(..., description="Company name")
    earningsDate: datetime = Field(..., description="Earnings release date")
    earningsTime: str = Field(..., description="Before/After market")
    estimatedEPS: Optional[float] = Field(None, description="Estimated EPS")
    actualEPS: Optional[float] = Field(None, description="Actual EPS (after release)")
    estimatedRevenue: Optional[float] = Field(None, description="Estimated revenue")
    actualRevenue: Optional[float] = Field(None, description="Actual revenue")
    surprise: Optional[float] = Field(None, description="Earnings surprise %")
    predictionsClosed: bool = Field(False, description="Can users still predict")
    totalPredictions: int = Field(0, description="Total predictions made")
    beatPredictions: int = Field(0, description="Beat predictions count")
    meetPredictions: int = Field(0, description="Meet predictions count")
    missPredictions: int = Field(0, description="Miss predictions count")


class EarningsPrediction(BaseEntity):
    """User's earnings prediction."""

    userId: str = Field(..., description="User ID")
    eventId: str = Field(..., description="Earnings event ID")
    ticker: str = Field(..., description="Stock ticker")
    prediction: EarningsPredictionType = Field(..., description="BEAT/MEET/MISS")
    createdAt: datetime = Field(..., description="When prediction was made")
    isCorrect: Optional[bool] = Field(None, description="Was prediction correct")
    xpAwarded: int = Field(0, description="XP awarded")


class EarningsResponse(PaginatedResponse):
    """Response for earnings list."""

    events: List[EarningsEvent] = Field(default_factory=list)
    userPredictions: List[EarningsPrediction] = Field(
        default_factory=list, description="Current user's predictions"
    )


class EarningsPredictionResult(BaseModel):
    """Result of submitting earnings prediction."""

    prediction: EarningsPrediction
    message: str = Field(..., description="Confirmation message")
    eventStats: dict = Field(default_factory=dict, description="Updated event stats")


class UserEarningsStats(BaseModel):
    """User's earnings prediction statistics."""

    totalPredictions: int = Field(0)
    correctPredictions: int = Field(0)
    accuracy: float = Field(0.0)
    currentStreak: int = Field(0)
    longestStreak: int = Field(0)
    totalXpEarned: int = Field(0)
