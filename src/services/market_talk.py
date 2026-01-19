"""Market Talk AI Podcast service."""

from datetime import datetime
from typing import Optional, List
import random

from src.models.market_talk import (
    MarketTalkEpisode,
    MarketTalkMessage,
    MarketTalkHost,
    MarketTalkResponse,
    MarketTalkLatestResponse,
)
from src.repositories.market_talk import MarketTalkRepository
from src.utils.logging import logger
from src.utils.errors import NotFoundError


class MarketTalkService:
    """Service for Market Talk AI Podcast business logic."""

    def __init__(self):
        self.repo = MarketTalkRepository()

        # Host personalities for generating dialogue
        self.host_traits = {
            MarketTalkHost.MIKE: {
                "name": "Mike",
                "personality": "bullish",
                "catchphrase": "This is the setup!",
                "style": "optimistic, sees opportunity everywhere",
            },
            MarketTalkHost.SARAH: {
                "name": "Sarah",
                "personality": "skeptical",
                "catchphrase": "Let's see the receipts.",
                "style": "cautious, data-driven, questions assumptions",
            },
        }

    def get_episodes(
        self, page: int = 1, page_size: int = 20
    ) -> MarketTalkResponse:
        """Get recent Market Talk episodes."""
        episodes, total = self.repo.get_episodes(page=page, page_size=page_size)

        # Check for live episode
        live_episode = self.repo.get_live_episode()

        total_pages = (total + page_size - 1) // page_size

        return MarketTalkResponse(
            episodes=episodes,
            liveEpisode=live_episode,
            page=page,
            pageSize=page_size,
            totalItems=total,
            totalPages=total_pages,
            hasMore=page < total_pages,
        )

    def get_episode_detail(self, episode_id: str) -> MarketTalkEpisode:
        """Get specific episode."""
        episode = self.repo.get_episode_by_id(episode_id)
        if not episode:
            raise NotFoundError("MarketTalkEpisode", episode_id)
        return episode

    def get_latest(self) -> MarketTalkLatestResponse:
        """Get latest Market Talk exchange for home card."""
        # Check for live first
        live_episode = self.repo.get_live_episode()
        if live_episode:
            return MarketTalkLatestResponse(
                episode=live_episode,
                latestMessages=live_episode.messages[-4:] if live_episode.messages else [],
                isLive=True,
            )

        # Get most recent episode
        latest = self.repo.get_latest_episode()
        if not latest:
            return MarketTalkLatestResponse(isLive=False)

        return MarketTalkLatestResponse(
            episode=latest,
            latestMessages=latest.messages[-4:] if latest.messages else [],
            isLive=False,
        )

    def generate_episode(
        self,
        topic: str,
        ticker: Optional[str] = None,
        message_count: int = 4,
    ) -> MarketTalkEpisode:
        """Generate a new Market Talk episode with AI dialogue.

        Note: This is a simplified version. In production, this would call
        an AI service (Claude) to generate the actual dialogue.
        """
        # Create title
        if ticker:
            title = f"Market Talk: {ticker} Discussion"
        else:
            title = f"Market Talk: {topic}"

        # Create episode
        episode = self.repo.create_episode(
            title=title,
            topic=topic,
            is_live=False,
            tickers=[ticker] if ticker else [],
        )

        # Generate placeholder dialogue
        # In production, this would call Claude API to generate real dialogue
        messages = self._generate_placeholder_dialogue(topic, ticker, message_count)

        for msg in messages:
            self.repo.add_message_to_episode(episode.id, msg)

        # Get updated episode
        return self.repo.get_episode_by_id(episode.id)

    def _generate_placeholder_dialogue(
        self,
        topic: str,
        ticker: Optional[str],
        count: int,
    ) -> List[MarketTalkMessage]:
        """Generate placeholder dialogue.

        In production, this would be replaced with actual AI-generated content.
        """
        messages = []
        hosts = [MarketTalkHost.MIKE, MarketTalkHost.SARAH]

        # Placeholder templates
        mike_templates = [
            f"I'm really liking what I see with {ticker or topic}. This is the setup!",
            f"Look, everyone's panicking about {topic}, but that's when you buy.",
            f"The fundamentals on {ticker or 'this sector'} are solid. I'm bullish here.",
            f"This pullback is a gift. I'm adding to my position.",
        ]

        sarah_templates = [
            f"Hold on, Mike. Let's look at the actual numbers on {ticker or topic}.",
            f"I need more data before I'd commit to {ticker or 'that'}. Let's see the receipts.",
            f"The market's been wrong before. What's the downside here?",
            f"I'm not saying sell, but the valuation looks stretched to me.",
        ]

        now = datetime.utcnow()

        for i in range(count):
            host = hosts[i % 2]
            templates = mike_templates if host == MarketTalkHost.MIKE else sarah_templates

            messages.append(
                MarketTalkMessage(
                    host=host,
                    text=random.choice(templates),
                    timestamp=now,
                    ticker=ticker,
                    sentiment="Bullish" if host == MarketTalkHost.MIKE else "Cautious",
                )
            )

        return messages

    def start_live_episode(
        self, topic: str, ticker: Optional[str] = None
    ) -> MarketTalkEpisode:
        """Start a live Market Talk episode."""
        # End any existing live episode
        current_live = self.repo.get_live_episode()
        if current_live:
            self.repo.end_live_episode(current_live.id)

        # Create new live episode
        if ticker:
            title = f"LIVE: {ticker} Analysis"
        else:
            title = f"LIVE: {topic}"

        episode = self.repo.create_episode(
            title=title,
            topic=topic,
            is_live=True,
            tickers=[ticker] if ticker else [],
        )

        logger.info("Started live Market Talk episode", id=episode.id, topic=topic)
        return episode

    def add_live_message(
        self,
        episode_id: str,
        host: str,
        text: str,
        ticker: Optional[str] = None,
        sentiment: Optional[str] = None,
    ) -> MarketTalkEpisode:
        """Add a message to a live episode."""
        try:
            host_enum = MarketTalkHost(host.upper())
        except ValueError:
            host_enum = MarketTalkHost.MIKE

        message = MarketTalkMessage(
            host=host_enum,
            text=text,
            timestamp=datetime.utcnow(),
            ticker=ticker,
            sentiment=sentiment,
        )

        episode = self.repo.add_message_to_episode(episode_id, message)
        if not episode:
            raise NotFoundError("MarketTalkEpisode", episode_id)

        return episode

    def end_live_episode(self, episode_id: str) -> MarketTalkEpisode:
        """End a live episode."""
        episode = self.repo.end_live_episode(episode_id)
        if not episode:
            raise NotFoundError("MarketTalkEpisode", episode_id)

        logger.info("Ended live Market Talk episode", id=episode_id)
        return episode

    def get_episodes_by_ticker(self, ticker: str, limit: int = 10) -> List[MarketTalkEpisode]:
        """Get episodes that discuss a specific ticker."""
        return self.repo.get_episodes_by_topic(ticker.upper(), limit=limit)
