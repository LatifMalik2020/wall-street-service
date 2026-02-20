"""Congress Trading service."""

from collections import Counter
from typing import Optional, List

from src.models.congress import (
    CongressTrade,
    CongressMember,
    CongressFilters,
    CongressTradesResponse,
    CongressMembersResponse,
    TopTradedCompany,
    SectorBreakdown,
    PoliticalParty,
    Chamber,
    TransactionType,
)
from src.repositories.congress import CongressRepository
from src.utils.logging import logger
from src.utils.errors import NotFoundError

# Simple ticker-to-sector mapping for common stocks
TICKER_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology", "GOOGL": "Communication Services",
    "GOOG": "Communication Services", "AMZN": "Consumer Discretionary", "NVDA": "Information Technology",
    "TSLA": "Consumer Discretionary", "META": "Communication Services", "JPM": "Financials",
    "V": "Financials", "UNH": "Healthcare", "JNJ": "Healthcare", "XOM": "Energy",
    "WMT": "Consumer Staples", "MA": "Financials", "PG": "Consumer Staples",
    "HD": "Consumer Discretionary", "CVX": "Energy", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "NFLX": "Communication Services", "DIS": "Communication Services",
    "INTC": "Information Technology", "AMD": "Information Technology", "CRM": "Information Technology",
    "ORCL": "Information Technology", "ADBE": "Information Technology", "PYPL": "Financials",
    "PFE": "Healthcare", "MRK": "Healthcare", "ABBV": "Healthcare", "LLY": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare", "BA": "Industrials", "CAT": "Industrials",
    "GE": "Industrials", "RTX": "Industrials", "HON": "Industrials",
    "T": "Communication Services", "VZ": "Communication Services",
    "RBLX": "Communication Services", "SNAP": "Communication Services",
    "SQ": "Financials", "GS": "Financials", "MS": "Financials",
    "C": "Financials", "BAC": "Financials", "WFC": "Financials",
}


class CongressService:
    """Service for Congress Trading business logic."""

    def __init__(self):
        self.repo = CongressRepository()

    def get_trades(
        self,
        page: int = 1,
        page_size: int = 20,
        party: Optional[str] = None,
        chamber: Optional[str] = None,
        transaction_type: Optional[str] = None,
        ticker: Optional[str] = None,
        member_id: Optional[str] = None,
        days_back: int = 30,
    ) -> CongressTradesResponse:
        """Get paginated Congress trades with optional filters."""
        # Build filters
        filters = CongressFilters(daysBack=days_back)

        if party:
            try:
                filters.party = PoliticalParty(party.upper())
            except ValueError:
                pass

        if chamber:
            try:
                filters.chamber = Chamber(chamber.title())
            except ValueError:
                pass

        if transaction_type:
            try:
                filters.transactionType = TransactionType(transaction_type)
            except ValueError:
                pass

        if ticker:
            filters.ticker = ticker.upper()

        if member_id:
            filters.memberId = member_id

        # Get trades
        trades, total = self.repo.get_trades(
            page=page,
            page_size=page_size,
            filters=filters,
        )

        # Get today's count and top performer
        today_count = self.repo.get_today_count()
        top_performer = self.repo.get_top_performer(days_back=days_back)

        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size

        return CongressTradesResponse(
            trades=trades,
            todayCount=today_count,
            topPerformer=top_performer,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def get_trade_detail(self, trade_id: str) -> CongressTrade:
        """Get specific trade by ID."""
        trade = self.repo.get_trade_by_id(trade_id)
        if not trade:
            raise NotFoundError("CongressTrade", trade_id)
        return trade

    def get_members(
        self, page: int = 1, page_size: int = 50
    ) -> CongressMembersResponse:
        """Get Congress members with trading activity."""
        members, total = self.repo.get_members(page=page, page_size=page_size)

        total_pages = (total + page_size - 1) // page_size

        return CongressMembersResponse(
            members=members,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def get_member_detail(self, member_id: str) -> CongressMember:
        """Get specific member with trades and computed stats (Capitol Trades quality)."""
        member = self.repo.get_member_by_id(member_id)
        if not member:
            raise NotFoundError("CongressMember", member_id)

        # Fetch all trades for this member
        recent_trades = self.repo.get_trades_by_member(member_id, limit=200)

        if not recent_trades:
            member.recentTrades = []
            return member

        # Win rate from trades with return data
        trades_with_returns = [t for t in recent_trades if t.returnSinceTransaction is not None]
        if trades_with_returns:
            profitable = [t for t in trades_with_returns if t.returnSinceTransaction > 0]
            win_rate = (len(profitable) / len(trades_with_returns)) * 100
        else:
            win_rate = 0.0

        # Trading volume (midpoint of each trade's amount range)
        trading_volume = sum(
            (t.amountRangeLow + t.amountRangeHigh) / 2 for t in recent_trades
        )

        # Unique issuers
        unique_tickers = set(t.ticker for t in recent_trades)

        # Active period
        sorted_by_date = sorted(recent_trades, key=lambda t: t.transactionDate)
        first_trade_date = sorted_by_date[0].transactionDate.isoformat()
        last_trade_date = sorted_by_date[-1].transactionDate.isoformat()

        # Top traded companies
        ticker_counts = Counter(t.ticker for t in recent_trades)
        ticker_volumes = {}
        ticker_names = {}
        for t in recent_trades:
            mid = (t.amountRangeLow + t.amountRangeHigh) / 2
            ticker_volumes[t.ticker] = ticker_volumes.get(t.ticker, 0) + mid
            ticker_names[t.ticker] = t.companyName

        top_companies = [
            TopTradedCompany(
                ticker=ticker,
                companyName=ticker_names.get(ticker, ticker),
                tradeCount=count,
                totalVolume=ticker_volumes.get(ticker, 0),
            )
            for ticker, count in ticker_counts.most_common(10)
        ]

        # Sector breakdown
        sector_counts = Counter()
        for t in recent_trades:
            sector = TICKER_SECTORS.get(t.ticker, "Other")
            sector_counts[sector] += 1

        total_trades = len(recent_trades)
        sectors = [
            SectorBreakdown(
                sector=sector,
                tradeCount=count,
                percentage=round((count / total_trades) * 100, 1),
            )
            for sector, count in sector_counts.most_common()
        ]

        # Average disclosure delay
        avg_delay = sum(t.daysToDisclose for t in recent_trades) / total_trades

        # Update member with all computed data
        member.recentTrades = recent_trades
        member.winRate = round(win_rate, 1)
        member.tradingVolume = round(trading_volume, 2)
        member.uniqueIssuers = len(unique_tickers)
        member.firstTradeDate = first_trade_date
        member.lastTradeDate = last_trade_date
        member.topTradedCompanies = top_companies
        member.sectorBreakdown = sectors
        member.avgDaysToDisclose = round(avg_delay, 1)
        member.totalFilings = total_trades  # Approximate
        member.totalTrades = total_trades

        return member

    def get_member_trades(
        self, member_id: str, limit: int = 50
    ) -> List[CongressTrade]:
        """Get trades for a specific member."""
        return self.repo.get_trades_by_member(member_id, limit=limit)

    def save_trade(self, trade: CongressTrade) -> CongressTrade:
        """Save a Congress trade (used by ingestion)."""
        self.repo.save_trade(trade)
        logger.info("Saved Congress trade via service", member=trade.memberName, ticker=trade.ticker)
        return trade

    def save_member(self, member: CongressMember) -> CongressMember:
        """Save a Congress member (used by ingestion)."""
        self.repo.save_member(member)
        logger.info("Saved Congress member via service", name=member.name)
        return member
