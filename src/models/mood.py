"""Market Mood Meter models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from src.models.base import BaseEntity


class MoodSentiment(str, Enum):
    """Market sentiment levels."""

    EXTREME_FEAR = "EXTREME_FEAR"
    FEAR = "FEAR"
    NEUTRAL = "NEUTRAL"
    GREED = "GREED"
    EXTREME_GREED = "EXTREME_GREED"

    @classmethod
    def from_index(cls, index: int) -> "MoodSentiment":
        """Convert fear/greed index (0-100) to sentiment."""
        if index <= 20:
            return cls.EXTREME_FEAR
        elif index <= 40:
            return cls.FEAR
        elif index <= 60:
            return cls.NEUTRAL
        elif index <= 80:
            return cls.GREED
        else:
            return cls.EXTREME_GREED


class MoodIndicator(BaseModel):
    """Individual mood indicator component."""

    name: str = Field(..., description="Indicator name")
    value: float = Field(..., description="Current value")
    contribution: str = Field(..., description="Contribution to overall mood")
    description: Optional[str] = Field(None, description="Explanation")


class MarketMood(BaseEntity):
    """Current market mood/fear-greed index."""

    fearGreedIndex: int = Field(..., ge=0, le=100, description="Fear/Greed index 0-100")
    sentiment: MoodSentiment = Field(..., description="Current sentiment level")
    previousClose: int = Field(..., description="Yesterday's index")
    weekAgo: int = Field(..., description="Index one week ago")
    monthAgo: int = Field(..., description="Index one month ago")
    yearAgo: int = Field(..., description="Index one year ago")
    updatedAt: datetime = Field(..., description="Last update time")
    indicators: List[MoodIndicator] = Field(default_factory=list)

    @property
    def change_from_yesterday(self) -> int:
        """Change from previous close."""
        return self.fearGreedIndex - self.previousClose


class MoodPrediction(BaseEntity):
    """User's mood prediction."""

    id: str = Field(default="", description="Prediction ID")
    userId: str = Field(..., description="User ID")
    predictedSentiment: MoodSentiment = Field(..., description="Predicted sentiment")
    predictedIndex: Optional[int] = Field(None, ge=0, le=100, description="Predicted index")
    targetDate: datetime = Field(..., description="Date prediction is for")
    createdAt: datetime = Field(..., description="When prediction was made")
    actualSentiment: Optional[MoodSentiment] = Field(None, description="Actual result")
    actualIndex: Optional[int] = Field(None, description="Actual index")
    isCorrect: Optional[bool] = Field(None, description="Was prediction correct")
    xpAwarded: int = Field(0, description="XP awarded for prediction")


class MoodPredictionResult(BaseModel):
    """Result of submitting a mood prediction."""

    prediction: MoodPrediction
    message: str = Field(..., description="Confirmation message")
    xpEarned: int = Field(0, description="XP earned (0 until resolved)")
