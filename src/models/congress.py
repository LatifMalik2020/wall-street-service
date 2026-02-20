"""Congress Trading Tracker models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from src.models.base import BaseEntity, PaginatedResponse


class PoliticalParty(str, Enum):
    """Political party affiliation."""

    DEMOCRAT = "D"
    REPUBLICAN = "R"
    INDEPENDENT = "I"


class Chamber(str, Enum):
    """Congressional chamber."""

    HOUSE = "House"
    SENATE = "Senate"


class TransactionType(str, Enum):
    """Type of stock transaction."""

    PURCHASE = "Purchase"
    SALE = "Sale"
    SALE_PARTIAL = "Sale (Partial)"
    SALE_FULL = "Sale (Full)"
    EXCHANGE = "Exchange"


class CongressTrade(BaseEntity):
    """A congressional stock trade disclosure."""

    id: str = Field(..., description="Unique trade ID")
    memberId: str = Field(..., description="Congress member ID")
    memberName: str = Field(..., description="Full name of member")
    party: PoliticalParty = Field(..., description="Political party")
    chamber: Chamber = Field(..., description="House or Senate")
    state: str = Field(..., description="State represented")
    ticker: str = Field(..., description="Stock ticker")
    companyName: str = Field(..., description="Company name")
    transactionType: TransactionType = Field(..., description="Buy/Sell type")
    transactionDate: datetime = Field(..., description="Date of transaction")
    disclosureDate: datetime = Field(..., description="Date disclosed")
    amountRangeLow: int = Field(..., description="Low end of amount range")
    amountRangeHigh: int = Field(..., description="High end of amount range")
    priceAtTransaction: Optional[float] = Field(None, description="Price at transaction")
    currentPrice: Optional[float] = Field(None, description="Current price")
    returnSinceTransaction: Optional[float] = Field(None, description="Return since trade")
    daysToDisclose: int = Field(..., description="Days between trade and disclosure")

    @property
    def amount_range_display(self) -> str:
        """Format amount range for display."""
        if self.amountRangeHigh >= 1000000:
            return f"${self.amountRangeLow // 1000}K - ${self.amountRangeHigh // 1000000}M+"
        elif self.amountRangeHigh >= 1000:
            return f"${self.amountRangeLow // 1000}K - ${self.amountRangeHigh // 1000}K"
        return f"${self.amountRangeLow} - ${self.amountRangeHigh}"


class TopTradedCompany(BaseModel):
    """A company frequently traded by a Congress member."""
    ticker: str
    companyName: str
    tradeCount: int
    totalVolume: float = 0.0


class SectorBreakdown(BaseModel):
    """Sector breakdown for a Congress member's trading."""
    sector: str
    tradeCount: int
    percentage: float = 0.0


class CongressMember(BaseEntity):
    """A congress member with trading history."""

    id: str = Field(..., description="Unique member ID")
    name: str = Field(..., description="Full name")
    party: PoliticalParty = Field(..., description="Political party")
    chamber: Chamber = Field(..., description="House or Senate")
    state: str = Field(..., description="State represented")
    district: Optional[str] = Field(None, description="District number (House only)")
    imageUrl: Optional[str] = Field(None, description="Profile image URL")
    totalTrades: int = Field(0, description="Total disclosed trades")
    totalFilings: int = Field(0, description="Total disclosure filings")
    estimatedPortfolioReturn: float = Field(0.0, description="Estimated portfolio return")
    avgDaysToDisclose: float = Field(0.0, description="Average disclosure delay")
    topHoldings: List[str] = Field(default_factory=list, description="Top stock holdings")
    winRate: float = Field(0.0, description="Percentage of profitable trades")
    tradingVolume: float = Field(0.0, description="Total estimated trading volume")
    uniqueIssuers: int = Field(0, description="Number of unique tickers traded")
    firstTradeDate: Optional[str] = Field(None, description="ISO date of first known trade")
    lastTradeDate: Optional[str] = Field(None, description="ISO date of most recent trade")
    topTradedCompanies: List[TopTradedCompany] = Field(default_factory=list, description="Top companies by trade count")
    sectorBreakdown: List[SectorBreakdown] = Field(default_factory=list, description="Trading by sector")
    recentTrades: List["CongressTrade"] = Field(default_factory=list, description="Recent trades")


class CongressFilters(BaseModel):
    """Filters for congress trades query."""

    party: Optional[PoliticalParty] = None
    chamber: Optional[Chamber] = None
    transactionType: Optional[TransactionType] = None
    ticker: Optional[str] = None
    memberId: Optional[str] = None
    daysBack: int = Field(30, ge=1, le=365)


class CongressTradesResponse(PaginatedResponse):
    """Response for congress trades list."""

    trades: List[CongressTrade] = Field(default_factory=list)
    todayCount: int = Field(0, description="Trades disclosed today")
    topPerformer: Optional[CongressTrade] = Field(None, description="Best performing trade")


class CongressMembersResponse(PaginatedResponse):
    """Response for congress members list."""

    members: List[CongressMember] = Field(default_factory=list)


# Update forward references for Pydantic
CongressMember.model_rebuild()
