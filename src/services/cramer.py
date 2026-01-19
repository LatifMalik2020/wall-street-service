"""Cramer Tracker service."""

from typing import Optional

from src.models.cramer import (
    CramerPick,
    CramerRecommendation,
    CramerPicksResponse,
    CramerStats,
)
from src.repositories.cramer import CramerRepository
from src.utils.logging import logger
from src.utils.errors import NotFoundError


class CramerService:
    """Service for Cramer Tracker business logic."""

    def __init__(self):
        self.repo = CramerRepository()

    def get_picks(
        self,
        page: int = 1,
        page_size: int = 20,
        recommendation: Optional[str] = None,
        days_back: int = 90,
    ) -> CramerPicksResponse:
        """Get paginated Cramer picks with optional filters."""
        # Parse recommendation filter
        rec_filter = None
        if recommendation:
            try:
                rec_filter = CramerRecommendation(recommendation.upper())
            except ValueError:
                pass  # Invalid recommendation, ignore filter

        # Get picks
        picks, total = self.repo.get_picks(
            page=page,
            page_size=page_size,
            recommendation=rec_filter,
            days_back=days_back,
        )

        # Get stats
        stats = self.repo.get_stats(days_back=days_back)

        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size

        return CramerPicksResponse(
            picks=picks,
            stats=stats,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def get_pick_detail(self, ticker: str) -> CramerPick:
        """Get latest pick for a specific ticker."""
        pick = self.repo.get_pick_by_ticker(ticker.upper())
        if not pick:
            raise NotFoundError("CramerPick", ticker)
        return pick

    def get_stats(self, days_back: int = 30) -> CramerStats:
        """Get Cramer performance statistics."""
        return self.repo.get_stats(days_back=days_back)

    def save_pick(self, pick: CramerPick) -> CramerPick:
        """Save a new Cramer pick (used by ingestion)."""
        self.repo.save_pick(pick)
        logger.info("Saved Cramer pick via service", ticker=pick.ticker)
        return pick

    def update_pick_price(
        self, pick_id: str, current_price: float
    ) -> Optional[CramerPick]:
        """Update the current price for a pick."""
        return self.repo.update_pick_prices(pick_id, current_price)
