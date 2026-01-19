"""Beat Congress Game service."""

from typing import Optional, List

from src.models.beat_congress import (
    BeatCongressGame,
    BeatCongressStatus,
    BeatCongressGamesResponse,
    BeatCongressLeaderboardResponse,
    BeatCongressLeaderboardEntry,
)
from src.models.congress import CongressMember
from src.repositories.beat_congress import BeatCongressRepository
from src.repositories.congress import CongressRepository
from src.utils.logging import logger
from src.utils.errors import NotFoundError, ValidationError, ConflictError
from src.utils.config import get_settings


class BeatCongressService:
    """Service for Beat Congress game business logic."""

    def __init__(self):
        self.repo = BeatCongressRepository()
        self.congress_repo = CongressRepository()
        self.settings = get_settings()

    def get_user_games(
        self,
        user_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> BeatCongressGamesResponse:
        """Get user's Beat Congress games."""
        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = BeatCongressStatus(status.upper())
            except ValueError:
                pass

        games, total = self.repo.get_user_games(
            user_id=user_id,
            status=status_filter,
            page=page,
            page_size=page_size,
        )

        # Count active games
        active_count = sum(1 for g in games if g.status == BeatCongressStatus.ACTIVE)

        total_pages = (total + page_size - 1) // page_size

        return BeatCongressGamesResponse(
            games=games,
            activeGames=active_count,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def get_game_detail(self, user_id: str, game_id: str) -> BeatCongressGame:
        """Get specific game."""
        game = self.repo.get_game_by_id(user_id, game_id)
        if not game:
            raise NotFoundError("BeatCongressGame", game_id)
        return game

    def create_game(
        self,
        user_id: str,
        congress_member_id: str,
        duration_days: int = 30,
    ) -> BeatCongressGame:
        """Create a new Beat Congress game."""
        # Validate duration
        if duration_days < 7 or duration_days > 90:
            raise ValidationError("Duration must be between 7 and 90 days", field="durationDays")

        # Check for existing active game with this member
        existing = self.repo.get_active_game_with_member(user_id, congress_member_id)
        if existing:
            raise ConflictError(f"You already have an active game against this member")

        # Get member info
        member = self.congress_repo.get_member_by_id(congress_member_id)
        if not member:
            raise NotFoundError("CongressMember", congress_member_id)

        # Create game
        game = self.repo.create_game(
            user_id=user_id,
            member_id=member.id,
            member_name=member.name,
            member_party=member.party,
            member_chamber=member.chamber,
            duration_days=duration_days,
        )

        logger.info(
            "Created Beat Congress game",
            user=user_id,
            member=member.name,
            duration=duration_days,
        )

        return game

    def update_game_values(
        self,
        user_id: str,
        game_id: str,
        user_portfolio_value: float,
        congress_portfolio_value: float,
    ) -> BeatCongressGame:
        """Update portfolio values for a game."""
        game = self.repo.update_game_values(
            user_id=user_id,
            game_id=game_id,
            user_value=user_portfolio_value,
            congress_value=congress_portfolio_value,
        )

        if not game:
            raise NotFoundError("BeatCongressGame", game_id)

        return game

    def complete_game(self, user_id: str, game_id: str) -> BeatCongressGame:
        """Complete a game and determine winner."""
        game = self.repo.get_game_by_id(user_id, game_id)
        if not game:
            raise NotFoundError("BeatCongressGame", game_id)

        if game.status != BeatCongressStatus.ACTIVE:
            raise ValidationError("Game is not active")

        user_won = game.userReturnPercent > game.congressReturnPercent

        completed_game = self.repo.complete_game(user_id, game_id, user_won)

        logger.info(
            "Completed Beat Congress game",
            user=user_id,
            won=user_won,
            user_return=game.userReturnPercent,
            congress_return=game.congressReturnPercent,
        )

        # TODO: Emit event for XP grant

        return completed_game

    def get_leaderboard(
        self,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> BeatCongressLeaderboardResponse:
        """Get Beat Congress leaderboard."""
        entries, total = self.repo.get_leaderboard(page=page, page_size=page_size)

        # Get user's rank if authenticated
        user_entry = None
        if user_id:
            user_entry = self.repo.get_user_leaderboard_entry(user_id)

        total_pages = (total + page_size - 1) // page_size

        return BeatCongressLeaderboardResponse(
            entries=entries,
            userRank=user_entry,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def process_expired_games(self) -> int:
        """Process games that have expired. Returns count processed."""
        games = self.repo.get_active_games_to_process()

        processed_count = 0
        for game in games:
            try:
                self.complete_game(game.userId, game.id)
                processed_count += 1
            except Exception as e:
                logger.error(
                    "Failed to process expired game",
                    game_id=game.id,
                    error=str(e),
                )

        logger.info("Processed expired Beat Congress games", count=processed_count)
        return processed_count

    def get_challengeable_members(self, user_id: str, limit: int = 10) -> List[CongressMember]:
        """Get Congress members the user can challenge."""
        members, _ = self.congress_repo.get_members(page=1, page_size=limit * 2)

        # Filter out members user already has active games with
        active_games, _ = self.repo.get_user_games(user_id, status=BeatCongressStatus.ACTIVE)
        active_member_ids = {g.congressMemberId for g in active_games}

        available = [m for m in members if m.id not in active_member_ids]
        return available[:limit]
