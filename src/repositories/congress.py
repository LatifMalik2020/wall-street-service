"""Congress Trading repository."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from decimal import Decimal

from src.models.congress import (
    CongressTrade,
    CongressMember,
    CongressFilters,
    PoliticalParty,
    Chamber,
    TransactionType,
)
from src.repositories.base import DynamoDBRepository
from src.utils.logging import logger
from src.utils.normalize import normalize_member_id


class CongressRepository(DynamoDBRepository):
    """Repository for Congress trading data."""

    # DynamoDB key patterns
    PK_CONGRESS = "CONGRESS"
    PK_MEMBER_PREFIX = "CONGRESS_MEMBER#"
    SK_TRADE_PREFIX = "TRADE#"
    SK_PROFILE = "PROFILE"

    def get_trades(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: Optional[CongressFilters] = None,
    ) -> Tuple[List[CongressTrade], int]:
        """Get paginated Congress trades with optional filters."""
        # Query all recent trades
        items, total = self._query_paginated(
            pk=self.PK_CONGRESS,
            page=page,
            page_size=page_size * 2,  # Fetch more to account for filtering
            sk_begins_with=self.SK_TRADE_PREFIX,
            scan_index_forward=False,  # Most recent first
        )

        trades = []
        for item in items:
            trade = self._item_to_trade(item)

            # Apply filters
            if filters:
                if filters.party and trade.party != filters.party:
                    continue
                if filters.chamber and trade.chamber != filters.chamber:
                    continue
                if filters.transactionType and trade.transactionType != filters.transactionType:
                    continue
                if filters.ticker and trade.ticker.upper() != filters.ticker.upper():
                    continue
                if filters.memberId and trade.memberId != filters.memberId:
                    continue

            trades.append(trade)
            if len(trades) >= page_size:
                break

        return trades, total

    def get_trade_by_id(self, trade_id: str) -> Optional[CongressTrade]:
        """Get single trade by ID."""
        item = self._get_item(pk=self.PK_CONGRESS, sk=f"{self.SK_TRADE_PREFIX}{trade_id}")
        return self._item_to_trade(item) if item else None

    def get_trades_by_member(
        self, member_id: str, limit: int = 50
    ) -> List[CongressTrade]:
        """Get trades for a specific member.

        Tries the member-specific partition key first. If empty,
        tries alternative ID formats (underscore vs hyphen) since
        FMP and QuiverQuant historically used different formats.
        """
        # Primary lookup: normalized member ID
        items = self._query(
            pk=f"{self.PK_MEMBER_PREFIX}{member_id}",
            sk_begins_with=self.SK_TRADE_PREFIX,
            limit=limit,
            scan_index_forward=False,
        )
        if items:
            return [self._item_to_trade(item) for item in items]

        # Fallback: try alternative ID format (underscores <-> hyphens)
        alt_id = member_id.replace("-", "_") if "-" in member_id else member_id.replace("_", "-")
        if alt_id != member_id:
            items = self._query(
                pk=f"{self.PK_MEMBER_PREFIX}{alt_id}",
                sk_begins_with=self.SK_TRADE_PREFIX,
                limit=limit,
                scan_index_forward=False,
            )
            if items:
                logger.info(
                    "Found trades under alternative member ID",
                    original_id=member_id,
                    alt_id=alt_id,
                    count=len(items),
                )
                return [self._item_to_trade(item) for item in items]

        return []

    def get_trades_by_member_name(
        self, member_name: str, limit: int = 200
    ) -> List[CongressTrade]:
        """Fallback: scan global trades and filter by member name.

        Used when member-specific partition keys are empty (data migration gap).
        More expensive than partition key lookup but ensures data is found.
        """
        items = self._query(
            pk=self.PK_CONGRESS,
            sk_begins_with=self.SK_TRADE_PREFIX,
            limit=2000,  # Scan more to find member's trades
            scan_index_forward=False,
        )

        name_lower = member_name.lower().strip()
        trades = []
        for item in items:
            item_name = item.get("memberName", "").lower().strip()
            if item_name == name_lower:
                trades.append(self._item_to_trade(item))
                if len(trades) >= limit:
                    break

        return trades

    def get_today_count(self) -> int:
        """Get count of trades disclosed today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        items = self._query(
            pk=self.PK_CONGRESS,
            sk_begins_with=f"{self.SK_TRADE_PREFIX}{today}",
        )
        return len(items)

    def get_top_performer(self, days_back: int = 30) -> Optional[CongressTrade]:
        """Get best performing trade in recent period."""
        items = self._query(
            pk=self.PK_CONGRESS,
            sk_begins_with=self.SK_TRADE_PREFIX,
            limit=200,
            scan_index_forward=False,
        )

        best_trade = None
        best_return = float("-inf")

        cutoff = datetime.utcnow() - timedelta(days=days_back)

        for item in items:
            trade = self._item_to_trade(item)
            if trade.disclosureDate < cutoff:
                continue
            if trade.returnSinceTransaction and trade.returnSinceTransaction > best_return:
                best_return = trade.returnSinceTransaction
                best_trade = trade

        return best_trade

    def save_trade(self, trade: CongressTrade) -> None:
        """Save a Congress trade."""
        trade_id = f"{trade.disclosureDate.strftime('%Y-%m-%d')}#{trade.memberId}#{trade.ticker}"

        item = {
            "PK": self.PK_CONGRESS,
            "SK": f"{self.SK_TRADE_PREFIX}{trade_id}",
            "id": trade.id,
            "memberId": trade.memberId,
            "memberName": trade.memberName,
            "party": trade.party.value,
            "chamber": trade.chamber.value,
            "state": trade.state,
            "ticker": trade.ticker,
            "companyName": trade.companyName,
            "transactionType": trade.transactionType.value,
            "transactionDate": trade.transactionDate.isoformat(),
            "disclosureDate": trade.disclosureDate.isoformat(),
            "amountRangeLow": trade.amountRangeLow,
            "amountRangeHigh": trade.amountRangeHigh,
            "priceAtTransaction": Decimal(str(trade.priceAtTransaction)) if trade.priceAtTransaction else None,
            "currentPrice": Decimal(str(trade.currentPrice)) if trade.currentPrice else None,
            "returnSinceTransaction": Decimal(str(trade.returnSinceTransaction)) if trade.returnSinceTransaction else None,
            "daysToDisclose": trade.daysToDisclose,
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
            # GSI for ticker lookups
            "GSI1PK": f"TICKER#{trade.ticker}",
            "GSI1SK": f"CONGRESS#{trade.disclosureDate.strftime('%Y-%m-%d')}",
        }

        # Remove None values
        item = {k: v for k, v in item.items() if v is not None}
        self._put_item(item)

        # Also store under member's key for member-specific queries
        member_item = item.copy()
        member_item["PK"] = f"{self.PK_MEMBER_PREFIX}{trade.memberId}"
        self._put_item(member_item)

        logger.info(
            "Saved Congress trade",
            member=trade.memberName,
            ticker=trade.ticker,
            type=trade.transactionType,
        )

    def get_members(
        self, page: int = 1, page_size: int = 50
    ) -> Tuple[List[CongressMember], int]:
        """Get all Congress members with trading activity."""
        items, total = self._query_paginated(
            pk="CONGRESS_MEMBERS",
            page=page,
            page_size=page_size,
            sk_begins_with="MEMBER#",
        )
        return [self._item_to_member(item) for item in items], total

    def get_member_by_id(self, member_id: str) -> Optional[CongressMember]:
        """Get member by ID."""
        item = self._get_item(pk="CONGRESS_MEMBERS", sk=f"MEMBER#{member_id}")
        return self._item_to_member(item) if item else None

    def save_member(self, member: CongressMember) -> None:
        """Save Congress member profile."""
        item = {
            "PK": "CONGRESS_MEMBERS",
            "SK": f"MEMBER#{member.id}",
            "id": member.id,
            "name": member.name,
            "party": member.party.value,
            "chamber": member.chamber.value,
            "state": member.state,
            "district": member.district,
            "imageUrl": member.imageUrl,
            "totalTrades": member.totalTrades,
            "estimatedPortfolioReturn": Decimal(str(member.estimatedPortfolioReturn)),
            "avgDaysToDisclose": Decimal(str(member.avgDaysToDisclose)),
            "topHoldings": member.topHoldings,
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
            # GSI for sorting by return
            "GSI1PK": "CONGRESS_LEADERBOARD",
            "GSI1SK": f"{member.estimatedPortfolioReturn:08.2f}#{member.id}",
        }
        item = {k: v for k, v in item.items() if v is not None}
        self._put_item(item)

    def _item_to_trade(self, item: dict) -> CongressTrade:
        """Convert DynamoDB item to CongressTrade model."""
        return CongressTrade(
            id=item.get("id", ""),
            memberId=item.get("memberId", ""),
            memberName=item.get("memberName", ""),
            party=PoliticalParty(item.get("party", "D")),
            chamber=Chamber(item.get("chamber", "House")),
            state=item.get("state", ""),
            ticker=item.get("ticker", ""),
            companyName=item.get("companyName", ""),
            transactionType=TransactionType(item.get("transactionType", "Purchase")),
            transactionDate=datetime.fromisoformat(item.get("transactionDate", "2024-01-01")),
            disclosureDate=datetime.fromisoformat(item.get("disclosureDate", "2024-01-01")),
            amountRangeLow=int(item.get("amountRangeLow", 0)),
            amountRangeHigh=int(item.get("amountRangeHigh", 0)),
            priceAtTransaction=float(item.get("priceAtTransaction")) if item.get("priceAtTransaction") else None,
            currentPrice=float(item.get("currentPrice")) if item.get("currentPrice") else None,
            returnSinceTransaction=float(item.get("returnSinceTransaction")) if item.get("returnSinceTransaction") else None,
            daysToDisclose=int(item.get("daysToDisclose", 0)),
        )

    def _item_to_member(self, item: dict) -> CongressMember:
        """Convert DynamoDB item to CongressMember model."""
        return CongressMember(
            id=item.get("id", ""),
            name=item.get("name", ""),
            party=PoliticalParty(item.get("party", "D")),
            chamber=Chamber(item.get("chamber", "House")),
            state=item.get("state", ""),
            district=item.get("district"),
            imageUrl=item.get("imageUrl"),
            totalTrades=int(item.get("totalTrades", 0)),
            estimatedPortfolioReturn=float(item.get("estimatedPortfolioReturn", 0)),
            avgDaysToDisclose=float(item.get("avgDaysToDisclose", 0)),
            topHoldings=item.get("topHoldings", []),
        )
