"""Alpaca market-data client for wall-street-service (Polygon migration).

Subclasses PolygonMarketClient and overrides every PRICE method with Alpaca
equivalents that emit Polygon-shaped payloads, so all existing handlers keep
working unchanged. Fundamentals (ratios/financials/short data/filings/IPOs)
remain inherited from Polygon until the SEC/FINRA slice replaces them.

Indicators (SMA/EMA/MACD/RSI) are computed locally from Alpaca daily bars —
Polygon's indicator endpoints were just math over aggregates anyway.

Auth: APCA_API_KEY_ID/APCA_API_SECRET_KEY (paper/live keys) or the Broker
authx client credentials (ALPACA_AUTHX_CLIENT_ID/SECRET) for sandbox testing.
`market_data_client()` is the factory the handlers use: Alpaca when
credentials exist, plain Polygon otherwise.
"""

from __future__ import annotations

import os
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.ingestion.polygon_client import PolygonMarketClient
from src.utils.logging import logger

ALPACA_DATA_URL = os.environ.get("ALPACA_DATA_URL", "https://data.alpaca.markets")
ALPACA_AUTHX_URL = os.environ.get(
    "ALPACA_AUTHX_URL", "https://authx.sandbox.alpaca.markets/v1/oauth2/token")
_FEED = os.environ.get("ALPACA_DATA_FEED", "iex")

_BAR_TIMESPANS = {"minute": "1Min", "hour": "1Hour", "day": "1Day", "week": "1Week"}


def _ms(iso: str) -> int:
    """Alpaca RFC3339 timestamp -> epoch milliseconds (Polygon's `t`)."""
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


