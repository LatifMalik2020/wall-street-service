"""Shared normalization utilities for Wall Street Service."""

import re


def normalize_member_id(name: str) -> str:
    """Generate a consistent, URL-safe member ID from a name.

    All ingestion clients MUST use this function to ensure
    consistent member IDs across FMP, QuiverQuant, and any future sources.

    Examples:
        "Nancy Pelosi"    -> "nancy-pelosi"
        "Tommy Tuberville" -> "tommy-tuberville"
        "Dr. John Smith"   -> "dr-john-smith"
        "Nancy  Pelosi"    -> "nancy-pelosi"
    """
    if not name:
        return ""
    # Lowercase, strip whitespace
    normalized = name.lower().strip()
    # Replace periods, commas, apostrophes with nothing
    normalized = re.sub(r"[.,']", "", normalized)
    # Replace any whitespace/underscores with hyphens
    normalized = re.sub(r"[\s_]+", "-", normalized)
    # Remove any characters that aren't alphanumeric or hyphens
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    # Collapse multiple hyphens
    normalized = re.sub(r"-+", "-", normalized)
    # Strip leading/trailing hyphens
    return normalized.strip("-")
