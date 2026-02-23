"""QuiverQuant API client for Congress trading data."""

import httpx
from datetime import datetime, timedelta
from typing import List, Optional
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


class QuiverQuantClient:
    """Client for QuiverQuant Congress trading API.

    QuiverQuant provides free access to congressional trading data.
    Documentation: https://www.quiverquant.com/api
    """

    BASE_URL = "https://api.quiverquant.com/beta"

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.quiver_quant_api_key
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_congress_trades(
        self,
        days_back: int = 30,
    ) -> List[CongressTrade]:
        """Fetch recent Congress trading data."""
        try:
            # QuiverQuant endpoint for Congress trades
            response = await self.client.get(
                "/historical/congresstrading",
                params={"limit": 500},
            )
            response.raise_for_status()
            data = response.json()

            trades = []
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            for item in data:
                try:
                    trade = self._parse_trade(item)
                    if trade and trade.disclosureDate >= cutoff_date:
                        trades.append(trade)
                except Exception as e:
                    logger.warning("Failed to parse trade", error=str(e), item=item)
                    continue

            logger.info("Fetched Congress trades from QuiverQuant", count=len(trades))
            return trades

        except httpx.HTTPError as e:
            logger.error("QuiverQuant API error", error=str(e))
            raise ExternalAPIError("QuiverQuant", str(e))

    async def fetch_congress_members(self) -> List[CongressMember]:
        """Fetch Congress member profiles.

        Note: QuiverQuant doesn't have a dedicated members endpoint,
        so we aggregate from trades data.
        """
        try:
            # Fetch trades and aggregate unique members
            trades = await self.fetch_congress_trades(days_back=365)

            members_dict = {}
            for trade in trades:
                if trade.memberId not in members_dict:
                    members_dict[trade.memberId] = {
                        "id": trade.memberId,
                        "name": trade.memberName,
                        "party": trade.party,
                        "chamber": trade.chamber,
                        "state": trade.state,
                        "trades": [],
                    }
                members_dict[trade.memberId]["trades"].append(trade)

            # Create member objects with stats
            members = []
            for member_id, data in members_dict.items():
                trades_list = data["trades"]
                avg_disclosure = sum(t.daysToDisclose for t in trades_list) / len(trades_list)

                # Calculate estimated return (simplified)
                total_return = sum(
                    (t.returnSinceTransaction or 0) for t in trades_list
                )
                avg_return = total_return / len(trades_list) if trades_list else 0

                # Get top holdings
                ticker_counts = {}
                for t in trades_list:
                    if t.transactionType in [TransactionType.PURCHASE]:
                        ticker_counts[t.ticker] = ticker_counts.get(t.ticker, 0) + 1
                top_holdings = sorted(ticker_counts.keys(), key=lambda x: ticker_counts[x], reverse=True)[:5]

                member = CongressMember(
                    id=member_id,
                    name=data["name"],
                    party=data["party"],
                    chamber=data["chamber"],
                    state=data["state"],
                    totalTrades=len(trades_list),
                    estimatedPortfolioReturn=round(avg_return, 2),
                    avgDaysToDisclose=round(avg_disclosure, 1),
                    topHoldings=top_holdings,
                )
                members.append(member)

            logger.info("Aggregated Congress members", count=len(members))
            return members

        except Exception as e:
            logger.error("Failed to fetch Congress members", error=str(e))
            raise ExternalAPIError("QuiverQuant", str(e))

    def _parse_trade(self, item: dict) -> Optional[CongressTrade]:
        """Parse QuiverQuant trade data to CongressTrade model."""
        try:
            # Parse party
            party_str = item.get("Party", "D")
            party = PoliticalParty.DEMOCRAT
            if party_str == "R":
                party = PoliticalParty.REPUBLICAN
            elif party_str == "I":
                party = PoliticalParty.INDEPENDENT

            # Parse chamber
            chamber_str = item.get("House", "House")
            chamber = Chamber.HOUSE if "House" in chamber_str else Chamber.SENATE

            # Parse transaction type
            tx_type_str = item.get("Transaction", "Purchase")
            if "Sale" in tx_type_str:
                if "Full" in tx_type_str:
                    tx_type = TransactionType.SALE_FULL
                elif "Partial" in tx_type_str:
                    tx_type = TransactionType.SALE_PARTIAL
                else:
                    tx_type = TransactionType.SALE
            elif "Exchange" in tx_type_str:
                tx_type = TransactionType.EXCHANGE
            else:
                tx_type = TransactionType.PURCHASE

            # Parse dates
            tx_date = datetime.strptime(item.get("TransactionDate", "2024-01-01"), "%Y-%m-%d")
            disc_date = datetime.strptime(item.get("ReportDate", item.get("TransactionDate", "2024-01-01")), "%Y-%m-%d")

            # Parse amount range
            amount_str = item.get("Range", "$1,001 - $15,000")
            amount_low, amount_high = self._parse_amount_range(amount_str)

            # Calculate days to disclose
            days_to_disclose = (disc_date - tx_date).days

            # Generate ID from data
            member_name = item.get("Representative", "Unknown")
            ticker = item.get("Ticker", "UNKNOWN")
            member_id = normalize_member_id(member_name)
            trade_id = f"{disc_date.strftime('%Y%m%d')}_{member_id}_{ticker}"

            return CongressTrade(
                id=trade_id,
                memberId=member_id,
                memberName=member_name,
                party=party,
                chamber=chamber,
                state=item.get("State", ""),
                ticker=ticker,
                companyName=item.get("Asset", ticker),
                transactionType=tx_type,
                transactionDate=tx_date,
                disclosureDate=disc_date,
                amountRangeLow=amount_low,
                amountRangeHigh=amount_high,
                daysToDisclose=max(0, days_to_disclose),
            )

        except Exception as e:
            logger.warning("Failed to parse QuiverQuant trade", error=str(e))
            return None

    def _parse_amount_range(self, range_str: str) -> tuple:
        """Parse amount range string to (low, high) integers."""
        # Common ranges from congressional disclosures
        ranges = {
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