class AlpacaMarketClient(PolygonMarketClient):
    """Polygon-compatible facade over Alpaca Market Data."""

    def __init__(self):
        super().__init__()
        self._apca_key = os.environ.get("APCA_API_KEY_ID", "")
        self._apca_secret = os.environ.get("APCA_API_SECRET_KEY", "")
        self._authx_id = os.environ.get("ALPACA_AUTHX_CLIENT_ID", "")
        self._authx_secret = os.environ.get("ALPACA_AUTHX_CLIENT_SECRET", "")
        self._authx_token: Optional[str] = None
        self._authx_expiry = 0.0
        self._alpaca_http: Optional[httpx.AsyncClient] = None

    # -- plumbing --

    @property
    def alpaca_enabled(self) -> bool:
        return bool(self._apca_key and self._apca_secret) or bool(
            self._authx_id and self._authx_secret)

    async def _alpaca_headers(self) -> Dict[str, str]:
        if self._apca_key and self._apca_secret:
            return {"APCA-API-KEY-ID": self._apca_key,
                    "APCA-API-SECRET-KEY": self._apca_secret}
        if self._authx_token and _time.time() < self._authx_expiry - 60:
            return {"Authorization": f"Bearer {self._authx_token}"}
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(ALPACA_AUTHX_URL, data={
                "grant_type": "client_credentials",
                "client_id": self._authx_id,
                "client_secret": self._authx_secret,
            })
            resp.raise_for_status()
            tok = resp.json()
        self._authx_token = tok["access_token"]
        self._authx_expiry = _time.time() + int(tok.get("expires_in", 900))
        return {"Authorization": f"Bearer {self._authx_token}"}

    async def _alpaca_get(self, path: str, params: Dict[str, Any]) -> Dict:
        if self._alpaca_http is None:
            self._alpaca_http = httpx.AsyncClient(base_url=ALPACA_DATA_URL, timeout=20)
        resp = await self._alpaca_http.get(
            path, params=params, headers=await self._alpaca_headers())
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._alpaca_http is not None:
            await self._alpaca_http.aclose()
        await super().close()

    # -- snapshots --

    async def _snapshots(self, symbols: List[str]) -> Dict[str, Dict]:
        if not symbols:
            return {}
        data = await self._alpaca_get("/v2/stocks/snapshots", {
            "symbols": ",".join(s.upper() for s in symbols), "feed": _FEED})
        return data.get("snapshots", data) or {}

    @staticmethod
    def _to_polygon_snapshot(symbol: str, snap: Dict) -> Dict:
        """Alpaca snapshot -> the Polygon ticker-snapshot dict handlers parse."""
        trade = snap.get("latestTrade") or {}
        day = snap.get("dailyBar") or {}
        prev = snap.get("prevDailyBar") or {}
        price = trade.get("p") or day.get("c") or prev.get("c") or 0
        prev_close = prev.get("c") or 0
        change = (price - prev_close) if price and prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        return {
            "ticker": symbol.upper(),
            "day": {k: day.get(a) for k, a in
                    (("c", "c"), ("o", "o"), ("h", "h"), ("l", "l"), ("v", "v"))},
            "prevDay": {"c": prev.get("c"), "o": prev.get("o"), "h": prev.get("h"),
                        "l": prev.get("l"), "v": prev.get("v")},
            "lastTrade": {"p": trade.get("p")},
            "todaysChange": round(change, 4),
            "todaysChangePerc": round(change_pct, 4),
        }

    async def get_quote(self, symbol: str) -> Optional[Dict]:
        if not self.alpaca_enabled:
            return await super().get_quote(symbol)
        try:
            snaps = await self._snapshots([symbol])
            snap = snaps.get(symbol.upper())
            if not snap:
                return None
            poly = self._to_polygon_snapshot(symbol, snap)
            price = poly["day"]["c"] or poly["lastTrade"]["p"] or poly["prevDay"]["c"] or 0
            return {
                "symbol": symbol.upper(),
                "price": float(price),
                "change": float(poly["todaysChange"]),
                "changePercent": round(float(poly["todaysChangePerc"]), 2),
                "volume": int(poly["day"]["v"] or 0),
                "latestTradingDay": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
        except httpx.HTTPError as e:
            logger.warning("Alpaca quote failed; falling back to Polygon",
                           symbol=symbol, error=str(e))
            return await super().get_quote(symbol)

    async def batch_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        if not self.alpaca_enabled:
            return await super().batch_quotes(symbols)
        try:
            snaps = await self._snapshots(symbols)
        except httpx.HTTPError as e:
            logger.warning("Alpaca batch quotes failed; falling back", error=str(e))
            return await super().batch_quotes(symbols)
        out: Dict[str, Dict] = {}
        for sym in symbols:
            snap = snaps.get(sym.upper())
            if not snap:
                continue
            poly = self._to_polygon_snapshot(sym, snap)
            price = poly["day"]["c"] or poly["lastTrade"]["p"] or poly["prevDay"]["c"]
            if not price:
                continue
            out[sym.upper()] = {
                "symbol": sym.upper(),
                "price": float(price),
                "change": float(poly["todaysChange"]),
                "changePercent": round(float(poly["todaysChangePerc"]), 2),
                "volume": int(poly["day"]["v"] or 0),
                "latestTradingDay": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
        return out

    async def get_bulk_snapshot(self, symbols: List[str]) -> List[Dict]:
        if not self.alpaca_enabled:
            return await super().get_bulk_snapshot(symbols)
        try:
            snaps = await self._snapshots(symbols)
        except httpx.HTTPError as e:
            logger.warning("Alpaca bulk snapshot failed; falling back", error=str(e))
            return await super().get_bulk_snapshot(symbols)
        return [self._to_polygon_snapshot(sym, snap)
                for sym, snap in snaps.items() if snap]

    # -- movers (screener) --

    async def get_market_movers(self, include_otc: bool = False) -> Tuple[List[Dict], List[Dict]]:
        if not self.alpaca_enabled:
            return await super().get_market_movers(include_otc)
        try:
            data = await self._alpaca_get("/v1beta1/screener/stocks/movers", {"top": 20})
        except httpx.HTTPError as e:
            logger.warning("Alpaca movers failed; falling back", error=str(e))
            return await super().get_market_movers(include_otc)

        def convert(row: Dict) -> Dict:
            price = row.get("price") or 0
            change = row.get("change") or 0
            return {
                "ticker": row.get("symbol", ""),
                "day": {},
                "prevDay": {"c": round(price - change, 4) if price else None},
                "lastTrade": {"p": price},
                "todaysChange": change,
                "todaysChangePerc": row.get("percent_change") or 0,
            }

        gainers = [convert(r) for r in data.get("gainers", [])]
        losers = [convert(r) for r in data.get("losers", [])]
        return gainers, losers

    # -- aggregates (equities/ETFs only — indices already use ETF proxies) --

    async def get_index_aggregates(self, ticker: str, multiplier: int, timespan: str,
                                   from_date: str, to_date: str, adjusted: bool = True,
                                   sort: str = "asc", limit: int = 5000) -> List[Dict]:
        if not self.alpaca_enabled:
            return await super().get_index_aggregates(
                ticker, multiplier, timespan, from_date, to_date, adjusted, sort, limit)
        unit = {"minute": "Min", "hour": "Hour", "day": "Day", "week": "Week"}.get(timespan)
        timeframe = f"{multiplier}{unit}" if unit else None
        if not timeframe:
            return await super().get_index_aggregates(
                ticker, multiplier, timespan, from_date, to_date, adjusted, sort, limit)
        try:
            bars: List[Dict] = []
            page = None
            for _ in range(5):
                params = {"timeframe": timeframe, "start": f"{from_date}T00:00:00Z",
                          "end": f"{to_date}T23:59:59Z", "limit": 10000,
                          "adjustment": "split" if adjusted else "raw",
                          "feed": _FEED, "sort": sort}
                if page:
                    params["page_token"] = page
                data = await self._alpaca_get(f"/v2/stocks/{ticker.upper()}/bars", params)
                bars.extend(data.get("bars") or [])
                page = data.get("next_page_token")
                if not page:
                    break
            return [{"t": _ms(b["t"]), "o": b["o"], "h": b["h"], "l": b["l"],
                     "c": b["c"], "v": b["v"]} for b in bars][:limit]
        except httpx.HTTPError as e:
            logger.warning("Alpaca aggregates failed; falling back",
                           ticker=ticker, error=str(e))
            return await super().get_index_aggregates(
                ticker, multiplier, timespan, from_date, to_date, adjusted, sort, limit)

    # -- market status (clock) --

    async def get_market_status(self) -> Optional[Dict]:
        # Trading-API clock needs trading keys; compute from the calendar-free
        # local rule the app already trusts elsewhere (ET regular session), and
        # fall back to Polygon only when Alpaca creds are absent entirely.
        if not self.alpaca_enabled:
            return await super().get_market_status()
        from zoneinfo import ZoneInfo
        et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
        minutes = et.hour * 60 + et.minute
        weekday = et.weekday() < 5
        if weekday and 9 * 60 + 30 <= minutes < 16 * 60:
            market = "open"
        elif weekday and (4 * 60 <= minutes < 9 * 60 + 30 or 16 * 60 <= minutes < 20 * 60):
            market = "extended-hours"
        else:
            market = "closed"
        return {
            "market": market,
            "earlyHours": market == "extended-hours" and minutes < 9 * 60 + 30,
            "afterHours": market == "extended-hours" and minutes >= 16 * 60,
            "serverTime": datetime.now(timezone.utc).isoformat(),
            "exchanges": {"nasdaq": market, "nyse": market, "otc": market},
        }

    # -- fundamentals from SEC company facts (primary source, free) --

    async def get_ratios(self, symbol: str) -> Optional[Dict]:
        from src.ingestion import sec_facts
        try:
            quote = await self.get_quote(symbol)
            price = quote.get("price") if quote else None
            ratios = await sec_facts.get_ratios(symbol, price)
            if ratios:
                return ratios
        except Exception as e:  # noqa: BLE001
            logger.warning("SEC ratios failed; falling back to Polygon",
                           symbol=symbol, error=str(e))
        return await super().get_ratios(symbol)

    # -- indicators, computed locally from daily bars --

    async def _daily_closes(self, symbol: str, days: int) -> List[Dict]:
        today = datetime.now(timezone.utc).date()
        return await self.get_index_aggregates(
            symbol, 1, "day", (today - timedelta(days=days)).isoformat(),
            today.isoformat())

    @staticmethod
    def _ema_series(values: List[float], window: int) -> List[float]:
        if len(values) < window:
            return []
        ema = sum(values[:window]) / window
        out = [ema]
        k = 2 / (window + 1)
        for v in values[window:]:
            ema += k * (v - ema)
            out.append(ema)
        return out

    async def get_sma(self, symbol: str, window: int = 50, timespan: str = "day",
                      limit: int = 100) -> List[Dict]:
        if not self.alpaca_enabled:
            return await super().get_sma(symbol, window, timespan, limit)
        bars = await self._daily_closes(symbol, days=window * 2 + limit + 40)
        if len(bars) < window:
            return []
        out = []
        running = sum(b["c"] for b in bars[:window])
        out.append({"timestamp": bars[window - 1]["t"], "value": running / window})
        for i in range(window, len(bars)):
            running += bars[i]["c"] - bars[i - window]["c"]
            out.append({"timestamp": bars[i]["t"], "value": running / window})
        return out[-limit:]

    async def get_ema(self, symbol: str, window: int = 50, timespan: str = "day",
                      limit: int = 100) -> List[Dict]:
        if not self.alpaca_enabled:
            return await super().get_ema(symbol, window, timespan, limit)
        bars = await self._daily_closes(symbol, days=window * 2 + limit + 40)
        series = self._ema_series([b["c"] for b in bars], window)
        stamped = [{"timestamp": bars[window - 1 + i]["t"], "value": v}
                   for i, v in enumerate(series)]
        return stamped[-limit:]

    async def get_macd(self, symbol: str, timespan: str = "day",
                       limit: int = 100) -> List[Dict]:
        if not self.alpaca_enabled:
            return await super().get_macd(symbol, timespan, limit)
        bars = await self._daily_closes(symbol, days=400)
        closes = [b["c"] for b in bars]
        fast, slow = self._ema_series(closes, 12), self._ema_series(closes, 26)
        if not slow:
            return []
        offset = len(fast) - len(slow)
        # macd_line[j] aligns with bars[25 + j] (slow EMA warm-up is 26 bars).
        macd_line = [fast[i + offset] - s for i, s in enumerate(slow)]
        signal = self._ema_series(macd_line, 9)
        sig_offset = len(macd_line) - len(signal)
        out = []
        for i, sig in enumerate(signal):
            j = sig_offset + i
            m = macd_line[j]
            out.append({"timestamp": bars[25 + j]["t"], "value": m,
                        "signal": sig, "histogram": m - sig})
        return out[-limit:]

    async def get_rsi(self, symbol: str, window: int = 14, timespan: str = "day",
                      limit: int = 100) -> List[Dict]:
        if not self.alpaca_enabled:
            return await super().get_rsi(symbol, window, timespan, limit)
        bars = await self._daily_closes(symbol, days=window * 3 + limit + 40)
        closes = [b["c"] for b in bars]
        if len(closes) <= window:
            return []
        gain = loss = 0.0
        for i in range(1, window + 1):
            d = closes[i] - closes[i - 1]
            gain += max(d, 0)
            loss += max(-d, 0)
        gain /= window
        loss /= window

        def rsi_val() -> float:
            if gain == 0 and loss == 0:
                return 50.0
            if loss == 0:
                return 100.0
            return 100 - 100 / (1 + gain / loss)

        out = [{"timestamp": bars[window]["t"], "value": rsi_val()}]
        for i in range(window + 1, len(closes)):
            d = closes[i] - closes[i - 1]
            gain = (gain * (window - 1) + max(d, 0)) / window
            loss = (loss * (window - 1) + max(-d, 0)) / window
            out.append({"timestamp": bars[i]["t"], "value": rsi_val()})
        return out[-limit:]


def market_data_client() -> PolygonMarketClient:
    """The provider seam: Alpaca-backed client when credentials exist,
    plain Polygon otherwise. Handlers construct through this instead of
    PolygonMarketClient() directly."""
    client = AlpacaMarketClient()
    return client if client.alpaca_enabled else PolygonMarketClient()
