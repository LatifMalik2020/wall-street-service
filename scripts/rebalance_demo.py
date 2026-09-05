#!/usr/bin/env python3
"""Rebalance-on-filing demo — the core shadow product moment on REAL data.

Initializes a shadow from a filer's PREVIOUS 13F, then applies the LATEST
filing at live prices, printing the provenance-stamped rebalance trades
("Buffett trimmed Kroger — your shadow sold N shares").

Usage: python3 scripts/rebalance_demo.py [filer] [allocation]
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
from alpaca import get_token  # noqa: E402

DATA_URL = "https://data.sandbox.alpaca.markets"


def live_prices(tickers):
    req = urllib.request.Request(
        f"{DATA_URL}/v2/stocks/trades/latest?symbols={','.join(sorted(set(tickers)))}",
        headers={"Authorization": "Bearer " + get_token()},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return {sym: t["p"] for sym, t in (data.get("trades") or {}).items() if t.get("p", 0) > 0}


def targets_for(cik, accession):
    holdings = edgar.fetch_quarter_holdings(cik, accession)
    holdings.sort(key=lambda h: h.value_usd, reverse=True)
    candidates = holdings[:engine.TOP_N_POSITIONS * 2]
    mapping = cmap.map_cusips([h.cusip for h in candidates],
                              issuers={h.cusip: h.issuer for h in candidates})
    rows = [{"ticker": mapping.get(h.cusip, {}).get("ticker", ""),
             "value_usd": h.value_usd, "provenance": accession} for h in candidates]
    return engine.target_weights_from_holdings(rows)


def main():
    filer = sys.argv[1] if len(sys.argv) > 1 else "berkshire"
    allocation = float(sys.argv[2]) if len(sys.argv) > 2 else 10_000.0
    cik = edgar.KNOWN_FILERS[filer]

    filings = edgar.latest_13f_accessions(cik, count=2)
    if len(filings) < 2:
        sys.exit(f"{filer}: fewer than 2 filings available")
    latest, prev = filings[0], filings[1]

    prev_targets = targets_for(cik, prev["accession"])
    new_targets = targets_for(cik, latest["accession"])
    prices = live_prices([t.ticker for t in prev_targets + new_targets])

    portfolio, init_trades = engine.initialize_shadow(
        allocation, prev_targets, prices, prev["accession"])
    print(f"1) Shadow initialized from {filer.upper()} 13F filed {prev['filingDate']}: "
          f"{len(portfolio.positions)} positions, ${allocation:,.0f}")

    trades = engine.apply_filing(portfolio, new_targets, prices, latest["accession"])
    print(f"2) New 13F filed {latest['filingDate']} detected -> lazy rebalance "
          f"produced {len(trades)} trades:\n")
    print(f"{'':2}{'TICKER':<7}{'ACTION':<11}{'SIDE':<5}{'SHARES':>9}{'PRICE':>9}{'VALUE':>10}")
    for t in sorted(trades, key=lambda x: -x.shares * x.price):
        print(f"  {t.ticker:<7}{t.kind:<11}{t.side:<5}{t.shares:>9.3f}{t.price:>9.2f}"
              f"{t.shares * t.price:>10.2f}")

    total = portfolio.market_value(prices)
    print(f"\n3) Post-rebalance: {len(portfolio.positions)} positions + "
          f"${portfolio.cash:,.2f} cash = ${total:,.2f} (value conserved: "
          f"{'YES' if abs(total - allocation) < 1 else 'NO — drift $%.2f' % (total - allocation)})")
    print(f"   appliedAccession: {portfolio.applied_accession}")

    # Idempotency proof on real data — a second application must be a no-op.
    again = engine.apply_filing(portfolio, new_targets, prices, latest["accession"])
    print(f"4) Re-applying same accession: {len(again)} trades (idempotent: "
          f"{'YES' if not again else 'NO'})")


if __name__ == "__main__":
    main()
