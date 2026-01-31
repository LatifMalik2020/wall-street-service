"""Congress Trading service."""

from typing import Optional, List

from src.models.congress import (
    CongressTrade,
    CongressMember,
    CongressFilters,
    CongressTradesResponse,
    CongressMembersResponse,
    PoliticalParty,
    Chamber,
    TransactionType,
)
from src.repositories.congress import CongressRepository
from src.utils.logging import logger
from src.utils.errors import NotFoundError


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
        """Get specific member with trades."""
        member = self.repo.get_member_by_id(member_id)
        if not member:
            raise NotFoundError("CongressMember", member_id)

        # Fetch recent trades for this member
        recent_trades = self.repo.get_trades_by_member(member_id, limit=50)

        # Calculate win rate from trades with return data
        trades_with_returns = [t for t in recent_trades if t.returnSinceTransaction is not None]
        if trades_with_returns:
            profitable_trades = [t for t in trades_with_returns if t.returnSinceTransaction > 0]
            win_rate = (len(profitable_trades) / len(trades_with_returns)) * 100
        else:
            win_rate = 0.0

        # Update member with trades and win rate
        member.recentTrades = recent_trades
        member.winRate = win_rate

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
