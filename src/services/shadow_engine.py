"""Shadow-portfolio engine — pure functions, no I/O.

Turns a filer's disclosed book into a mirrored paper portfolio and applies
quarterly filing diffs as rebalances. Storage/prices are injected by callers
(see SHADOW_PORTFOLIOS_DESIGN.md), which keeps every mechanic unit-testable —
the discipline the removed v1 features lacked.

Money is modeled in floats consistent with the existing paper engine; shadow
positions allow fractional shares (it's paper).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

TOP_N_POSITIONS = 20
MIN_WEIGHT = 0.005  # ignore sub-0.5% sliver weights


@dataclass
class TargetWeight:
    ticker: str
    weight: float                 # 0..1 share of the shadow allocation
    provenance: str = ""          # accession / disclosure id


@dataclass
class ShadowPosition:
    ticker: str
    shares: float
    avg_price: float


@dataclass
class ShadowTrade:
    ticker: str
    side: str                     # buy | sell
    shares: float
    price: float
    kind: str                     # init | opened | exited | increased | decreased
    provenance: str = ""


@dataclass
class ShadowPortfolio:
    allocated_cash: float                       # original virtual allocation
    cash: float                                 # uninvested remainder
    positions: List[ShadowPosition] = field(default_factory=list)
    applied_accession: str = ""

    def position(self, ticker: str) -> Optional[ShadowPosition]:
        return next((p for p in self.positions if p.ticker == ticker), None)

    def market_value(self, prices: Dict[str, float]) -> float:
        return self.cash + sum(
            p.shares * prices.get(p.ticker, p.avg_price) for p in self.positions
        )


def target_weights_from_holdings(holdings: List[dict],
                                 top_n: int = TOP_N_POSITIONS) -> List[TargetWeight]:
    """Filer holdings [{ticker, value_usd}] -> normalized top-N target weights.

    Rows without a ticker (unmapped CUSIPs, bonds) are excluded BEFORE
    normalization so the investable book always sums to ~1.0.
    """
    investable = [h for h in holdings if h.get("ticker")]
    investable.sort(key=lambda h: h.get("value_usd", 0), reverse=True)
    picked = investable[:top_n]
    total = sum(h.get("value_usd", 0) for h in picked)
    if total <= 0:
        return []
    out = []
    for h in picked:
        w = h["value_usd"] / total
        if w >= MIN_WEIGHT:
            out.append(TargetWeight(h["ticker"], w, h.get("provenance", "")))
    # renormalize after the sliver filter
    s = sum(t.weight for t in out)
    for t in out:
        t.weight = t.weight / s
    return out


def _trade_to_weight(portfolio: ShadowPortfolio, ticker: str, target_value: float,
                     price: float, kind: str, provenance: str,
                     trades: List[ShadowTrade]) -> None:
    """Buy/sell `ticker` so its market value ≈ target_value at `price`."""
    if price <= 0:
        return
    pos = portfolio.position(ticker)
    current_value = (pos.shares * price) if pos else 0.0
    delta_value = target_value - current_value

    if abs(delta_value) < 1.0:  # ignore <$1 rebalance dust
        return

    if delta_value > 0:
        spend = min(delta_value, portfolio.cash)
        if spend < 1.0:
            return
        shares = spend / price
        if pos:
            total_cost = pos.avg_price * pos.shares + spend
            pos.shares += shares
            pos.avg_price = total_cost / pos.shares
        else:
            portfolio.positions.append(ShadowPosition(ticker, shares, price))
        portfolio.cash -= spend
        trades.append(ShadowTrade(ticker, "buy", shares, price, kind, provenance))
    else:
        if not pos:
            return
        shares = min(pos.shares, -delta_value / price)
        pos.shares -= shares
        portfolio.cash += shares * price
        trades.append(ShadowTrade(ticker, "sell", shares, price, kind, provenance))
        if pos.shares * price < 1.0:      # fully (or effectively) exited
            portfolio.cash += pos.shares * price
            portfolio.positions.remove(pos)


def initialize_shadow(allocation: float, targets: List[TargetWeight],
                      prices: Dict[str, float],
                      accession: str) -> tuple:
    """Build a fresh shadow portfolio from target weights at current prices.
    Returns (portfolio, trades). Tickers with no price are skipped (their
    weight stays as cash — honest, visible, and self-correcting next filing)."""
    portfolio = ShadowPortfolio(allocated_cash=allocation, cash=allocation,
                                applied_accession=accession)
    trades: List[ShadowTrade] = []
    for t in targets:
        price = prices.get(t.ticker, 0)
        _trade_to_weight(portfolio, t.ticker, allocation * t.weight, price,
                         "init", t.provenance or accession, trades)
    return portfolio, trades


PTR_REFERENCE_BOOK = 1_000_000.0  # assumed member portfolio for scaling nudges
PTR_MAX_WEIGHT = 0.25             # single-ticker cap for congress shadows


def nudge_targets_from_ptr(targets: List[TargetWeight], ptr_trades: List[dict],
                           reference_book: float = PTR_REFERENCE_BOOK) -> List[TargetWeight]:
    """Congress mode: PTRs disclose trades (deltas + amount RANGES), never the
    full book, so a congress shadow follows trades as weight NUDGES:

      buy          -> weight += midpoint(range) / reference_book (capped)
      sell         -> exit the position (a full 'S' is a disclosed full sale)
      sell_partial -> weight -= midpoint(range) / reference_book (floored at 0)

    ptr_trades: [{ticker, action, amount_low, amount_high}]. Weights need not
    sum to 1 — the remainder stays as honest cash, same as 13F shadows.
    """
    weights = {t.ticker: t.weight for t in targets}
    provenance = {t.ticker: t.provenance for t in targets}
    for tr in ptr_trades:
        ticker = tr["ticker"]
        delta = ((tr["amount_low"] + tr["amount_high"]) / 2.0) / reference_book
        if tr["action"] == "buy":
            weights[ticker] = min(weights.get(ticker, 0.0) + delta, PTR_MAX_WEIGHT)
        elif tr["action"] == "sell":
            weights.pop(ticker, None)
        elif tr["action"] == "sell_partial":
            if ticker in weights:
                weights[ticker] = max(weights[ticker] - delta, 0.0)
                if weights[ticker] < MIN_WEIGHT:
                    weights.pop(ticker)
        provenance[ticker] = tr.get("provenance", provenance.get(ticker, ""))
    return [TargetWeight(tk, w, provenance.get(tk, ""))
            for tk, w in weights.items() if w >= MIN_WEIGHT]


def apply_filing(portfolio: ShadowPortfolio, new_targets: List[TargetWeight],
                 prices: Dict[str, float], accession: str) -> List[ShadowTrade]:
    """Rebalance an existing shadow to a new filing's target weights.

    Sells first (exits + reductions free the cash that buys then consume),
    mirroring how the filer's book actually shifted. Idempotent per accession.
    """
    if portfolio.applied_accession == accession:
        return []

    trades: List[ShadowTrade] = []
    total_value = portfolio.market_value(prices)
    target_by_ticker = {t.ticker: t for t in new_targets}

    # 1) exits and reductions
    for pos in list(portfolio.positions):
        price = prices.get(pos.ticker, 0)
        target = target_by_ticker.get(pos.ticker)
        if target is None:
            _trade_to_weight(portfolio, pos.ticker, 0, price,
                             "exited", accession, trades)
        else:
            target_value = total_value * target.weight
            if price > 0 and pos.shares * price > target_value:
                _trade_to_weight(portfolio, pos.ticker, target_value, price,
                                 "decreased", accession, trades)

    # 2) opens and increases
    for t in new_targets:
        price = prices.get(t.ticker, 0)
        pos = portfolio.position(t.ticker)
        target_value = total_value * t.weight
        current_value = (pos.shares * price) if pos and price > 0 else 0
        if current_value < target_value:
            kind = "increased" if pos else "opened"
            _trade_to_weight(portfolio, t.ticker, target_value, price,
                             kind, accession, trades)

    portfolio.applied_accession = accession
    return trades
