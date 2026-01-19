"""Earnings Predictions repository."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from decimal import Decimal

from src.models.earnings import (
    EarningsEvent,
    EarningsPrediction,
    EarningsPredictionType,
    UserEarningsStats,
)
from src.repositories.base import DynamoDBRepository
from src.utils.logging import logger


class EarningsRepository(DynamoDBRepository):
    """Repository for Earnings data."""

    # DynamoDB key patterns
    PK_EARNINGS = "EARNINGS"
    SK_EVENT_PREFIX = "EVENT#"
    PK_USER_PREFIX = "USER#"
    SK_EARNINGS_PRED_PREFIX = "EARNINGS_PRED#"
    SK_EARNINGS_STATS = "EARNINGS_STATS"

    def get_upcoming_events(
        self, days_ahead: int = 14, page: int = 1, page_size: int = 20
    ) -> Tuple[List[EarningsEvent], int]:
        """Get upcoming earnings events."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        end_date = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        items, total = self._query_paginated(
            pk=self.PK_EARNINGS,
            page=page,
            page_size=page_size,
            sk_begins_with=self.SK_EVENT_PREFIX,
            scan_index_forward=True,  # Earliest first
        )

        events = []
        for item in items:
            event = self._item_to_event(item)
            # Filter to date range
            event_date = event.earningsDate.strftime("%Y-%m-%d")
            if today <= event_date <= end_date:
                events.append(event)

        return events, total

    def get_event_by_id(self, event_id: str) -> Optional[EarningsEvent]:
        """Get single earnings event."""
        item = self._get_item(pk=self.PK_EARNINGS, sk=f"{self.SK_EVENT_PREFIX}{event_id}")
        return self._item_to_event(item) if item else None

    def get_event_by_ticker(self, ticker: str) -> Optional[EarningsEvent]:
        """Get upcoming earnings event for a ticker."""
        items = self._query(
            pk=self.PK_EARNINGS,
            sk_begins_with=self.SK_EVENT_PREFIX,
            limit=100,
        )

        today = datetime.utcnow()
        for item in items:
            event = self._item_to_event(item)
            if event.ticker.upper() == ticker.upper() and event.earningsDate >= today:
                return event
        return None

    def save_event(self, event: EarningsEvent) -> None:
        """Save earnings event."""
        event_id = f"{event.earningsDate.strftime('%Y-%m-%d')}#{event.ticker}"

        item = {
            "PK": self.PK_EARNINGS,
            "SK": f"{self.SK_EVENT_PREFIX}{event_id}",
            "id": event.id,
            "ticker": event.ticker,
            "companyName": event.companyName,
            "earningsDate": event.earningsDate.isoformat(),
            "earningsTime": event.earningsTime,
            "estimatedEPS": Decimal(str(event.estimatedEPS)) if event.estimatedEPS else None,
            "actualEPS": Decimal(str(event.actualEPS)) if event.actualEPS else None,
            "estimatedRevenue": Decimal(str(event.estimatedRevenue)) if event.estimatedRevenue else None,
            "actualRevenue": Decimal(str(event.actualRevenue)) if event.actualRevenue else None,
            "surprise": Decimal(str(event.surprise)) if event.surprise else None,
            "predictionsClosed": event.predictionsClosed,
            "totalPredictions": event.totalPredictions,
            "beatPredictions": event.beatPredictions,
            "meetPredictions": event.meetPredictions,
            "missPredictions": event.missPredictions,
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
            # GSI for ticker lookup
            "GSI1PK": f"TICKER#{event.ticker}",
            "GSI1SK": f"EARNINGS#{event.earningsDate.strftime('%Y-%m-%d')}",
        }
        item = {k: v for k, v in item.items() if v is not None}
        self._put_item(item)
        logger.info("Saved earnings event", ticker=event.ticker, date=event.earningsDate)

    def update_event_results(
        self,
        event_id: str,
        actual_eps: float,
        actual_revenue: Optional[float] = None,
    ) -> Optional[EarningsEvent]:
        """Update event with actual results."""
        event = self.get_event_by_id(event_id)
        if not event:
            return None

        # Calculate surprise
        surprise = None
        if event.estimatedEPS and event.estimatedEPS != 0:
            surprise = ((actual_eps - event.estimatedEPS) / abs(event.estimatedEPS)) * 100

        update_expr = "SET actualEPS = :eps, surprise = :surp, predictionsClosed = :closed, updatedAt = :ua"
        expr_values = {
            ":eps": Decimal(str(actual_eps)),
            ":surp": Decimal(str(round(surprise, 2))) if surprise else None,
            ":closed": True,
            ":ua": self._now_iso(),
        }

        if actual_revenue:
            update_expr += ", actualRevenue = :rev"
            expr_values[":rev"] = Decimal(str(actual_revenue))

        updated = self._update_item(
            pk=self.PK_EARNINGS,
            sk=f"{self.SK_EVENT_PREFIX}{event_id}",
            update_expression=update_expr,
            expression_values={k: v for k, v in expr_values.items() if v is not None},
        )
        return self._item_to_event(updated)

    def increment_prediction_count(
        self, event_id: str, prediction_type: EarningsPredictionType
    ) -> None:
        """Increment prediction count for an event."""
        count_field = f"{prediction_type.value.lower()}Predictions"

        self._update_item(
            pk=self.PK_EARNINGS,
            sk=f"{self.SK_EVENT_PREFIX}{event_id}",
            update_expression=f"SET totalPredictions = totalPredictions + :one, {count_field} = {count_field} + :one",
            expression_values={":one": 1},
        )

    # User predictions
    def get_user_prediction(
        self, user_id: str, event_id: str
    ) -> Optional[EarningsPrediction]:
        """Get user's prediction for an event."""
        item = self._get_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_EARNINGS_PRED_PREFIX}{event_id}",
        )
        return self._item_to_prediction(item) if item else None

    def get_user_predictions(
        self, user_id: str, limit: int = 50
    ) -> List[EarningsPrediction]:
        """Get user's earnings predictions."""
        items = self._query(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk_begins_with=self.SK_EARNINGS_PRED_PREFIX,
            limit=limit,
            scan_index_forward=False,
        )
        return [self._item_to_prediction(item) for item in items]

    def save_prediction(self, prediction: EarningsPrediction) -> None:
        """Save user's earnings prediction."""
        item = {
            "PK": f"{self.PK_USER_PREFIX}{prediction.userId}",
            "SK": f"{self.SK_EARNINGS_PRED_PREFIX}{prediction.eventId}",
            "userId": prediction.userId,
            "eventId": prediction.eventId,
            "ticker": prediction.ticker,
            "prediction": prediction.prediction.value,
            "createdAt": prediction.createdAt.isoformat(),
            "isCorrect": prediction.isCorrect,
            "xpAwarded": prediction.xpAwarded,
            # GSI for finding all predictions for an event
            "GSI1PK": f"EVENT_PREDICTIONS#{prediction.eventId}",
            "GSI1SK": prediction.userId,
        }
        item = {k: v for k, v in item.items() if v is not None}
        self._put_item(item)
        logger.info(
            "Saved earnings prediction",
            user=prediction.userId,
            ticker=prediction.ticker,
            prediction=prediction.prediction,
        )

    def resolve_prediction(
        self, user_id: str, event_id: str, is_correct: bool
    ) -> Optional[EarningsPrediction]:
        """Resolve a prediction with actual results."""
        xp_awarded = 50 if is_correct else 0

        updated = self._update_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=f"{self.SK_EARNINGS_PRED_PREFIX}{event_id}",
            update_expression="SET isCorrect = :ic, xpAwarded = :xp",
            expression_values={":ic": is_correct, ":xp": xp_awarded},
        )
        return self._item_to_prediction(updated)

    def get_predictions_for_event(self, event_id: str) -> List[EarningsPrediction]:
        """Get all predictions for an event (for batch resolution)."""
        items = self._query(
            pk=f"EVENT_PREDICTIONS#{event_id}",
            index_name="GSI1",
        )
        return [self._item_to_prediction(item) for item in items]

    # User stats
    def get_user_stats(self, user_id: str) -> UserEarningsStats:
        """Get user's earnings prediction stats."""
        item = self._get_item(
            pk=f"{self.PK_USER_PREFIX}{user_id}",
            sk=self.SK_EARNINGS_STATS,
        )

        if not item:
            return UserEarningsStats()

        return UserEarningsStats(
            totalPredictions=int(item.get("totalPredictions", 0)),
            correctPredictions=int(item.get("correctPredictions", 0)),
            accuracy=float(item.get("accuracy", 0)),
            currentStreak=int(item.get("currentStreak", 0)),
            longestStreak=int(item.get("longestStreak", 0)),
            totalXpEarned=int(item.get("totalXpEarned", 0)),
        )

    def update_user_stats(self, user_id: str, is_correct: bool, xp: int) -> None:
        """Update user stats after prediction resolution."""
        stats = self.get_user_stats(user_id)

        new_total = stats.totalPredictions + 1
        new_correct = stats.correctPredictions + (1 if is_correct else 0)
        new_accuracy = (new_correct / new_total) * 100 if new_total > 0 else 0
        new_streak = (stats.currentStreak + 1) if is_correct else 0
        new_longest = max(stats.longestStreak, new_streak)
        new_xp = stats.totalXpEarned + xp

        item = {
            "PK": f"{self.PK_USER_PREFIX}{user_id}",
            "SK": self.SK_EARNINGS_STATS,
            "totalPredictions": new_total,
            "correctPredictions": new_correct,
            "accuracy": Decimal(str(round(new_accuracy, 1))),
            "currentStreak": new_streak,
            "longestStreak": new_longest,
            "totalXpEarned": new_xp,
            "updatedAt": self._now_iso(),
        }
        self._put_item(item)

    def _item_to_event(self, item: dict) -> EarningsEvent:
        """Convert DynamoDB item to EarningsEvent model."""
        return EarningsEvent(
            id=item.get("id", ""),
            ticker=item.get("ticker", ""),
            companyName=item.get("companyName", ""),
            earningsDate=datetime.fromisoformat(item.get("earningsDate", datetime.utcnow().isoformat())),
            earningsTime=item.get("earningsTime", "After"),
            estimatedEPS=float(item["estimatedEPS"]) if item.get("estimatedEPS") else None,
            actualEPS=float(item["actualEPS"]) if item.get("actualEPS") else None,
            estimatedRevenue=float(item["estimatedRevenue"]) if item.get("estimatedRevenue") else None,
            actualRevenue=float(item["actualRevenue"]) if item.get("actualRevenue") else None,
            surprise=float(item["surprise"]) if item.get("surprise") else None,
            predictionsClosed=item.get("predictionsClosed", False),
            totalPredictions=int(item.get("totalPredictions", 0)),
            beatPredictions=int(item.get("beatPredictions", 0)),
            meetPredictions=int(item.get("meetPredictions", 0)),
            missPredictions=int(item.get("missPredictions", 0)),
        )

    def _item_to_prediction(self, item: dict) -> EarningsPrediction:
        """Convert DynamoDB item to EarningsPrediction model."""
        return EarningsPrediction(
            userId=item.get("userId", ""),
            eventId=item.get("eventId", ""),
            ticker=item.get("ticker", ""),
            prediction=EarningsPredictionType(item.get("prediction", "MEET")),
            createdAt=datetime.fromisoformat(item.get("createdAt", datetime.utcnow().isoformat())),
            isCorrect=item.get("isCorrect"),
            xpAwarded=int(item.get("xpAwarded", 0)),
        )
