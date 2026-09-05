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

_BATCH_KEYED = 100    # OpenFIGI max jobs/request with an API key
_BATCH_KEYLESS = 10   # keyless hard limit — 11+ jobs returns HTTP 413
_KEYLESS_PAUSE = 6.5  # seconds between keyless batches (rate ~25/min)
_MAX_PASSES = 4       # retry throttled jobs until convergence (bounded)


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


_SUFFIX_TOKENS = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
                  "PLC", "LTD", "LIMITED", "LP", "SA", "NV", "NEW", "DEL",
                  "HOLDINGS", "HLDGS", "GROUP", "GRP", "CLASS", "CL", "A", "B", "C"}


def _normalize(name: str) -> str:
    """Uppercase, drop punctuation, then strip legal-suffix tokens from the END
    only (substring replace corrupted names: CORPORATION -> ' ORATION')."""
    tokens = re.sub(r"[^A-Za-z0-9 ]", " ", name.upper()).split()
    while len(tokens) > 1 and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens)


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

    keyed = bool(os.environ.get("OPENFIGI_API_KEY"))
    batch_size = _BATCH_KEYED if keyed else _BATCH_KEYLESS
    wait = pause if pause is not None else (0.3 if keyed else _KEYLESS_PAUSE)
    # Retry throttled jobs until convergence (bounded, growing backoff). A single
    # retry pass left $50B of Berkshire's book unmapped — throttle errors are
    # the norm keyless, not the exception.
    pending = missing
    for attempt in range(_MAX_PASSES):
        if not pending:
            break
        if attempt > 0:
            time.sleep(max(wait, 3.0) * attempt)
        still: List[str] = []
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i + batch_size]
            try:
                hits, erred = _openfigi_batch(batch)
                resolved.update(hits)
                still.extend(erred)
            except Exception:
                still.extend(batch)  # whole-request failure — retry next pass
            if i + batch_size < len(pending):
                time.sleep(wait)
        pending = still  # EDGAR name fallback still applies to leftovers

    if issuers:
        for cusip in cusips:
            if cusip not in resolved and cusip in issuers:
                hit = _edgar_name_lookup(issuers[cusip])
                if hit:
                    resolved[cusip] = hit

    cache.update(resolved)
    _save_cache(cache)
    return resolved
