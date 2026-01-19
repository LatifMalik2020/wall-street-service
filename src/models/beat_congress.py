"""Beat Congress Game models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from src.models.base import BaseEntity, PaginatedResponse
from src.models.congress import PoliticalParty, Chamber


class BeatCongressStatus(str, Enum):
    """Game status."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class BeatCongressGame(BaseEntity):
    """A Beat Congress challenge game."""

    id: str = Field(..., description="Unique game ID")
    userId: str = Field(..., description="User ID")
    congressMemberId: str = Field(..., description="Congress member ID")
    congressMemberName: str = Field(..., description="Member name")
    congressMemberParty: PoliticalParty = Field(..., description="Member party")
    congressMemberChamber: Chamber = Field(..., description="House/Senate")
    startDate: datetime = Field(..., description="Game start date")
    endDate: datetime = Field(..., description="Game end date")
    durationDays: int = Field(30, description="Game duration")
    status: BeatCongressStatus = Field(..., description="Game status")

    # Portfolio tracking
    userStartingValue: float = Field(10000.0, description="User starting portfolio")
    userCurrentValue: float = Field(10000.0, description="User current portfolio")
    userReturnPercent: float = Field(0.0, description="User return %")
    congressStartingValue: float = Field(10000.0, description="Congress starting value")
    congressCurrentValue: float = Field(10000.0, description="Congress current value")
    congressReturnPercent: float = Field(0.0, description="Congress return %")

    # Result
    userWon: Optional[bool] = Field(None, description="Did user win")
    xpAwarded: int = Field(0, description="XP awarded")

    @property
    def is_user_winning(self) -> bool:
        """Check if user is currently winning."""
        return self.userReturnPercent > self.congressReturnPercent

    @property
    def days_remaining(self) -> int:
        """Days remaining in the game."""
        remaining = (self.endDate - datetime.utcnow()).days
        return max(0, remaining)


class BeatCongressLeaderboardEntry(BaseModel):
    """Leaderboard entry for Beat Congress."""

    rank: int = Field(..., description="Leaderboard rank")
    userId: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    gamesPlayed: int = Field(0, description="Total games played")
    gamesWon: int = Field(0, description="Games won")
    winRate: float = Field(0.0, description="Win percentage")
    totalXpEarned: int = Field(0, description="Total XP from Beat Congress")
    currentStreak: int = Field(0, description="Current win streak")


class BeatCongressGamesResponse(PaginatedResponse):
    """Response for Beat Congress games list."""

    games: List[BeatCongressGame] = Field(default_factory=list)
    activeGames: int = Field(0, description="Number of active games")


class BeatCongressLeaderboardResponse(PaginatedResponse):
    """Response for Beat Congress leaderboard."""

    entries: List[BeatCongressLeaderboardEntry] = Field(default_factory=list)
    userRank: Optional[BeatCongressLeaderboardEntry] = Field(
        None, description="Current user's rank"
    )


class CreateBeatCongressRequest(BaseModel):
    """Request to create a new Beat Congress game."""

    congressMemberId: str = Field(..., description="Congress member to challenge")
    durationDays: int = Field(30, ge=7, le=90, description="Game duration")
