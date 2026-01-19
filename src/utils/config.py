"""Configuration management."""

import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Environment
    environment: str = "dev"
    log_level: str = "info"

    # AWS
    aws_region: str = "us-east-1"
    dynamodb_table: str = "tradestreak-wall-street"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # External APIs
    quiver_quant_api_key: Optional[str] = None
    alpha_vantage_api_key: Optional[str] = None

    # XP Configuration
    xp_mood_prediction_correct: int = 25
    xp_earnings_prediction_correct: int = 50
    xp_beat_congress_win: int = 100

    # Cache TTLs (seconds)
    cache_ttl_cramer: int = 3600  # 1 hour
    cache_ttl_congress: int = 3600  # 1 hour
    cache_ttl_mood: int = 900  # 15 minutes
    cache_ttl_earnings: int = 1800  # 30 minutes

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
