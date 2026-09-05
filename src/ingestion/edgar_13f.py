"""SEC EDGAR 13F ingester — the shadow-portfolio data source.

Primary-source design (DATA_RELIABILITY_PLAN.md): institutional holdings come
straight from the SEC — free, authoritative, no vendor, no API key. Quarterly
13F-HR filings (due <=45 days after quarter end) give each tracked investor's
full US-equity book; the quarter-over-quarter DIFF is the shadow signal
("Buffett opened X, added to Y, trimmed Z, exited W").

EDGAR etiquette: descriptive User-Agent required; stay well under 10 req/s.

Flow per investor (by CIK):
  1. https://data.sec.gov/submissions/CIK{cik10}.json  -> filing index
  2. pick the latest N 13F-HR accessions
  3. accession dir index.json -> locate the information-table XML
  4. parse infoTable entries -> aggregated holdings {issuer, cusip, value, shares}
  5. diff two quarters -> opened / exited / increased / decreased
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional

USER_AGENT = "TradeStreak data research contact@tradestreak.net"
_BASE_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
_BASE_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}"

# A few well-known filers for the shadow roster (CIKs are public identifiers).
KNOWN_FILERS = {
    "berkshire": "1067983",     # Berkshire Hathaway (Buffett)
    "scion": "1649339",         # Scion Asset Management (Burry)
    "pershing-square": "1336528",
    "appaloosa": "1656456",
    "bridgewater": "1350694",
}


@dataclass
class Holding:
    issuer: str
    cusip: str
    value_usd: float
    shares: float


@dataclass
class HoldingChange:
    kind: str          # opened | exited | increased | decreased
    issuer: str
    cusip: str
    shares_before: float
    shares_after: float
    value_after_usd: float

    @property
    def pct_change(self) -> Optional[float]:
        if self.shares_before <= 0:
            return None
        return (self.shares_after - self.shares_before) / self.shares_before * 100


def _get(url: str, retries: int = 2) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception:
            if attempt == retries:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("unreachable")


def latest_13f_accessions(cik: str, count: int = 2) -> List[Dict[str, str]]:
    """Return the latest `count` 13F-HR filings as {accession, filingDate}."""
    cik10 = cik.zfill(10)
    data = json.loads(_get(_BASE_SUBMISSIONS.format(cik10=cik10)))
    recent = data.get("filings", {}).get("recent", {})
    out: List[Dict[str, str]] = []
    for form, date, acc in zip(recent.get("form", []),
                               recent.get("filingDate", []),
                               recent.get("accessionNumber", [])):
        if form == "13F-HR":  # originals only; amendments handled later
            out.append({"accession": acc, "filingDate": date})
            if len(out) >= count:
                break
    return out


def _find_info_table_url(cik: str, accession: str) -> str:
    """Locate the information-table XML inside an accession directory."""
    acc_nodash = accession.replace("-", "")
    index_url = _BASE_ARCHIVES.format(cik=int(cik), acc_nodash=acc_nodash) + "/index.json"
    listing = json.loads(_get(index_url))
    files = [f.get("name", "") for f in listing.get("directory", {}).get("item", [])]
    # The info table is an XML that is not the primary_doc; prefer names that
    # mention "infotable"/"information", else any non-primary .xml.
    candidates = [f for f in files if f.lower().endswith(".xml")]
    preferred = [f for f in candidates if re.search(r"info", f, re.I)]
    pick = (preferred or [f for f in candidates if "primary_doc" not in f.lower()] or candidates)
    if not pick:
        raise RuntimeError(f"no XML found in accession {accession}")
    return _BASE_ARCHIVES.format(cik=int(cik), acc_nodash=acc_nodash) + "/" + pick[0]


def parse_info_table(xml_bytes: bytes) -> List[Holding]:
    """Parse a 13F information table into aggregated holdings (by CUSIP).

    Handles the namespaced schema; sums duplicate CUSIP rows (managers often
    split a position across discretion buckets). Skips put/call rows so the
    shadow signal reflects share ownership, not options overlays.
    """
    root = ET.fromstring(xml_bytes)

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    agg: Dict[str, Holding] = {}
    for node in root.iter():
        if local(node.tag) != "infotable":
            continue
        issuer = cusip = put_call = ""
        value = shares = 0.0
        for child in node.iter():
            t = local(child.tag)
            text = (child.text or "").strip()
            if t == "nameofissuer":
                issuer = text
            elif t == "cusip":
                cusip = text
            elif t == "value":
                value = float(text or 0)
            elif t == "sshprnamt":
                shares = float(text or 0)
            elif t == "putcall":
                put_call = text
        if not cusip or put_call:
            continue
        if cusip in agg:
            prev = agg[cusip]
            agg[cusip] = Holding(prev.issuer, cusip, prev.value_usd + value, prev.shares + shares)
        else:
            agg[cusip] = Holding(issuer, cusip, value, shares)
    return list(agg.values())


def diff_holdings(previous: List[Holding], current: List[Holding],
                  min_value_usd: float = 1_000_000) -> List[HoldingChange]:
    """Quarter-over-quarter changes — the shadow signal. Small positions
    (< min_value_usd in the current quarter, or at exit time the prior value)
    are dropped to keep the feed meaningful."""
    prev = {h.cusip: h for h in previous}
    curr = {h.cusip: h for h in current}
    changes: List[HoldingChange] = []

    for cusip, h in curr.items():
        before = prev.get(cusip)
        if before is None:
            if h.value_usd >= min_value_usd:
                changes.append(HoldingChange("opened", h.issuer, cusip, 0, h.shares, h.value_usd))
        elif h.shares > before.shares:
            if h.value_usd >= min_value_usd:
                changes.append(HoldingChange("increased", h.issuer, cusip,
                                             before.shares, h.shares, h.value_usd))
        elif h.shares < before.shares:
            changes.append(HoldingChange("decreased", h.issuer, cusip,
                                         before.shares, h.shares, h.value_usd))

    for cusip, before in prev.items():
        if cusip not in curr and before.value_usd >= min_value_usd:
            changes.append(HoldingChange("exited", before.issuer, cusip,
                                         before.shares, 0, 0))

    changes.sort(key=lambda c: c.value_after_usd, reverse=True)
    return changes


def fetch_quarter_holdings(cik: str, accession: str) -> List[Holding]:
    url = _find_info_table_url(cik, accession)
    time.sleep(0.2)  # EDGAR politeness
    return parse_info_table(_get(url))


def shadow_signal(cik: str) -> Dict[str, object]:
    """End-to-end: latest two 13Fs -> holdings diff for one investor."""
    filings = latest_13f_accessions(cik, count=2)
    if len(filings) < 2:
        raise RuntimeError("need two 13F filings to diff")
    current = fetch_quarter_holdings(cik, filings[0]["accession"])
    time.sleep(0.3)
    previous = fetch_quarter_holdings(cik, filings[1]["accession"])
    return {
        "asOfFiling": filings[0]["filingDate"],
        "previousFiling": filings[1]["filingDate"],
        "positions": len(current),
        "changes": diff_holdings(previous, current),
    }
