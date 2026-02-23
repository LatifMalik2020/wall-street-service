"""Financial Modeling Prep (FMP) API client for Congress trading data.

FMP provides clean, structured congressional trading data via their Stable API.
This is our PRIMARY data source for daily ingestion.

Endpoints used:
- GET /stable/senate-latest - Latest Senate trades
- GET /stable/house-latest - Latest House trades
- GET /stable/senate-trading-by-name?name=Nancy+Pelosi - Per-member queries

Pricing: $25/mo Starter plan
Docs: https://site.financialmodelingprep.com/developer/docs/stable
"""

import httpx
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import uuid

from src.models.congress import (
    CongressTrade,
    CongressMember,
    PoliticalParty,
    Chamber,
    TransactionType,
)
from src.utils.config import get_settings
from src.utils.logging import logger
from src.utils.errors import ExternalAPIError
from src.utils.normalize import normalize_member_id


class FMPClient:
    """Client for Financial Modeling Prep Congress trading API."""

    BASE_URL = "https://financialmodelingprep.com"

    def __init__(self):
        self.settings = get_settings()
        self.api_key = getattr(self.settings, "fmp_api_key", None)
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_senate_latest(self, limit: int = 100) -> List[CongressTrade]:
        """Fetch latest Senate trading disclosures."""
        return await self._fetch_trades("/stable/senate-latest", Chamber.SENATE, limit)

    async def fetch_house_latest(self, limit: int = 100) -> List[CongressTrade]:
        """Fetch latest House trading disclosures."""
        return await self._fetch_trades("/stable/house-latest", Chamber.HOUSE, limit)

    async def fetch_all_latest(self, limit: int = 200) -> List[CongressTrade]:
        """Fetch latest trades from both chambers."""
        senate = await self.fetch_senate_latest(limit=limit)
        house = await self.fetch_house_latest(limit=limit)
        all_trades = senate + house
        all_trades.sort(key=lambda t: t.disclosureDate, reverse=True)
        return all_trades

    async def fetch_trades_by_name(
        self, name: str, chamber: str = "senate"
    ) -> List[CongressTrade]:
        """Fetch trades for a specific Congress member by name."""
        endpoint = f"/stable/{chamber}-trading-by-name"
        chamber_enum = Chamber.SENATE if chamber == "senate" else Chamber.HOUSE

        try:
            response = await self.client.get(
                endpoint,
                params={"name": name, "apikey": self.api_key},
            )
            response.raise_for_status()
            data = response.json()

            trades = []
            for item in data:
                trade = self._parse_fmp_trade(item, chamber_enum)
                if trade:
                    trades.append(trade)

            logger.info(
                "Fetched FMP trades by name",
                name=name,
                chamber=chamber,
                count=len(trades),
            )
            return trades

        except httpx.HTTPError as e:
            logger.error("FMP API error", endpoint=endpoint, error=str(e))
            raise ExternalAPIError("FMP", str(e))

    async def _fetch_trades(
        self, endpoint: str, chamber: Chamber, limit: int
    ) -> List[CongressTrade]:
        """Generic trade fetcher for FMP endpoints."""
        if not self.api_key:
            logger.warning("FMP API key not configured, skipping fetch")
            return []

        try:
            response = await self.client.get(
                endpoint,
                params={"apikey": self.api_key, "limit": limit},
            )
            response.raise_for_status()
            data = response.json()

            trades = []
            for item in data:
                trade = self._parse_fmp_trade(item, chamber)
                if trade:
                    trades.append(trade)

            logger.info(
                "Fetched FMP trades",
                endpoint=endpoint,
                count=len(trades),
            )
            return trades

        except httpx.HTTPError as e:
            logger.error("FMP API error", endpoint=endpoint, error=str(e))
            raise ExternalAPIError("FMP", str(e))

    def _parse_fmp_trade(
        self, item: dict, default_chamber: Chamber
    ) -> Optional[CongressTrade]:
        """Parse FMP trade data to CongressTrade model.

        FMP trade format:
        {
            "firstName": "Nancy",
            "lastName": "Pelosi",
            "office": "House",
            "link": "...",
            "dateRecieved": "2024-01-15",
            "transactionDate": "2024-01-02",
            "owner": "SP",
            "assetDescription": "NVIDIA Corporation",
            "assetType": "Stock",
            "type": "Purchase",
            "amount": "$1,001 - $15,000",
            "comment": "",
            "symbol": "NVDA"
        }
        """
        try:
            first_name = item.get("firstName", "")
            last_name = item.get("lastName", "")
            full_name = f"{first_name} {last_name}".strip()

            if not full_name:
                return None

            # Parse party from office or default
            office = item.get("office", "")
            if "Senate" in office:
                chamber = Chamber.SENATE
            elif "House" in office:
                chamber = Chamber.HOUSE
            else:
                chamber = default_chamber

            # Parse transaction type
            tx_type_str = item.get("type", "Purchase")
            tx_type = self._parse_transaction_type(tx_type_str)

            # Parse dates
            tx_date_str = item.get("transactionDate", "")
            disc_date_str = item.get("dateRecieved", item.get("dateReceived", ""))

            tx_date = self._parse_date(tx_date_str)
            disc_date = self._parse_date(disc_date_str) or tx_date

            if not tx_date:
                return None

            # Parse amount
            amount_str = item.get("amount", "$1,001 - $15,000")
            amount_low, amount_high = self._parse_amount_range(amount_str)

            # Calculate days to disclose
            days_to_disclose = (disc_date - tx_date).days if disc_date and tx_date else 0

            ticker = item.get("symbol", "").upper()
            company_name = item.get("assetDescription", ticker)

            # Generate member ID (normalized across all sources)
            member_id = normalize_member_id(full_name)

            # Generate unique trade ID
            trade_id = (
                f"{disc_date.strftime('%Y%m%d') if disc_date else 'unknown'}"
                f"_{member_id}_{ticker}"
            )

            return CongressTrade(
                id=trade_id,
                memberId=member_id,
                memberName=full_name,
                party=PoliticalParty.DEMOCRAT,  # FMP doesn't reliably provide party
                chamber=chamber,
                state="",  # FMP doesn't provide state
                ticker=ticker,
                companyName=company_name,
                transactionType=tx_type,
                transactionDate=tx_date,
                disclosureDate=disc_date or tx_date,
                amountRangeLow=amount_low,
                amountRangeHigh=amount_high,
                daysToDisclose=max(0, days_to_disclose),
            )

        except Exception as e:
            logger.warning("Failed to parse FMP trade", error=str(e))
            return None

    def _parse_transaction_type(self, tx_str: str) -> TransactionType:
        """Parse FMP transaction type string."""
        tx_lower = tx_str.lower()
        if "sale" in tx_lower:
            if "full" in tx_lower:
                return TransactionType.SALE_FULL
            elif "partial" in tx_lower:
                return TransactionType.SALE_PARTIAL
            return TransactionType.SALE
        elif "exchange" in tx_lower:
            return TransactionType.EXCHANGE
        return TransactionType.PURCHASE

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in various formats."""
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _parse_amount_range(self, range_str: str) -> tuple:
        """Parse FMP amount range string."""
        ranges = {
            "$1 - $1,000": (1, 1000),
            "$1,001 - $15,000": (1001, 15000),
            "$15,001 - $50,000": (15001, 50000),
            "$50,001 - $100,000": (50001, 100000),
            "$100,001 - $250,000": (100001, 250000),
            "$250,001 - $500,000": (250001, 500000),
            "$500,001 - $1,000,000": (500001, 1000000),
            "$1,000,001 - $5,000,000": (1000001, 5000000),
            "$5,000,001 - $25,000,000": (5000001, 25000000),
            "$25,000,001 - $50,000,000": (25000001, 50000000),
            "Over $50,000,000": (50000001, 100000000),
        }
        return ranges.get(range_str, (1001, 15000))
