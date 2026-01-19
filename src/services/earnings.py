"""Earnings Predictions service."""

from datetime import datetime
from typing import Optional, List

from src.models.earnings import (
    EarningsEvent,
    EarningsPrediction,
    EarningsPredictionType,
    EarningsResponse,
    EarningsPredictionResult,
    UserEarningsStats,
)
from src.repositories.earnings import EarningsRepository
from src.utils.logging import logger
from src.utils.errors import NotFoundError, ValidationError, ConflictError
from src.utils.config import get_settings


class EarningsService:
    """Service for Earnings Predictions business logic."""

    def __init__(self):
        self.repo = EarningsRepository()
        self.settings = get_settings()

    def get_upcoming_events(
        self,
        user_id: Optional[str] = None,
        days_ahead: int = 14,
        page: int = 1,
        page_size: int = 20,
    ) -> EarningsResponse:
        """Get upcoming earnings events with user predictions."""
        events, total = self.repo.get_upcoming_events(
            days_ahead=days_ahead,
            page=page,
            page_size=page_size,
        )

        # Get user's predictions if authenticated
        user_predictions = []
        if user_id:
            user_predictions = self.repo.get_user_predictions(user_id, limit=50)

        total_pages = (total + page_size - 1) // page_size

        return EarningsResponse(
            events=events,
            userPredictions=user_predictions,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def get_event_detail(self, event_id: str) -> EarningsEvent:
        """Get specific earnings event."""
        event = self.repo.get_event_by_id(event_id)
        if not event:
            raise NotFoundError("EarningsEvent", event_id)
        return event

    def get_event_by_ticker(self, ticker: str) -> EarningsEvent:
        """Get upcoming earnings event for a ticker."""
        event = self.repo.get_event_by_ticker(ticker.upper())
        if not event:
            raise NotFoundError("EarningsEvent", ticker)
        return event

    def submit_prediction(
        self,
        user_id: str,
        ticker: str,
        prediction_type: str,
    ) -> EarningsPredictionResult:
        """Submit an earnings prediction."""
        # Parse prediction type
        try:
            pred_type = EarningsPredictionType(prediction_type.upper())
        except ValueError:
            raise ValidationError(f"Invalid prediction type: {prediction_type}", field="prediction")

        # Find the event
        event = self.repo.get_event_by_ticker(ticker.upper())
        if not event:
            raise NotFoundError("EarningsEvent", ticker)

        # Check if predictions are still open
        if event.predictionsClosed:
            raise ValidationError("Predictions are closed for this earnings event")

        # Check if user already predicted
        existing = self.repo.get_user_prediction(user_id, event.id)
        if existing:
            raise ConflictError("You already predicted for this earnings event")

        # Create prediction
        prediction = EarningsPrediction(
            userId=user_id,
            eventId=event.id,
            ticker=event.ticker,
            prediction=pred_type,
            createdAt=datetime.utcnow(),
        )

        self.repo.save_prediction(prediction)

        # Update event stats
        self.repo.increment_prediction_count(event.id, pred_type)

        # Get updated event stats
        updated_event = self.repo.get_event_by_id(event.id)
        event_stats = {
            "totalPredictions": updated_event.totalPredictions if updated_event else 0,
            "beatPredictions": updated_event.beatPredictions if updated_event else 0,
            "meetPredictions": updated_event.meetPredictions if updated_event else 0,
            "missPredictions": updated_event.missPredictions if updated_event else 0,
        }

        return EarningsPredictionResult(
            prediction=prediction,
            message=f"Prediction saved! We'll see how {ticker} does.",
            eventStats=event_stats,
        )

    def get_user_predictions(self, user_id: str, limit: int = 50) -> List[EarningsPrediction]:
        """Get user's earnings predictions."""
        return self.repo.get_user_predictions(user_id, limit=limit)

    def get_user_stats(self, user_id: str) -> UserEarningsStats:
        """Get user's earnings prediction statistics."""
        return self.repo.get_user_stats(user_id)

    def save_event(self, event: EarningsEvent) -> EarningsEvent:
        """Save earnings event (used by ingestion)."""
        self.repo.save_event(event)
        logger.info("Saved earnings event", ticker=event.ticker, date=event.earningsDate)
        return event

    def update_event_results(
        self,
        event_id: str,
        actual_eps: float,
        actual_revenue: Optional[float] = None,
    ) -> Optional[EarningsEvent]:
        """Update event with actual results and resolve predictions."""
        event = self.repo.update_event_results(event_id, actual_eps, actual_revenue)
        if not event:
            return None

        # Determine result type
        result_type = self._determine_result(event)

        # Resolve all predictions
        predictions = self.repo.get_predictions_for_event(event_id)
        for pred in predictions:
            is_correct = pred.prediction == result_type
            self.repo.resolve_prediction(pred.userId, event_id, is_correct)
            self.repo.update_user_stats(pred.userId, is_correct, 50 if is_correct else 0)

            if is_correct:
                logger.info(
                    "Correct earnings prediction",
                    user=pred.userId,
                    ticker=event.ticker,
                    predicted=pred.prediction,
                )

        logger.info("Resolved earnings predictions", event=event_id, count=len(predictions))
        return event

    def _determine_result(self, event: EarningsEvent) -> EarningsPredictionType:
        """Determine if earnings BEAT/MET/MISSED estimates."""
        if not event.actualEPS or not event.estimatedEPS:
            return EarningsPredictionType.MEET

        surprise_threshold = 0.02  # 2% threshold for beat/miss

        if event.estimatedEPS == 0:
            return EarningsPredictionType.MEET

        surprise_pct = (event.actualEPS - event.estimatedEPS) / abs(event.estimatedEPS)

        if surprise_pct > surprise_threshold:
            return EarningsPredictionType.BEAT
        elif surprise_pct < -surprise_threshold:
            return EarningsPredictionType.MISS
        else:
            return EarningsPredictionType.MEET
