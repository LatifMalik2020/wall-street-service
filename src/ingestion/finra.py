"""Daily short-sale volume from FINRA Reg SHO files (Polygon migration).

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
