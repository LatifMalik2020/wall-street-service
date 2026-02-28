"""HTTP handlers for Wall Street Service API."""

from src.handlers.cramer import (
    get_cramer_picks,
    get_cramer_pick_detail,
    get_cramer_stats,
)
from src.handlers.congress import (
    get_congress_trades,
    get_congress_trade_detail,
    get_congress_members,
    get_congress_member_detail,
    get_congress_member_trades,
    backfill_member_trades,
)
from src.handlers.mood import (
    get_market_mood,
    submit_mood_prediction,
    get_user_mood_predictions,
)
from src.handlers.earnings import (
    get_upcoming_earnings,
    get_earnings_event_detail,
    submit_earnings_prediction,
    get_user_earnings_predictions,
    get_user_earnings_stats,
)
from src.handlers.beat_congress import (
    get_beat_congress_games,
    get_beat_congress_game_detail,
    create_beat_congress_game,
    get_beat_congress_leaderboard,
    get_challengeable_members,
)
from src.handlers.market_talk import (
    get_market_talk_episodes,
    get_market_talk_episode_detail,
    get_market_talk_latest,
    generate_market_talk,
)
from src.handlers.stocks import (
    get_stock_detail,
    get_stock_ratios,
    get_stock_financials,
    get_stock_short_interest,
    get_stock_technicals,
    get_ipos,
    get_market_status,
    get_stock_filings,
)

__all__ = [
    # Cramer
    "get_cramer_picks",
    "get_cramer_pick_detail",
    "get_cramer_stats",
    # Congress
    "get_congress_trades",
    "get_congress_trade_detail",
    "get_congress_members",
    "get_congress_member_detail",
    "get_congress_member_trades",
    "backfill_member_trades",
    # Mood
    "get_market_mood",
    "submit_mood_prediction",
    "get_user_mood_predictions",
    # Earnings
    "get_upcoming_earnings",
    "get_earnings_event_detail",
    "submit_earnings_prediction",
    "get_user_earnings_predictions",
    "get_user_earnings_stats",
    # Beat Congress
    "get_beat_congress_games",
    "get_beat_congress_game_detail",
    "create_beat_congress_game",
    "get_beat_congress_leaderboard",
    "get_challengeable_members",
    # Market Talk
    "get_market_talk_episodes",
    "get_market_talk_episode_detail",
    "get_market_talk_latest",
    "generate_market_talk",
    # Stocks
    "get_stock_detail",
    "get_stock_ratios",
    "get_stock_financials",
    "get_stock_short_interest",
    "get_stock_technicals",
    "get_ipos",
    "get_market_status",
    "get_stock_filings",
]
