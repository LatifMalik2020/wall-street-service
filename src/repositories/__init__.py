"""Repository layer for DynamoDB access."""

from src.repositories.base import DynamoDBRepository
from src.repositories.cramer import CramerRepository
from src.repositories.congress import CongressRepository
from src.repositories.mood import MoodRepository
from src.repositories.earnings import EarningsRepository
from src.repositories.beat_congress import BeatCongressRepository
from src.repositories.market_talk import MarketTalkRepository

__all__ = [
    "DynamoDBRepository",
    "CramerRepository",
    "CongressRepository",
    "MoodRepository",
    "EarningsRepository",
    "BeatCongressRepository",
    "MarketTalkRepository",
]
