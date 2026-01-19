"""Cramer Tracker repository."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from decimal import Decimal

from src.models.cramer import CramerPick, CramerRecommendation, CramerStats
from src.repositories.base import DynamoDBRepository
from src.utils.logging import logger


class CramerRepository(DynamoDBRepository):
    """Repository for Cramer picks data."""

    # DynamoDB key patterns
    PK_CRAMER = "CRAMER"
    SK_PICK_PREFIX = "PICK#"
    SK_STATS = "STATS"

    def get_picks(
        self,
        page: int = 1,
        page_size: int = 20,
        recommendation: Optional[CramerRecommendation] = None,
        days_back: int = 90,
    ) -> Tuple[List[CramerPick], int]:
        """Get paginated Cramer picks."""
        # Calculate date range
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        # Query with date range
        items, total = self._query_paginated(
            pk=self.PK_CRAMER,
            page=page,
            page_size=page_size,
            sk_begins_with=self.SK_PICK_PREFIX,
            scan_index_forward=False,  # Most recent first
        )

        picks = []
        for item in items:
            pick = self._item_to_pick(item)
            # Filter by recommendation if specified
            if recommendation and pick.recommendation != recommendation:
                continue
            picks.append(pick)

        return picks, total

    def get_pick_by_id(self, pick_id: str) -> Optional[CramerPick]:
        """Get single pick by ID."""
        item = self._get_item(pk=self.PK_CRAMER, sk=f"{self.SK_PICK_PREFIX}{pick_id}")
        return self._item_to_pick(item) if item else None

    def get_pick_by_ticker(self, ticker: str) -> Optional[CramerPick]:
        """Get most recent pick for a ticker."""
        items = self._query(
            pk=self.PK_CRAMER,
            sk_begins_with=self.SK_PICK_PREFIX,
            limit=100,
            scan_index_forward=False,
        )

        for item in items:
            if item.get("ticker", "").upper() == ticker.upper():
                return self._item_to_pick(item)
        return None

    def save_pick(self, pick: CramerPick) -> None:
        """Save a Cramer pick."""
        item = {
            "PK": self.PK_CRAMER,
            "SK": f"{self.SK_PICK_PREFIX}{pick.pickDate.strftime('%Y-%m-%d')}#{pick.ticker}",
            "id": pick.id,
            "ticker": pick.ticker,
            "companyName": pick.companyName,
            "recommendation": pick.recommendation.value,
            "priceAtPick": Decimal(str(pick.priceAtPick)),
            "currentPrice": Decimal(str(pick.currentPrice)),
            "returnPercent": Decimal(str(pick.returnPercent)),
            "inverseReturnPercent": Decimal(str(pick.inverseReturnPercent)),
            "pickDate": pick.pickDate.isoformat(),
            "showName": pick.showName,
            "notes": pick.notes,
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
            # GSI for ticker lookups
            "GSI1PK": f"TICKER#{pick.ticker}",
            "GSI1SK": f"CRAMER#{pick.pickDate.strftime('%Y-%m-%d')}",
        }
        self._put_item(item)
        logger.info("Saved Cramer pick", ticker=pick.ticker, recommendation=pick.recommendation)

    def update_pick_prices(self, pick_id: str, current_price: float) -> Optional[CramerPick]:
        """Update current price and return for a pick."""
        # First get the pick to calculate returns
        item = self._get_item(pk=self.PK_CRAMER, sk=f"{self.SK_PICK_PREFIX}{pick_id}")
        if not item:
            return None

        price_at_pick = float(item.get("priceAtPick", 0))
        if price_at_pick <= 0:
            return None

        return_percent = ((current_price - price_at_pick) / price_at_pick) * 100
        inverse_return = -return_percent

        updated = self._update_item(
            pk=self.PK_CRAMER,
            sk=f"{self.SK_PICK_PREFIX}{pick_id}",
            update_expression="SET currentPrice = :cp, returnPercent = :rp, inverseReturnPercent = :irp, updatedAt = :ua",
            expression_values={
                ":cp": Decimal(str(current_price)),
                ":rp": Decimal(str(round(return_percent, 2))),
                ":irp": Decimal(str(round(inverse_return, 2))),
                ":ua": self._now_iso(),
            },
        )
        return self._item_to_pick(updated)

    def get_stats(self, days_back: int = 30) -> CramerStats:
        """Calculate Cramer statistics."""
        items = self._query(
            pk=self.PK_CRAMER,
            sk_begins_with=self.SK_PICK_PREFIX,
            limit=500,
            scan_index_forward=False,
        )

        # Filter to date range
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        recent_picks = []
        for item in items:
            pick = self._item_to_pick(item)
            if pick.pickDate >= cutoff_date:
                recent_picks.append(pick)

        if not recent_picks:
            return CramerStats(periodDays=days_back)

        # Calculate statistics
        follow_wins = 0
        inverse_wins = 0
        total_follow_return = 0.0
        total_inverse_return = 0.0
        best_follow = None
        worst_follow = None

        for pick in recent_picks:
            total_follow_return += pick.returnPercent
            total_inverse_return += pick.inverseReturnPercent

            if pick.is_winning:
                follow_wins += 1
            else:
                inverse_wins += 1

            if best_follow is None or pick.returnPercent > best_follow.returnPercent:
                best_follow = pick
            if worst_follow is None or pick.returnPercent < worst_follow.returnPercent:
                worst_follow = pick

        total_picks = len(recent_picks)

        return CramerStats(
            totalPicks=total_picks,
            followWinRate=round((follow_wins / total_picks) * 100, 1) if total_picks > 0 else 0,
            inverseWinRate=round((inverse_wins / total_picks) * 100, 1) if total_picks > 0 else 0,
            avgFollowReturn=round(total_follow_return / total_picks, 2) if total_picks > 0 else 0,
            avgInverseReturn=round(total_inverse_return / total_picks, 2) if total_picks > 0 else 0,
            bestFollowPick=best_follow,
            worstFollowPick=worst_follow,
            periodDays=days_back,
        )

    def _item_to_pick(self, item: dict) -> CramerPick:
        """Convert DynamoDB item to CramerPick model."""
        return CramerPick(
            id=item.get("id", item.get("SK", "").split("#")[-1]),
            ticker=item.get("ticker", ""),
            companyName=item.get("companyName", ""),
            recommendation=CramerRecommendation(item.get("recommendation", "HOLD")),
            priceAtPick=float(item.get("priceAtPick", 0)),
            currentPrice=float(item.get("currentPrice", 0)),
            returnPercent=float(item.get("returnPercent", 0)),
            inverseReturnPercent=float(item.get("inverseReturnPercent", 0)),
            pickDate=datetime.fromisoformat(item.get("pickDate", "2024-01-01")),
            showName=item.get("showName"),
            notes=item.get("notes"),
        )
