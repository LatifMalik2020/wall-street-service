"""Market Talk AI Podcast models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from src.models.base import BaseEntity, PaginatedResponse


class MarketTalkHost(str, Enum):
    """AI podcast hosts."""

    MIKE = "MIKE"  # The Bull - optimistic
    SARAH = "SARAH"  # The Skeptic - cautious


class MarketTalkMessage(BaseModel):
    """A single message in the Market Talk conversation."""

    host: MarketTalkHost = Field(..., description="Which host is speaking")
    text: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="When message was generated")
    ticker: Optional[str] = Field(None, description="Related ticker if any")
    sentiment: Optional[str] = Field(None, description="Bullish/Bearish/Neutral")


class MarketTalkEpisode(BaseEntity):
    """A Market Talk episode/conversation."""

    id: str = Field(..., description="Unique episode ID")
    title: str = Field(..., description="Episode title")
    topic: str = Field(..., description="Main topic (e.g., ticker, sector, event)")
    messages: List[MarketTalkMessage] = Field(default_factory=list)
    createdAt: datetime = Field(..., description="Episode creation time")
    isLive: bool = Field(False, description="Is this a live conversation")
    tickersMentioned: List[str] = Field(default_factory=list)
    audioUrl: Optional[str] = Field(None, description="Audio URL if available")
    duration: Optional[int] = Field(None, description="Duration in seconds")


class MarketTalkResponse(PaginatedResponse):
    """Response for Market Talk episodes list."""

    episodes: List[MarketTalkEpisode] = Field(default_factory=list)
    liveEpisode: Optional[MarketTalkEpisode] = Field(None, description="Current live episode")


class MarketTalkLatestResponse(BaseModel):
    """Response for latest Market Talk exchange."""

    episode: Optional[MarketTalkEpisode] = Field(None)
    latestMessages: List[MarketTalkMessage] = Field(
        default_factory=list, description="Most recent exchange"
    )
    isLive: bool = Field(False)


class GenerateMarketTalkRequest(BaseModel):
    """Request to generate Market Talk content."""

    topic: str = Field(..., description="Topic to discuss")
    ticker: Optional[str] = Field(None, description="Specific ticker to discuss")
    messageCount: int = Field(4, ge=2, le=10, description="Number of exchanges")
