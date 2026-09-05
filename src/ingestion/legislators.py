"""Member metadata from the unitedstates/congress-legislators dataset.

Public-domain, community-maintained, hosted on GitHub Pages — fills what the
House Clerk index lacks (party, canonical name). Matched by state+district+
last name, which is far more reliable than fuzzy full-name matching.

Cache-per-day: membership changes rarely; one fetch a day is plenty.
"""

import json
import os
import time
import urllib.request
from typing import Dict, Optional

LEGISLATORS_URL = ("https://unitedstates.github.io/congress-legislators/"
                   "legislators-current.json")
USER_AGENT = "TradeStreak data research contact@tradestreak.net"
CACHE_PATH = os.environ.get("LEGISLATORS_CACHE_PATH",
                            "/tmp/tradestreak_legislators.json")
CACHE_TTL_SECONDS = 24 * 3600

_PARTY_CODES = {"Democrat": "D", "Republican": "R", "Independent": "I"}


def _fetch_raw() -> list:
    req = urllib.request.Request(LEGISLATORS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def load_member_index(force: bool = False) -> Dict[str, dict]:
    """{'STATE:DD:lastname' and 'STATE:lastname' -> {party, fullName}}."""
    if not force:
        try:
            stat = os.stat(CACHE_PATH)
            if time.time() - stat.st_mtime < CACHE_TTL_SECONDS:
                with open(CACHE_PATH) as f:
                    return json.load(f)
        except OSError:
            pass

    index: Dict[str, dict] = {}
    for person in _fetch_raw():
        terms = person.get("terms") or []
        if not terms:
            continue
        term = terms[-1]  # current term
        name = person.get("name", {})
        last = (name.get("last") or "").lower()
        state = (term.get("state") or "").upper()
        party = _PARTY_CODES.get(term.get("party", ""), "U")
        info = {"party": party,
                "fullName": name.get("official_full")
                or f"{name.get('first', '')} {name.get('last', '')}".strip()}
        if term.get("type") == "rep" and term.get("district") is not None:
            index[f"{state}:{int(term['district']):02d}:{last}"] = info
        index.setdefault(f"{state}:{last}", info)

    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(index, f)
    except OSError:
        pass
    return index


def lookup(index: Dict[str, dict], state_dst: str, last: str) -> Optional[dict]:
    """Match a Clerk filing's StateDst (e.g. 'IL01') + last name."""
    state, district = state_dst[:2].upper(), state_dst[2:]
    last = last.lower()
    if district.isdigit():
        hit = index.get(f"{state}:{int(district):02d}:{last}")
        if hit:
            return hit
    return index.get(f"{state}:{last}")
