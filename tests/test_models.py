"""Tests for domain models."""

import pytest
from datetime import datetime

from src.models.cramer import CramerPick, CramerRecommendation
from src.models.congress import (
    CongressTrade,
    CongressMember,
    PoliticalParty,
    Chamber,
    TransactionType,
)
from src.models.mood import MarketMood, MoodSentiment, MoodIndicator
from src.models.earnings import EarningsEvent, EarningsPrediction, EarningsPredictionType
from src.models.beat_congress import BeatCongressGame, BeatCongressStatus


class TestCramerModels:
    """Tests for Cramer models."""

    def test_cramer_pick_creation(self):
        """Test creating a Cramer pick."""
        pick = CramerPick(
            id="test-1",
            ticker="AAPL",
            companyName="Apple Inc.",
            recommendation=CramerRecommendation.BUY,
            priceAtPick=150.0,
            currentPrice=160.0,
            returnPercent=6.67,
            inverseReturnPercent=-6.67,
            pickDate=datetime(2024, 1, 15),
        )

        assert pick.ticker == "AAPL"
        assert pick.recommendation == CramerRecommendation.BUY
        assert pick.is_winning is True  # BUY with positive return

    def test_cramer_pick_is_winning_buy(self):
        """Test is_winning for BUY recommendation."""
        pick = CramerPick(
            id="test-1",
            ticker="AAPL",
            companyName="Apple Inc.",
            recommendation=CramerRecommendation.BUY,
            priceAtPick=150.0,
            currentPrice=140.0,
            returnPercent=-6.67,
            inverseReturnPercent=6.67,
            pickDate=datetime(2024, 1, 15),
        )

        assert pick.is_winning is False  # BUY with negative return

    def test_cramer_pick_is_winning_sell(self):
        """Test is_winning for SELL recommendation."""
        pick = CramerPick(
            id="test-1",
            ticker="AAPL",
            companyName="Apple Inc.",
            recommendation=CramerRecommendation.SELL,
            priceAtPick=150.0,
            currentPrice=140.0,
            returnPercent=-6.67,
            inverseReturnPercent=6.67,
            pickDate=datetime(2024, 1, 15),
        )

        assert pick.is_winning is True  # SELL with negative price return is winning


class TestCongressModels:
    """Tests for Congress models."""

    def test_congress_trade_creation(self):
        """Test creating a Congress trade."""
        trade = CongressTrade(
            id="trade-1",
            memberId="pelosi-1",
            memberName="Nancy Pelosi",
            party=PoliticalParty.DEMOCRAT,
            chamber=Chamber.HOUSE,
            state="CA",
            ticker="NVDA",
            companyName="NVIDIA Corporation",
            transactionType=TransactionType.PURCHASE,
            transactionDate=datetime(2024, 1, 10),
            disclosureDate=datetime(2024, 2, 20),
            amountRangeLow=250001,
            amountRangeHigh=500000,
            daysToDisclose=41,
        )

        assert trade.memberName == "Nancy Pelosi"
        assert trade.party == PoliticalParty.DEMOCRAT
        assert trade.daysToDisclose == 41

    def test_amount_range_display(self):
        """Test amount range display formatting."""
        trade = CongressTrade(
            id="trade-1",
            memberId="test-1",
            memberName="Test Member",
            party=PoliticalParty.REPUBLICAN,
            chamber=Chamber.SENATE,
            state="TX",
            ticker="AAPL",
            companyName="Apple Inc.",
            transactionType=TransactionType.SALE,
            transactionDate=datetime(2024, 1, 1),
            disclosureDate=datetime(2024, 1, 15),
            amountRangeLow=1000001,
            amountRangeHigh=5000000,
            daysToDisclose=14,
        )

        assert "M" in trade.amount_range_display


class TestMoodModels:
    """Tests for Mood models."""

    def test_mood_sentiment_from_index(self):
        """Test MoodSentiment.from_index."""
        assert MoodSentiment.from_index(10) == MoodSentiment.EXTREME_FEAR
        assert MoodSentiment.from_index(30) == MoodSentiment.FEAR
        assert MoodSentiment.from_index(50) == MoodSentiment.NEUTRAL
        assert MoodSentiment.from_index(70) == MoodSentiment.GREED
        assert MoodSentiment.from_index(90) == MoodSentiment.EXTREME_GREED

    def test_market_mood_creation(self):
        """Test creating a MarketMood."""
        mood = MarketMood(
            fearGreedIndex=35,
            sentiment=MoodSentiment.FEAR,
            previousClose=40,
            weekAgo=50,
            monthAgo=45,
            yearAgo=55,
            updatedAt=datetime.utcnow(),
            indicators=[
                MoodIndicator(
                    name="VIX",
                    value=25.5,
                    contribution="Fear",
                    description="Market volatility",
                )
            ],
        )

        assert mood.fearGreedIndex == 35
        assert mood.change_from_yesterday == -5
        assert len(mood.indicators) == 1


class TestEarningsModels:
    """Tests for Earnings models."""

    def test_earnings_event_creation(self):
        """Test creating an EarningsEvent."""
        event = EarningsEvent(
            id="earnings-1",
            ticker="AAPL",
            companyName="Apple Inc.",
            earningsDate=datetime(2024, 2, 1),
            earningsTime="After",
            estimatedEPS=1.45,
        )

        assert event.ticker == "AAPL"
        assert event.predictionsClosed is False
        assert event.actualEPS is None


class TestBeatCongressModels:
    """Tests for Beat Congress models."""

    def test_beat_congress_game_creation(self):
        """Test creating a BeatCongressGame."""
        game = BeatCongressGame(
            id="game-1",
            userId="user-1",
            congressMemberId="pelosi-1",
            congressMemberName="Nancy Pelosi",
            congressMemberParty=PoliticalParty.DEMOCRAT,
            congressMemberChamber=Chamber.HOUSE,
            startDate=datetime(2024, 1, 1),
            endDate=datetime(2024, 1, 31),
            durationDays=30,
            status=BeatCongressStatus.ACTIVE,
            userReturnPercent=5.0,
            congressReturnPercent=3.0,
        )

        assert game.is_user_winning is True
        assert game.status == BeatCongressStatus.ACTIVE
