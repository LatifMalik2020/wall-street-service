"""Market Mood service."""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from src.models.mood import (
    MarketMood,
    MoodSentiment,
    MoodPrediction,
    MoodPredictionResult,
)
from src.repositories.mood import MoodRepository
from src.utils.logging import logger
from src.utils.errors import ValidationError, ConflictError
from src.utils.config import get_settings


class MoodService:
    """Service for Market Mood business logic."""

    def __init__(self):
        self.repo = MoodRepository()
        self.settings = get_settings()

    def get_current_mood(self) -> MarketMood:
        """Get current market mood."""
        mood = self.repo.get_current_mood()
        if not mood:
            # Return a default mood if none exists
            return MarketMood(
                fearGreedIndex=50,
                sentiment=MoodSentiment.NEUTRAL,
                previousClose=50,
                weekAgo=50,
                monthAgo=50,
                yearAgo=50,
                updatedAt=datetime.utcnow(),
                indicators=[],
            )
        return mood

    def get_mood_by_date(self, date: datetime) -> Optional[MarketMood]:
        """Get mood for a specific date."""
        return self.repo.get_historical_mood(date)

    def save_mood(self, mood: MarketMood) -> MarketMood:
        """Save market mood (used by ingestion)."""
        self.repo.save_mood(mood, is_current=True)
        logger.info("Saved market mood", index=mood.fearGreedIndex, sentiment=mood.sentiment)
        return mood

    def submit_prediction(
        self,
        user_id: str,
        predicted_sentiment: str,
        predicted_index: Optional[int] = None,
    ) -> MoodPredictionResult:
        """Submit a mood prediction for next week."""
        # Parse sentiment
        try:
            sentiment = MoodSentiment(predicted_sentiment.upper())
        except ValueError:
            raise ValidationError(f"Invalid sentiment: {predicted_sentiment}", field="predictedSentiment")

        # Target date is 7 days from now
        target_date = datetime.utcnow() + timedelta(days=7)
        target_date = target_date.replace(hour=16, minute=0, second=0, microsecond=0)  # Market close

        # Check for existing prediction
        existing = self.repo.get_user_prediction(user_id, target_date)
        if existing:
            raise ConflictError("You already have a prediction for this period")

        # Create prediction with unique ID
        prediction_id = f"{user_id[:8]}-{target_date.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
        prediction = MoodPrediction(
            id=prediction_id,
            userId=user_id,
            predictedSentiment=sentiment,
            predictedIndex=predicted_index,
            targetDate=target_date,
            createdAt=datetime.utcnow(),
        )

        self.repo.save_prediction(prediction)

        return MoodPredictionResult(
            prediction=prediction,
            message=f"Prediction saved! We'll check back on {target_date.strftime('%B %d')}.",
            xpEarned=0,  # XP awarded when resolved
        )

    def get_user_predictions(self, user_id: str, limit: int = 30) -> list:
        """Get user's mood predictions."""
        return self.repo.get_user_predictions(user_id, limit=limit)

    def resolve_predictions(self, target_date: datetime) -> int:
        """Resolve all pending predictions for a date. Returns count of resolved."""
        # Get actual mood for that date
        actual_mood = self.repo.get_historical_mood(target_date)
        if not actual_mood:
            logger.warning("No mood data for date, skipping resolution", date=target_date)
            return 0

        # Get pending predictions
        pending = self.repo.get_pending_predictions(target_date)

        resolved_count = 0
        for prediction in pending:
            self.repo.resolve_prediction(prediction.userId, target_date, actual_mood)
            resolved_count += 1

            # TODO: Emit event for XP grant if correct
            if prediction.predictedSentiment == actual_mood.sentiment:
                logger.info(
                    "Correct mood prediction",
                    user=prediction.userId,
                    predicted=prediction.predictedSentiment,
                    actual=actual_mood.sentiment,
                )

        logger.info("Resolved mood predictions", count=resolved_count, date=target_date)
        return resolved_count
