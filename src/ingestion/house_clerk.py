"""House Clerk congress-trade source — primary-source replacement for Quiver.

Adapts src/ingestion/house_ptr.py (Clerk of the House disclosure index +
e-filed PTR PDFs) to the CongressTrade model so the existing scheduler,
repository, and API serve it unchanged. Free, no API key, updated daily.

Coverage honesty: e-filed PTRs only (~89% of filings; paper scans have no
text layer). Party is UNKNOWN (the Clerk's index doesn't carry it); the
member-profile enrichment path can fill it later. Senate eFD is phase 2.
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from src.ingestion import house_ptr, legislators
from src.models.congress import Chamber, CongressTrade, PoliticalParty, TransactionType
from src.utils.logging import logger
from src.utils.normalize import normalize_member_id

_TX_TYPES = {
    "buy": TransactionType.PURCHASE,
    "sell": TransactionType.SALE_FULL,
    "sell_partial": TransactionType.SALE_PARTIAL,
    "exchange": TransactionType.EXCHANGE,
}


def _parse_date(raw: str) -> Optional[datetime]:
    """Clerk dates come as MM/DD/YYYY (trades) or M/D/YYYY (index)."""
    for fmt in ("%m/%d/%Y",):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def to_congress_trade(filing: "house_ptr.PTRFiling", trade: "house_ptr.PTRTrade",
                      row: int,
                      member_info: Optional[dict] = None) -> Optional[CongressTrade]:
    """One parsed PTR row -> CongressTrade (pure; None if dates unparseable).
    member_info (from legislators.lookup) supplies party + canonical name."""
    tx_date = _parse_date(trade.transaction_date)
    disc_date = _parse_date(filing.filing_date) or _parse_date(trade.notification_date)
    if not tx_date or not disc_date:
        return None
    member_name = (member_info or {}).get("fullName") or filing.member
    party = {"D": PoliticalParty.DEMOCRAT, "R": PoliticalParty.REPUBLICAN,
             "I": PoliticalParty.INDEPENDENT}.get(
                 (member_info or {}).get("party", ""), PoliticalParty.UNKNOWN)
    member_id = normalize_member_id(member_name)
    return CongressTrade(
        # doc_id + row keeps ids unique when a member trades a ticker twice
        # in one filing (FMP's date_member_ticker scheme collapsed those)
        id=f"{disc_date.strftime('%Y%m%d')}_{member_id}_{trade.ticker}"
           f"_{filing.doc_id}_{row:03d}",
        memberId=member_id,
        memberName=member_name,
        party=party,
        chamber=Chamber.HOUSE,
        state=filing.state_dst[:2],
        ticker=trade.ticker,
        companyName=trade.asset,
        transactionType=_TX_TYPES.get(trade.action, TransactionType.PURCHASE),
        transactionDate=tx_date,
        disclosureDate=disc_date,
        amountRangeLow=trade.amount_low,
        amountRangeHigh=trade.amount_high,
        daysToDisclose=max(0, (disc_date - tx_date).days),
    )


def fetch_latest_sync(year: Optional[int] = None,
                      max_filings: int = 40) -> List[CongressTrade]:
    """Trades from the freshest e-filed PTRs (blocking; wrapped async below)."""
    year = year or datetime.utcnow().year
    filings = [f for f in house_ptr.fetch_index(year) if f.is_efiled]
    try:
        member_index = legislators.load_member_index()
    except Exception as e:
        member_index = {}
        logger.warning("legislators dataset unavailable; party will be UNKNOWN",
                       error=str(e))
    trades: List[CongressTrade] = []
    parsed = failed = 0
    for filing in filings[-max_filings:]:
        try:
            rows = house_ptr.parse_ptr(house_ptr.fetch_ptr_text(filing.doc_id, year))
            parsed += 1
        except Exception as e:
            failed += 1
            logger.warning("House Clerk PTR fetch/parse failed",
                           doc_id=filing.doc_id, error=str(e))
            continue
        info = legislators.lookup(member_index, filing.state_dst, filing.last)
        for n, row in enumerate(rows):
            trade = to_congress_trade(filing, row, n, member_info=info)
            if trade:
                trades.append(trade)
    logger.info("House Clerk ingest", filings=parsed, failed=failed,
                trades=len(trades))
    return trades


class HouseClerkClient:
    """Async facade matching the FMP/Quiver client shape for the scheduler."""

    async def fetch_all_latest(self, limit: int = 200) -> List[CongressTrade]:
        trades = await asyncio.to_thread(fetch_latest_sync)
        return trades[-limit:]

    async def close(self) -> None:
        pass  # urllib per-request; nothing to close
