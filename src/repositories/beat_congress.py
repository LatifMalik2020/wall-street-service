"""Beat Congress Game repository."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from decimal import Decimal
import uuid

from src.models.beat_congress import (
    BeatCongressGame,
    BeatCongressStatus,
    BeatCongressLeaderboardEntry,
)
from src.models.congress import PoliticalParty, Chamber
from src.repositories.base import DynamoDBRepository
from src.utils.logging import logger


class BeatCongressRepository(DynamoDBRepository):
    """Repository for Beat Congress game data."""

    # DynamoDB key patterns
    PK_USER_PREFIX = "USER#"
    SK_BEAT_CONGRESS_PREFIX = "BEAT_CONGRESS#"
    SK_BEAT_CONGRESS_STATS = "BEAT_CONGRESS_STATS"
    PK_LEADERBOARD = "BEAT_CONGRESS_LEADERBOARD"

    def get_user_games(
        self,
        user_id: str,
        status: Optional[BeatCongressStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[BeatCongressGame], int]:
        """Get user's Beat Congress games."""
        items, total = self._query_paginated(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            page=page,
            page_size=page_size,
            sk_begins_with=self.SK_BEAT_CONGRESS_PREFIX,
            scan_index_forward=False,
        )

        games = []
        for item in items:
            game = self._item_to_game(item)
            if status and game.status != status:
                continue
            games.append(game)

        return games, total

    def get_game_by_id(self, user_id: str, game_id: str) -> Optional[BeatCongressGame]:
        """Get specific game."""
        item = self._get_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_BEAT_CONGRESS_PREFIX}{game_id}",
        )
        return self._item_to_game(item) if item else None

    def get_active_game_with_member(
        self, user_id: str, member_id: str
    ) -> Optional[BeatCongressGame]:
        """Check if user has active game with specific member."""
        games, _ = self.get_user_games(user_id, status=BeatCongressStatus.ACTIVE)
        for game in games:
            if game.congressMemberId == member_id:
                return game
        return None

    def create_game(
        self,
        user_id: str,
        member_id: str,
        member_name: str,
        member_party: PoliticalParty,
        member_chamber: Chamber,
        duration_days: int = 30,
    ) -> BeatCongressGame:
        """Create a new Beat Congress game."""
        game_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow()
        end_date = now + timedelta(days=duration_days)

        game = BeatCongressGame(
            id=game_id,
            userId=user_id,
            congressMemberId=member_id,
            congressMemberName=member_name,
            congressMemberParty=member_party,
            congressMemberChamber=member_chamber,
            startDate=now,
            endDate=end_date,
            durationDays=duration_days,
            status=BeatCongressStatus.ACTIVE,
            userStartingValue=10000.0,
            userCurrentValue=10000.0,
            userReturnPercent=0.0,
            congressStartingValue=10000.0,
            congressCurrentValue=10000.0,
            congressReturnPercent=0.0,
        )

        item = {
            "PK": f"{self.PK_USER_PREFIX}{user_id}",
            "SK": f"{self.SK_BEAT_CONGRESS_PREFIX}{game_id}",
            "id": game_id,
            "userId": user_id,
            "congressMemberId": member_id,
            "congressMemberName": member_name,
            "congressMemberParty": member_party.value,
            "congressMemberChamber": member_chamber.value,
            "startDate": now.isoformat(),
            "endDate": end_date.isoformat(),
            "durationDays": duration_days,
            "status": BeatCongressStatus.ACTIVE.value,
            "userStartingValue": Decimal("10000.00"),
            "userCurrentValue": Decimal("10000.00"),
            "userReturnPercent": Decimal("0.00"),
            "congressStartingValue": Decimal("10000.00"),
            "congressCurrentValue": Decimal("10000.00"),
            "congressReturnPercent": Decimal("0.00"),
            "userWon": None,
            "xpAwarded": 0,
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
            # GSI for finding all active games
            "GSI1PK": "ACTIVE_GAMES",
            "GSI1SK": f"{end_date.isoformat()}#{user_id}",
        }
        self._put_item(item)
        logger.info("Created Beat Congress game", user=user_id, member=member_name)
        return game

    def update_game_values(
        self,
        user_id: str,
        game_id: str,
        user_value: float,
        congress_value: float,
    ) -> Optional[BeatCongressGame]:
        """Update portfolio values for a game."""
        game = self.get_game_by_id(user_id, game_id)
        if not game:
            return None

        user_return = ((user_value - game.userStartingValue) / game.userStartingValue) * 100
        congress_return = ((congress_value - game.congressStartingValue) / game.congressStartingValue) * 100

        updated = self._update_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_BEAT_CONGRESS_PREFIX}{game_id}",
            update_expression="SET userCurrentValue = :ucv, userReturnPercent = :urp, congressCurrentValue = :ccv, congressReturnPercent = :crp, updatedAt = :ua",
            expression_values={
                ":ucv": Decimal(str(round(user_value, 2))),
                ":urp": Decimal(str(round(user_return, 2))),
                ":ccv": Decimal(str(round(congress_value, 2))),
                ":crp": Decimal(str(round(congress_return, 2))),
                ":ua": self._now_iso(),
            },
        )
        return self._item_to_game(updated)

    def complete_game(
        self, user_id: str, game_id: str, user_won: bool
    ) -> Optional[BeatCongressGame]:
        """Mark game as completed."""
        xp_awarded = 100 if user_won else 25  # Participation XP

        updated = self._update_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_BEAT_CONGRESS_PREFIX}{game_id}",
            update_expression="SET #status = :status, userWon = :won, xpAwarded = :xp, updatedAt = :ua, GSI1PK = :gsi",
            expression_values={
                ":status": BeatCongressStatus.COMPLETED.value,
                ":won": user_won,
                ":xp": xp_awarded,
                ":ua": self._now_iso(),
                ":gsi": "COMPLETED_GAMES",  # Move out of active games index
            },
            expression_names={"#status": "status"},
        )

        # Update user's leaderboard stats
        self._update_leaderboard_stats(user_id, user_won, xp_awarded)

        return self._item_to_game(updated)

    def get_active_games_to_process(self) -> List[BeatCongressGame]:
        """Get all active games that have ended (for batch processing)."""
        now = datetime.utcnow().isoformat()
        items = self._query(
            pk="ACTIVE_GAMES",
            index_name="GSI1",
            sk_between=("2020-01-01", now),  # All games that have ended
        )
        return [self._item_to_game(item) for item in items]

    # Leaderboard
    def get_leaderboard(
        self, page: int = 1, page_size: int = 50
    ) -> Tuple[List[BeatCongressLeaderboardEntry], int]:
        """Get Beat Congress leaderboard."""
        items, total = self._query_paginated(
            pk=self.PK_LEADERBOARD,
            page=page,
            page_size=page_size,
            index_name="GSI1",
            scan_index_forward=False,  # Highest first
        )

        entries = []
        for i, item in enumerate(items):
            entry = BeatCongressLeaderboardEntry(
                rank=(page - 1) * page_size + i + 1,
                userId=item.get("userId", ""),
                username=item.get("username", "User"),
                gamesPlayed=int(item.get("gamesPlayed", 0)),
                gamesWon=int(item.get("gamesWon", 0)),
                winRate=float(item.get("winRate", 0)),
                totalXpEarned=int(item.get("totalXpEarned", 0)),
                currentStreak=int(item.get("currentStreak", 0)),
            )
            entries.append(entry)

        return entries, total

    def get_user_leaderboard_entry(
        self, user_id: str
    ) -> Optional[BeatCongressLeaderboardEntry]:
        """Get user's leaderboard entry."""
        item = self._get_item(pk=self.PK_LEADERBOARD, sk=f"USER#{user_id}")
        if not item:
            return None

        # Calculate rank
        entries, _ = self.get_leaderboard(page=1, page_size=1000)
        rank = 0
        for i, entry in enumerate(entries):
            if entry.userId == user_id:
                rank = i + 1
                break

        return BeatCongressLeaderboardEntry(
            rank=rank or 999,
            userId=item.get("userId", ""),
            username=item.get("username", "User"),
            gamesPlayed=int(item.get("gamesPlayed", 0)),
            gamesWon=int(item.get("gamesWon", 0)),
            winRate=float(item.get("winRate", 0)),
            totalXpEarned=int(item.get("totalXpEarned", 0)),
            currentStreak=int(item.get("currentStreak", 0)),
        )

    def _update_leaderboard_stats(
        self, user_id: str, won: bool, xp: int
    ) -> None:
        """Update user's leaderboard stats after game completion."""
        entry = self.get_user_leaderboard_entry(user_id)

        games_played = (entry.gamesPlayed if entry else 0) + 1
        games_won = (entry.gamesWon if entry else 0) + (1 if won else 0)
        total_xp = (entry.totalXpEarned if entry else 0) + xp
        current_streak = ((entry.currentStreak if entry else 0) + 1) if won else 0
        win_rate = (games_won / games_played) * 100 if games_played > 0 else 0

        item = {
            "PK": self.PK_LEADERBOARD,
            "SK": f"USER#{user_id}",
            "userId": user_id,
            "username": entry.username if entry else "User",
            "gamesPlayed": games_played,
            "gamesWon": games_won,
            "winRate": Decimal(str(round(win_rate, 1))),
            "totalXpEarned": total_xp,
            "currentStreak": current_streak,
            "updatedAt": self._now_iso(),
            # GSI for leaderboard sorting
            "GSI1PK": self.PK_LEADERBOARD,
            "GSI1SK": f"{games_won:06d}#{win_rate:05.1f}#{user_id}",
        }
        self._put_item(item)

    def _item_to_game(self, item: dict) -> BeatCongressGame:
        """Convert DynamoDB item to BeatCongressGame model."""
        return BeatCongressGame(
            id=item.get("id", ""),
            userId=item.get("userId", ""),
            congressMemberId=item.get("congressMemberId", ""),
            congressMemberName=item.get("congressMemberName", ""),
            congressMemberParty=PoliticalParty(item.get("congressMemberParty", "D")),
            congressMemberChamber=Chamber(item.get("congressMemberChamber", "House")),
            startDate=datetime.fromisoformat(item.get("startDate", datetime.utcnow().isoformat())),
            endDate=datetime.fromisoformat(item.get("endDate", datetime.utcnow().isoformat())),
            durationDays=int(item.get("durationDays", 30)),
            status=BeatCongressStatus(item.get("status", "ACTIVE")),
            userStartingValue=float(item.get("userStartingValue", 10000)),
            userCurrentValue=float(item.get("userCurrentValue", 10000)),
            userReturnPercent=float(item.get("userReturnPercent", 0)),
            congressStartingValue=float(item.get("congressStartingValue", 10000)),
            congressCurrentValue=float(item.get("congressCurrentValue", 10000)),
            congressReturnPercent=float(item.get("congressReturnPercent", 0)),
            userWon=item.get("userWon"),
            xpAwarded=int(item.get("xpAwarded", 0)),
        )
