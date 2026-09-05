"""CUSIP -> ticker mapping for the 13F shadow signal.

13F information tables identify positions by CUSIP; the app trades tickers.
Strategy (reliability-first, no paid vendor):

  1. OpenFIGI mapping API (Bloomberg, free): POST /v3/mapping with
     idType=ID_CUSIP, batched. Works keyless at a low rate; an optional
     OPENFIGI_API_KEY env raises limits. Authoritative for listed US equities.
  2. Fallback: fuzzy issuer-name match against EDGAR's official
     company_tickers.json (free, primary source).
  3. Cache-forever: CUSIPs are stable identifiers, so every resolved mapping is
     persisted to a local JSON cache and never re-fetched.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Dict, List, Optional

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
USER_AGENT = "TradeStreak data research contact@tradestreak.net"
CACHE_PATH = os.environ.get("CUSIP_CACHE_PATH", "/tmp/tradestreak_cusip_cache.json")

_BATCH = 100          # OpenFIGI max jobs per request
_KEYLESS_PAUSE = 6.5  # seconds between keyless batches (rate ~10/min)


def _load_cache() -> Dict[str, Dict[str, str]]:
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Dict[str, str]]) -> None:
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _openfigi_batch(cusips: List[str]) -> tuple:
    """Resolve one batch via OpenFIGI.
    Returns ({cusip: {ticker, name}}, [erred_cusips_to_retry])."""
    jobs = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in cusips]
    req = urllib.request.Request(
        OPENFIGI_URL,
        data=json.dumps(jobs).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    api_key = os.environ.get("OPENFIGI_API_KEY", "")
    if api_key:
        req.add_header("X-OPENFIGI-APIKEY", api_key)
    with urllib.request.urlopen(req, timeout=30) as resp:
        results = json.load(resp)
    out: Dict[str, Dict[str, str]] = {}
    erred: List[str] = []
    for cusip, result in zip(cusips, results):
        rows = result.get("data") or []
        if rows:
            out[cusip] = {
                "ticker": rows[0].get("ticker", ""),
                "name": rows[0].get("name", ""),
            }
        elif result.get("error"):
            # per-job throttle/temporary error — retryable, NOT a real miss
            erred.append(cusip)
    return out, erred


_edgar_names: Optional[Dict[str, str]] = None  # normalized name -> ticker


def _normalize(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9 ]", " ", name.upper())
    for suffix in (" INC", " CORP", " CO", " PLC", " LTD", " LP", " SA", " NV",
                   " CLASS A", " CLASS B", " CLASS C", " NEW", " DEL"):
        name = name.replace(suffix, " ")
    return " ".join(name.split())


def _edgar_name_lookup(issuer: str) -> Optional[Dict[str, str]]:
    global _edgar_names
    if _edgar_names is None:
        req = urllib.request.Request(EDGAR_TICKERS_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.load(resp)
        _edgar_names = {}
        for row in raw.values():
            _edgar_names.setdefault(_normalize(row.get("title", "")), row.get("ticker", ""))
    ticker = _edgar_names.get(_normalize(issuer))
    return {"ticker": ticker, "name": issuer} if ticker else None


def map_cusips(cusips: List[str], issuers: Optional[Dict[str, str]] = None,
               pause: Optional[float] = None) -> Dict[str, Dict[str, str]]:
    """Resolve CUSIPs to {ticker, name}. `issuers` (cusip -> issuer name)
    enables the EDGAR fallback for anything OpenFIGI misses."""
    cache = _load_cache()
    resolved = {c: cache[c] for c in cusips if c in cache}
    missing = [c for c in cusips if c not in resolved]

    wait = pause if pause is not None else (
        0.3 if os.environ.get("OPENFIGI_API_KEY") else _KEYLESS_PAUSE)
    retryable: List[str] = []
    for i in range(0, len(missing), _BATCH):
        batch = missing[i:i + _BATCH]
        try:
            hits, erred = _openfigi_batch(batch)
            resolved.update(hits)
            retryable.extend(erred)
        except Exception:
            retryable.extend(batch)  # whole-request failure — retry below
        if i + _BATCH < len(missing):
            time.sleep(wait)

    if retryable:
        time.sleep(max(wait, 3.0))  # back off, then one retry pass
        try:
            hits, _ = _openfigi_batch(retryable)
            resolved.update(hits)
        except Exception:
            pass  # EDGAR name fallback still applies

    if issuers:
        for cusip in cusips:
            if cusip not in resolved and cusip in issuers:
                hit = _edgar_name_lookup(issuers[cusip])
                if hit:
                    resolved[cusip] = hit

    cache.update(resolved)
    _save_cache(cache)
    return resolved
