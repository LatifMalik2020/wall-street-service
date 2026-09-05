"""House PTR (periodic transaction report) ingestion — primary source.

Replaces the dead Quiver feed with the Clerk of the House's official
disclosure index (free, updated daily):

  index:  https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip
          -> {year}FD.xml listing every filing (FilingType 'P' = PTR)
  filing: https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{docid}.pdf

E-filed PTRs (8-digit DocIDs starting with '2') are RC4-encrypted text PDFs —
pypdf decrypts with the empty password and extracts cleanly. Paper filings
(7-digit DocIDs) are scans; we index them but mark them unparseable rather
than pretend coverage we don't have.

Senate eFD is session-gated and phase 2. Requires pypdf (only non-stdlib dep).
"""

from __future__ import annotations

import io
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import List, Optional

INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
USER_AGENT = "Mozilla/5.0 (TradeStreak data research contact@tradestreak.net)"


@dataclass
class PTRFiling:
    doc_id: str
    last: str
    first: str
    state_dst: str
    filing_date: str          # MM/DD/YYYY as published
    year: int

    @property
    def is_efiled(self) -> bool:
        # e-filed docs get 8-digit IDs starting with '2'; shorter IDs are
        # scanned paper filings whose PDFs are images (no text layer).
        return len(self.doc_id) == 8 and self.doc_id.startswith("2")

    @property
    def member(self) -> str:
        return f"{self.first} {self.last}".strip()


@dataclass
class PTRTrade:
    owner: str                # SP / DC / JT / '' (self)
    asset: str
    ticker: str
    action: str               # buy | sell | sell_partial | exchange
    transaction_date: str
    notification_date: str
    amount_low: int
    amount_high: int


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_index(year: int) -> List[PTRFiling]:
    """All PTR filings in the Clerk's yearly index (newest DocIDs last)."""
    blob = _get(INDEX_URL.format(year=year))
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
        root = ET.fromstring(zf.read(xml_name))
    out = []
    for m in root.findall("Member"):
        if m.findtext("FilingType") != "P":
            continue
        out.append(PTRFiling(
            doc_id=(m.findtext("DocID") or "").strip(),
            last=(m.findtext("Last") or "").strip(),
            first=(m.findtext("First") or "").strip(),
            state_dst=(m.findtext("StateDst") or "").strip(),
            filing_date=(m.findtext("FilingDate") or "").strip(),
            year=year,
        ))
    out.sort(key=lambda f: f.doc_id)
    return out


def fetch_ptr_text(doc_id: str, year: int) -> str:
    """Extracted text of an e-filed PTR PDF (decrypted with empty password)."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(_get(PTR_PDF_URL.format(year=year, doc_id=doc_id))))
    if reader.is_encrypted:
        reader.decrypt("")
    return "\n".join(page.extract_text() or "" for page in reader.pages)


_ACTIONS = {"P": "buy", "S": "sell", "S (partial)": "sell_partial", "E": "exchange"}

# One transaction row in the extracted text (whitespace-normalized):
#   [owner] <asset name> (TICKER) [type] P|S|E [(partial)] MM/DD/YYYY MM/DD/YYYY $low - $high
_ROW = re.compile(
    r"(?:^|\s)(SP|DC|JT)?\s*"
    # '$' and '?' excluded so the match can't reach back into the previous
    # row's amount column ('$200? JT ViaSat...' must anchor owner=JT)
    r"(?P<asset>[^()\[\]$?]{3,120}?)\s*"
    r"\((?P<ticker>[A-Z][A-Z0-9.\-]{0,9})\)\s*"
    r"(?:\[[A-Z]{2}\]\s*)?"
    r"(?P<action>P|S \(partial\)|S|E)\s+"
    r"(?P<tx>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<notif>\d{2}/\d{2}/\d{4})\s+"
    r"\$(?P<low>[\d,]+)\s*-\s*\$(?P<high>[\d,]+)"
)


def parse_ptr(text: str) -> List[PTRTrade]:
    """Transaction rows from an e-filed PTR's extracted text.

    Only rows with an exchange ticker in parentheses are returned — un-tickered
    assets (funds, bonds, crypto descriptions) can't drive equity shadows.
    """
    flat = " ".join(text.split())
    trades = []
    for m in _ROW.finditer(flat):
        owner = m.group(1) or ""
        asset = m.group("asset").strip(" -•")
        # the owner code can be glued to the asset when the regex ate no owner
        for code in ("SP", "DC", "JT"):
            if asset.startswith(code + " "):
                owner, asset = code, asset[len(code) + 1:]
        trades.append(PTRTrade(
            owner=owner,
            asset=asset,
            ticker=m.group("ticker"),
            action=_ACTIONS[m.group("action")],
            transaction_date=m.group("tx"),
            notification_date=m.group("notif"),
            amount_low=int(m.group("low").replace(",", "")),
            amount_high=int(m.group("high").replace(",", "")),
        ))
    return trades


def latest_trades(year: int, max_filings: int = 10) -> List[dict]:
    """Freshest e-filed PTR trades: [{member, state, filed, trade}, ...]."""
    filings = [f for f in fetch_index(year) if f.is_efiled]
    out = []
    for filing in filings[-max_filings:]:
        try:
            trades = parse_ptr(fetch_ptr_text(filing.doc_id, year))
        except Exception:
            continue  # single bad PDF must not kill the batch
        for t in trades:
            out.append({"member": filing.member, "state": filing.state_dst,
                        "filed": filing.filing_date, "doc_id": filing.doc_id,
                        "trade": t})
    return out
