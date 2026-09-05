#!/usr/bin/env python3
"""End-to-end Shadow Portfolio demo — composes the whole stack:

  EDGAR 13F (primary source) -> CUSIP->ticker mapping -> target weights
    -> LIVE prices (Alpaca sandbox data REST) -> shadow_engine mirror

Usage: python3 scripts/shadow_demo.py [filer] [allocation]
       (filer from edgar_13f.KNOWN_FILERS, default berkshire; default $10,000)
"""

import importlib.util
import json
import pathlib
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
ALPACA_DIR = REPO.parent / "alpaca-broker"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


edgar = load("edgar_13f", REPO / "src/ingestion/edgar_13f.py")
cmap = load("cusip_map", REPO / "src/ingestion/cusip_map.py")
engine = load("shadow_engine", REPO / "src/services/shadow_engine.py")
sys.path.insert(0, str(ALPACA_DIR))
from alpaca import get_token  # noqa: E402  (authx harness; .env stays gitignored)

DATA_URL = "https://data.sandbox.alpaca.markets"


def live_prices(tickers):
    """Latest trade price per ticker from the Alpaca sandbox data REST."""
    req = urllib.request.Request(
        f"{DATA_URL}/v2/stocks/trades/latest?symbols={','.join(tickers)}",
        headers={"Authorization": "Bearer " + get_token()},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return {sym: t["p"] for sym, t in (data.get("trades") or {}).items() if t.get("p", 0) > 0}


def main():
    filer = sys.argv[1] if len(sys.argv) > 1 else "berkshire"
    allocation = float(sys.argv[2]) if len(sys.argv) > 2 else 10_000.0
    cik = edgar.KNOWN_FILERS[filer]

    filings = edgar.latest_13f_accessions(cik, count=1)
    accession, filed = filings[0]["accession"], filings[0]["filingDate"]
    holdings = edgar.fetch_quarter_holdings(cik, accession)

    # Only the top-N positions can enter the shadow, so only map CUSIPs that
    # could plausibly make the cut (2x buffer for unmappable rows). Keeps
    # keyless OpenFIGI runtime sane on huge books (Bridgewater files 100s).
    holdings.sort(key=lambda h: h.value_usd, reverse=True)
    candidates = holdings[:engine.TOP_N_POSITIONS * 2]
    mapping = cmap.map_cusips([h.cusip for h in candidates],
                              issuers={h.cusip: h.issuer for h in candidates})
    rows = [{"ticker": mapping.get(h.cusip, {}).get("ticker", ""),
             "value_usd": h.value_usd, "provenance": accession} for h in candidates]

    targets = engine.target_weights_from_holdings(rows)
    prices = live_prices([t.ticker for t in targets])
    portfolio, trades = engine.initialize_shadow(allocation, targets, prices, accession)

    print(f"SHADOW: {filer.upper()}  ·  based on 13F filed {filed}  ·  ${allocation:,.0f} paper")
    print(f"{len(holdings)} disclosed positions -> {len(targets)} mirrored -> {len(trades)} shadow trades\n")
    print(f"{'TICKER':<7}{'SHARES':>10}{'PRICE':>10}{'VALUE':>11}{'WEIGHT':>8}")
    total = portfolio.market_value(prices)
    for p in sorted(portfolio.positions, key=lambda x: -x.shares * prices.get(x.ticker, 0)):
        value = p.shares * prices.get(p.ticker, p.avg_price)
        print(f"{p.ticker:<7}{p.shares:>10.3f}{prices.get(p.ticker, 0):>10.2f}"
              f"{value:>11.2f}{value / total * 100:>7.1f}%")
    print(f"{'CASH':<7}{'':>10}{'':>10}{portfolio.cash:>11.2f}{portfolio.cash / total * 100:>7.1f}%")
    print(f"\ntotal ${total:,.2f} · as-of label: \"Based on filings as of {filed} — "
          f"positions may have changed since.\"")

    # Staleness guard: 13Fs are due 45 days after quarter end, so a healthy
    # filer never goes >135 days without a new one. Older = likely deregistered
    # (e.g. Scion, last filing 2025-11-03) — the shadow must say so loudly.
    import datetime
    age = (datetime.date.today() - datetime.date.fromisoformat(filed)).days
    if age > 135:
        print(f"⚠ STALE FILER: last 13F is {age} days old — fund may have "
              f"deregistered or stopped reporting. Do not offer for new follows.")


if __name__ == "__main__":
    main()
