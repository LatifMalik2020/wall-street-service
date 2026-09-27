"""Short data from FINRA (Polygon migration): daily Reg SHO short volume
and bi-monthly consolidated short interest.

FINRA publishes consolidated short-volume files every trading day at
cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt — free, keyless,
pipe-delimited: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market.
This is the primary dataset Polygon's /stocks/v1/short-volume resells.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

import httpx

from src.utils.logging import logger

_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
_UA = {"User-Agent": "TradeStreak data research contact@tradestreak.net"}

# date-string -> {symbol: (short, total)}; a day's file never changes.
_day_cache: Dict[str, Optional[Dict[str, tuple]]] = {}


async def _day_volumes(client: httpx.AsyncClient, ymd: str) -> Optional[Dict[str, tuple]]:
    if ymd in _day_cache:
        return _day_cache[ymd]
    resp = await client.get(_URL.format(ymd=ymd))
    if resp.status_code != 200:
        _day_cache[ymd] = None
        return None
    table: Dict[str, tuple] = {}
    for line in resp.text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 5:
            continue
        try:
            table[parts[1]] = (float(parts[2]), float(parts[4]))
        except ValueError:
            continue
    _day_cache[ymd] = table
    return table


async def get_short_volume(symbol: str, limit: int = 5) -> List[Dict]:
    """Most recent `limit` trading days of short volume for a symbol, shaped
    like Polygon's short-volume rows (date desc)."""
    sym = symbol.upper()
    out: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=20, headers=_UA) as client:
            day = date.today()
            for _ in range(limit * 3 + 6):  # skip weekends/holidays
                if len(out) >= limit:
                    break
                ymd = day.strftime("%Y%m%d")
                day -= timedelta(days=1)
                table = await _day_volumes(client, ymd)
                if not table:
                    continue
                row = table.get(sym)
                if not row:
                    continue
                short, total = row
                out.append({
                    "ticker": sym,
                    "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                    "short_volume": short,
                    "total_volume": total,
                    "short_volume_ratio": round(short / total, 4) if total else None,
                })
    except httpx.HTTPError as e:
        logger.warning("FINRA short volume fetch failed", symbol=sym, error=str(e))
    return out


# -- consolidated (bi-monthly) short interest ---------------------------------
#
# FINRA's public Query API serves the consolidated equity short-interest
# dataset (all exchange-listed + OTC symbols, settlement dates mid/end month)
# keylessly: POST api.finra.org/data/group/otcMarket/name/consolidatedShortInterest.
# Same data as the cdn.finra.org/equity/otcmarket/biweekly/shrt{YYYYMMDD}.csv
# files, but filterable by symbol so we never download the 2 MB file.

_SI_URL = ("https://api.finra.org/data/group/otcMarket/name/"
           "consolidatedShortInterest")
_SI_LOOKBACK_DAYS = 200  # ~13 settlement dates; enough for limit<=10


def short_interest_rows_from_finra(symbol: str, records: List[Dict],
                                   limit: int) -> List[Dict]:
    """FINRA API records -> short-interest rows (settlement_date desc) in the
    shape the stocks handler builds ShortInterestData from."""
    sym = symbol.upper()
    by_date: Dict[str, Dict] = {}
    for r in records:
        if (r.get("symbolCode") or "").upper() != sym:
            continue
        settle = r.get("settlementDate")
        qty = r.get("currentShortPositionQuantity")
        if not settle or qty is None:
            continue
        by_date[settle] = r  # later records (revisions) win
    out: List[Dict] = []
    for settle in sorted(by_date, reverse=True)[:limit]:
        r = by_date[settle]
        adv = r.get("averageDailyVolumeQuantity")
        dtc = r.get("daysToCoverQuantity")
        if dtc is None and adv:
            dtc = round(float(r["currentShortPositionQuantity"]) / float(adv), 2)
        out.append({
            "ticker": sym,
            "short_interest": float(r["currentShortPositionQuantity"]),
            "avg_daily_volume": float(adv) if adv is not None else None,
            "days_to_cover": float(dtc) if dtc is not None else None,
            "settlement_date": settle,
        })
    return out


async def get_short_interest(symbol: str, limit: int = 5) -> List[Dict]:
    """Most recent `limit` FINRA short-interest settlements for a symbol.
    Returns [] on any failure (never invented data)."""
    sym = symbol.upper()
    today = date.today()
    body = {
        "limit": 100,
        "compareFilters": [
            {"compareType": "equal", "fieldName": "symbolCode", "fieldValue": sym},
        ],
        "dateRangeFilters": [{
            "fieldName": "settlementDate",
            "startDate": (today - timedelta(days=_SI_LOOKBACK_DAYS)).isoformat(),
            "endDate": today.isoformat(),
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers={
                **_UA, "Accept": "application/json"}) as client:
            resp = await client.post(_SI_URL, json=body)
            if resp.status_code == 204 or not resp.content:
                return []
            resp.raise_for_status()
            records = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("FINRA short interest fetch failed", symbol=sym, error=str(e))
        return []
    if not isinstance(records, list):
        return []
    return short_interest_rows_from_finra(sym, records, limit)
