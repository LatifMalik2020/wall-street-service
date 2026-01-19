"""Market Mood repository."""

from datetime import datetime, timedelta
from typing import List, Optional
from decimal import Decimal

from src.models.mood import MarketMood, MoodSentiment, MoodIndicator, MoodPrediction
from src.repositories.base import DynamoDBRepository
from src.utils.logging import logger


class MoodRepository(DynamoDBRepository):
    """Repository for Market Mood data."""

    # DynamoDB key patterns
    PK_MOOD = "MARKET_MOOD"
    SK_CURRENT = "CURRENT"
    SK_HISTORY_PREFIX = "HISTORY#"
    PK_USER_PREFIX = "USER#"
    SK_MOOD_PREDICTION_PREFIX = "MOOD_PREDICTION#"

    def get_current_mood(self) -> Optional[MarketMood]:
        """Get current market mood."""
        item = self._get_item(pk=self.PK_MOOD, sk=self.SK_CURRENT)
        return self._item_to_mood(item) if item else None

    def get_historical_mood(self, date: datetime) -> Optional[MarketMood]:
        """Get mood for a specific date."""
        date_str = date.strftime("%Y-%m-%d")
        item = self._get_item(pk=self.PK_MOOD, sk=f"{self.SK_HISTORY_PREFIX}{date_str}")
        return self._item_to_mood(item) if item else None

    def save_mood(self, mood: MarketMood, is_current: bool = True) -> None:
        """Save market mood data."""
        indicators_data = [
            {
                "name": ind.name,
                "value": Decimal(str(ind.value)),
                "contribution": ind.contribution,
                "description": ind.description,
            }
            for ind in mood.indicators
        ]

        item = {
            "PK": self.PK_MOOD,
            "SK": self.SK_CURRENT if is_current else f"{self.SK_HISTORY_PREFIX}{mood.updatedAt.strftime('%Y-%m-%d')}",
            "fearGreedIndex": mood.fearGreedIndex,
            "sentiment": mood.sentiment.value,
            "previousClose": mood.previousClose,
            "weekAgo": mood.weekAgo,
            "monthAgo": mood.monthAgo,
            "yearAgo": mood.yearAgo,
            "updatedAt": mood.updatedAt.isoformat(),
            "indicators": indicators_data,
            "createdAt": self._now_iso(),
        }
        self._put_item(item)

        # Also save to history
        if is_current:
            history_item = item.copy()
            history_item["SK"] = f"{self.SK_HISTORY_PREFIX}{mood.updatedAt.strftime('%Y-%m-%d')}"
            self._put_item(history_item)

        logger.info("Saved market mood", index=mood.fearGreedIndex, sentiment=mood.sentiment)

    def get_user_prediction(
        self, user_id: str, target_date: datetime
    ) -> Optional[MoodPrediction]:
        """Get user's mood prediction for a specific date."""
        date_str = target_date.strftime("%Y-%m-%d")
        item = self._get_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_MOOD_PREDICTION_PREFIX}{date_str}",
        )
        return self._item_to_prediction(item) if item else None

    def get_user_predictions(
        self, user_id: str, limit: int = 30
    ) -> List[MoodPrediction]:
        """Get user's recent mood predictions."""
        items = self._query(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk_begins_with=self.SK_MOOD_PREDICTION_PREFIX,
            limit=limit,
            scan_index_forward=False,
        )
        return [self._item_to_prediction(item) for item in items]

    def save_prediction(self, prediction: MoodPrediction) -> None:
        """Save user's mood prediction."""
        date_str = prediction.targetDate.strftime("%Y-%m-%d")

        item = {
            "PK": f"{self.PK_USER_PREFIX}{prediction.userId}",
            "SK": f"{self.SK_MOOD_PREDICTION_PREFIX}{date_str}",
            "userId": prediction.userId,
            "predictedSentiment": prediction.predictedSentiment.value,
            "predictedIndex": prediction.predictedIndex,
            "targetDate": prediction.targetDate.isoformat(),
            "createdAt": prediction.createdAt.isoformat(),
            "actualSentiment": prediction.actualSentiment.value if prediction.actualSentiment else None,
            "actualIndex": prediction.actualIndex,
            "isCorrect": prediction.isCorrect,
            "xpAwarded": prediction.xpAwarded,
            # GSI for finding all predictions for a date (to resolve)
            "GSI1PK": f"MOOD_PREDICTIONS#{date_str}",
            "GSI1SK": prediction.userId,
        }
        item = {k: v for k, v in item.items() if v is not None}
        self._put_item(item)
        logger.info(
            "Saved mood prediction",
            user=prediction.userId,
            predicted=prediction.predictedSentiment,
        )

    def resolve_prediction(
        self, user_id: str, target_date: datetime, actual_mood: MarketMood
    ) -> Optional[MoodPrediction]:
        """Resolve a prediction with actual results."""
        prediction = self.get_user_prediction(user_id, target_date)
        if not prediction:
            return None

        is_correct = prediction.predictedSentiment == actual_mood.sentiment
        xp_awarded = 25 if is_correct else 0

        date_str = target_date.strftime("%Y-%m-%d")
        updated = self._update_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_MOOD_PREDICTION_PREFIX}{date_str}",
            update_expression="SET actualSentiment = :as, actualIndex = :ai, isCorrect = :ic, xpAwarded = :xp",
            expression_values={
                ":as": actual_mood.sentiment.value,
                ":ai": actual_mood.fearGreedIndex,
                ":ic": is_correct,
                ":xp": xp_awarded,
            },
        )
        return self._item_to_prediction(updated)

    def get_pending_predictions(self, target_date: datetime) -> List[MoodPrediction]:
        """Get all pending predictions for a date (for batch resolution)."""
        date_str = target_date.strftime("%Y-%m-%d")
        items = self._query(
            pk=f"MOOD_PREDICTIONS#{date_str}",
            index_name="GSI1",
        )
        return [self._item_to_prediction(item) for item in items if not item.get("isCorrect")]

    def _item_to_mood(self, item: dict) -> MarketMood:
        """Convert DynamoDB item to MarketMood model."""
        indicators = []
        for ind_data in item.get("indicators", []):
            indicators.append(
                MoodIndicator(
                    name=ind_data.get("name", ""),
                    value=float(ind_data.get("value", 0)),
                    contribution=ind_data.get("contribution", "Neutral"),
                    description=ind_data.get("description"),
                )
            )

        return MarketMood(
            fearGreedIndex=int(item.get("fearGreedIndex", 50)),
            sentiment=MoodSentiment(item.get("sentiment", "NEUTRAL")),
            previousClose=int(item.get("previousClose", 50)),
            weekAgo=int(item.get("weekAgo", 50)),
            monthAgo=int(item.get("monthAgo", 50)),
            yearAgo=int(item.get("yearAgo", 50)),
            updatedAt=datetime.fromisoformat(item.get("updatedAt", datetime.utcnow().isoformat())),
            indicators=indicators,
        )

    def _item_to_prediction(self, item: dict) -> MoodPrediction:
        """Convert DynamoDB item to MoodPrediction model."""
        return MoodPrediction(
            userId=item.get("userId", ""),
            predictedSentiment=MoodSentiment(item.get("predictedSentiment", "NEUTRAL")),
            predictedIndex=item.get("predictedIndex"),
            targetDate=datetime.fromisoformat(item.get("targetDate", datetime.utcnow().isoformat())),
            createdAt=datetime.fromisoformat(item.get("createdAt", datetime.utcnow().isoformat())),
            actualSentiment=MoodSentiment(item["actualSentiment"]) if item.get("actualSentiment") else None,
            actualIndex=item.get("actualIndex"),
            isCorrect=item.get("isCorrect"),
            xpAwarded=int(item.get("xpAwarded", 0)),
        )
