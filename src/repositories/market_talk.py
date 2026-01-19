"""Market Talk repository."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import uuid

from src.models.market_talk import (
    MarketTalkEpisode,
    MarketTalkMessage,
    MarketTalkHost,
)
from src.repositories.base import DynamoDBRepository
from src.utils.logging import logger


class MarketTalkRepository(DynamoDBRepository):
    """Repository for Market Talk episodes."""

    # DynamoDB key patterns
    PK_MARKET_TALK = "MARKET_TALK"
    SK_EPISODE_PREFIX = "EPISODE#"
    SK_CURRENT = "CURRENT_LIVE"

    def get_episodes(
        self, page: int = 1, page_size: int = 20
    ) -> Tuple[List[MarketTalkEpisode], int]:
        """Get recent Market Talk episodes."""
        items, total = self._query_paginated(
            pk=self.PK_MARKET_TALK,
            page=page,
            page_size=page_size,
            sk_begins_with=self.SK_EPISODE_PREFIX,
            scan_index_forward=False,  # Most recent first
        )
        return [self._item_to_episode(item) for item in items], total

    def get_episode_by_id(self, episode_id: str) -> Optional[MarketTalkEpisode]:
        """Get specific episode."""
        item = self._get_item(
            pk=self.PK_MARKET_TALK,
            sk=f"{self.SK_EPISODE_PREFIX}{episode_id}",
        )
        return self._item_to_episode(item) if item else None

    def get_live_episode(self) -> Optional[MarketTalkEpisode]:
        """Get current live episode if any."""
        item = self._get_item(pk=self.PK_MARKET_TALK, sk=self.SK_CURRENT)
        if not item:
            return None
        # Get actual episode
        episode_id = item.get("episodeId")
        if episode_id:
            return self.get_episode_by_id(episode_id)
        return None

    def get_latest_episode(self) -> Optional[MarketTalkEpisode]:
        """Get most recent episode."""
        items = self._query(
            pk=self.PK_MARKET_TALK,
            sk_begins_with=self.SK_EPISODE_PREFIX,
            limit=1,
            scan_index_forward=False,
        )
        return self._item_to_episode(items[0]) if items else None

    def save_episode(self, episode: MarketTalkEpisode) -> None:
        """Save a Market Talk episode."""
        messages_data = [
            {
                "host": msg.host.value,
                "text": msg.text,
                "timestamp": msg.timestamp.isoformat(),
                "ticker": msg.ticker,
                "sentiment": msg.sentiment,
            }
            for msg in episode.messages
        ]

        item = {
            "PK": self.PK_MARKET_TALK,
            "SK": f"{self.SK_EPISODE_PREFIX}{episode.createdAt.strftime('%Y-%m-%dT%H:%M:%S')}#{episode.id}",
            "id": episode.id,
            "title": episode.title,
            "topic": episode.topic,
            "messages": messages_data,
            "createdAt": episode.createdAt.isoformat(),
            "isLive": episode.isLive,
            "tickersMentioned": episode.tickersMentioned,
            "audioUrl": episode.audioUrl,
            "duration": episode.duration,
            "updatedAt": self._now_iso(),
            # GSI for topic-based queries
            "GSI1PK": f"TOPIC#{episode.topic}",
            "GSI1SK": episode.createdAt.isoformat(),
        }
        item = {k: v for k, v in item.items() if v is not None}
        self._put_item(item)

        # If live, update current live pointer
        if episode.isLive:
            self._put_item({
                "PK": self.PK_MARKET_TALK,
                "SK": self.SK_CURRENT,
                "episodeId": episode.id,
                "updatedAt": self._now_iso(),
            })

        logger.info("Saved Market Talk episode", id=episode.id, topic=episode.topic)

    def add_message_to_episode(
        self, episode_id: str, message: MarketTalkMessage
    ) -> Optional[MarketTalkEpisode]:
        """Add a message to an existing episode."""
        episode = self.get_episode_by_id(episode_id)
        if not episode:
            return None

        # Get current messages
        episode.messages.append(message)

        # Update tickers mentioned
        if message.ticker and message.ticker not in episode.tickersMentioned:
            episode.tickersMentioned.append(message.ticker)

        # Save updated episode
        self.save_episode(episode)
        return episode

    def end_live_episode(self, episode_id: str) -> Optional[MarketTalkEpisode]:
        """Mark episode as no longer live."""
        # Find the episode
        episode = self.get_episode_by_id(episode_id)
        if not episode:
            return None

        episode.isLive = False
        self.save_episode(episode)

        # Clear live pointer
        self._delete_item(pk=self.PK_MARKET_TALK, sk=self.SK_CURRENT)

        return episode

    def get_episodes_by_topic(
        self, topic: str, limit: int = 10
    ) -> List[MarketTalkEpisode]:
        """Get episodes for a specific topic."""
        items = self._query(
            pk=f"TOPIC#{topic}",
            index_name="GSI1",
            limit=limit,
            scan_index_forward=False,
        )
        return [self._item_to_episode(item) for item in items]

    def create_episode(
        self,
        title: str,
        topic: str,
        is_live: bool = False,
        tickers: Optional[List[str]] = None,
    ) -> MarketTalkEpisode:
        """Create a new Market Talk episode."""
        episode = MarketTalkEpisode(
            id=str(uuid.uuid4())[:8],
            title=title,
            topic=topic,
            messages=[],
            createdAt=datetime.utcnow(),
            isLive=is_live,
            tickersMentioned=tickers or [],
        )
        self.save_episode(episode)
        return episode

    def _item_to_episode(self, item: dict) -> MarketTalkEpisode:
        """Convert DynamoDB item to MarketTalkEpisode model."""
        messages = []
        for msg_data in item.get("messages", []):
            messages.append(
                MarketTalkMessage(
                    host=MarketTalkHost(msg_data.get("host", "MIKE")),
                    text=msg_data.get("text", ""),
                    timestamp=datetime.fromisoformat(msg_data.get("timestamp", datetime.utcnow().isoformat())),
                    ticker=msg_data.get("ticker"),
                    sentiment=msg_data.get("sentiment"),
                )
            )

        return MarketTalkEpisode(
            id=item.get("id", ""),
            title=item.get("title", ""),
            topic=item.get("topic", ""),
            messages=messages,
            createdAt=datetime.fromisoformat(item.get("createdAt", datetime.utcnow().isoformat())),
            isLive=item.get("isLive", False),
            tickersMentioned=item.get("tickersMentioned", []),
            audioUrl=item.get("audioUrl"),
            duration=item.get("duration"),
        )
