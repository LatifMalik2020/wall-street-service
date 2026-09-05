#!/usr/bin/env python3
"""Congress shadow demo — House PTR trades -> weight nudges -> shadow engine.

Follows one member: starts a $10k all-cash shadow, applies their freshest
disclosed trades as range-midpoint weight nudges at live prices. Also prints
2026 parse-coverage honesty stats (e-filed vs paper scans).

Usage: python3 scripts/congress_demo.py [last-name] [allocation]
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


ptr = load("house_ptr", REPO / "src/ingestion/house_ptr.py")
engine = load("shadow_engine", REPO / "src/services/shadow_engine.py")
sys.path.insert(0, str(ALPACA_DIR))
from alpaca import get_token  # noqa: E402

DATA_URL = "https://data.sandbox.alpaca.markets"


def live_prices(tickers):
    if not tickers:
        return {}
    req = urllib.request.Request(
        f"{DATA_URL}/v2/stocks/trades/latest?symbols={','.join(sorted(set(tickers)))}",
        headers={"Authorization": "Bearer " + get_token()},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return {sym: t["p"] for sym, t in (data.get("trades") or {}).items() if t.get("p", 0) > 0}


def main():
    member_last = sys.argv[1] if len(sys.argv) > 1 else "Taylor"
    allocation = float(sys.argv[2]) if len(sys.argv) > 2 else 10_000.0
    year = 2026

    filings = ptr.fetch_index(year)
    efiled = [f for f in filings if f.is_efiled]
    print(f"2026 coverage: {len(filings)} PTR filings — {len(efiled)} e-filed "
          f"(parseable), {len(filings) - len(efiled)} paper scans "
          f"({len(efiled) / len(filings) * 100:.0f}% trade-level coverage)\n")

    mine = [f for f in efiled if f.last.lower() == member_last.lower()]
    if not mine:
        sys.exit(f"no e-filed 2026 PTRs for '{member_last}'")
    trades = []
    for f in mine[-3:]:  # up to 3 freshest filings
        for t in ptr.parse_ptr(ptr.fetch_ptr_text(f.doc_id, year)):
            trades.append({"ticker": t.ticker, "action": t.action,
                           "amount_low": t.amount_low, "amount_high": t.amount_high,
                           "provenance": f"ptr:{f.doc_id}"})
    member = mine[-1].member
    print(f"SHADOW: Rep. {member} ({mine[-1].state_dst}) · {len(trades)} disclosed "
          f"trades · ${allocation:,.0f} paper")

    targets = engine.nudge_targets_from_ptr([], trades)
    prices = live_prices([t.ticker for t in targets])
    portfolio, shadow_trades = engine.initialize_shadow(
        allocation, targets, prices, trades[-1]["provenance"] if trades else "none")

    print(f"-> {len(shadow_trades)} shadow trades:\n")
    print(f"{'TICKER':<7}{'SHARES':>9}{'PRICE':>9}{'VALUE':>10}{'WEIGHT':>8}  PROVENANCE")
    total = portfolio.market_value(prices)
    for p in sorted(portfolio.positions, key=lambda x: -x.shares * prices.get(x.ticker, 0)):
        value = p.shares * prices.get(p.ticker, p.avg_price)
        prov = next((t.provenance for t in targets if t.ticker == p.ticker), "")
        print(f"{p.ticker:<7}{p.shares:>9.3f}{prices.get(p.ticker, 0):>9.2f}"
              f"{value:>10.2f}{value / total * 100:>7.1f}%  {prov}")
    print(f"{'CASH':<7}{'':>9}{'':>9}{portfolio.cash:>10.2f}{portfolio.cash / total * 100:>7.1f}%")
    print(f"\ntotal ${total:,.2f} · amounts are DISCLOSED RANGES — weights use "
          f"range midpoints scaled to a ${engine.PTR_REFERENCE_BOOK:,.0f} reference book.")


if __name__ == "__main__":
    main()
