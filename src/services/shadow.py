"""Shadow-portfolio service — roster, follow, lazy rebalance-on-read.

Semantics in SHADOW_PORTFOLIOS_DESIGN.md. All portfolio math lives in
shadow_engine (pure, tested); this layer is persistence + orchestration.
`repo` and `price_lookup` are injectable for offline tests.
"""

from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from src.services import shadow_engine
from src.services.shadow_engine import ShadowPortfolio, ShadowPosition, TargetWeight

STALE_DAYS = 135  # 45-day 13F deadline x 3 -> likely deregistered

FILER_NAMES = {
    1067983: "Berkshire Hathaway (Warren Buffett)",
    1649339: "Scion Asset Management (Michael Burry)",
    1336528: "Pershing Square (Bill Ackman)",
    1656456: "Appaloosa (David Tepper)",
    1350694: "Bridgewater Associates (Ray Dalio)",
}


def _portfolio_to_dict(p: ShadowPortfolio, cik: int) -> Dict:
    return {
        "cik": cik,
        "allocatedCash": p.allocated_cash,
        "cash": p.cash,
        "positions": [{"ticker": x.ticker, "shares": x.shares,
                       "avgPrice": x.avg_price} for x in p.positions],
        "appliedAccession": p.applied_accession,
    }


def _portfolio_from_dict(d: Dict) -> ShadowPortfolio:
    return ShadowPortfolio(
        allocated_cash=d["allocatedCash"], cash=d["cash"],
        positions=[ShadowPosition(x["ticker"], x["shares"], x["avgPrice"])
                   for x in d.get("positions", [])],
        applied_accession=d.get("appliedAccession", ""),
    )


def _targets_from_rows(rows: List[Dict]) -> List[TargetWeight]:
    return [TargetWeight(r["ticker"], r["weight"], r.get("provenance", ""))
            for r in rows]


def _trade_to_dict(t) -> Dict:
    return {"ticker": t.ticker, "side": t.side, "shares": t.shares,
            "price": t.price, "kind": t.kind, "provenance": t.provenance}


class ShadowService:
    def __init__(self, repo=None,
                 price_lookup: Optional[Callable[[List[str]], Dict[str, float]]] = None):
        if repo is None:
            from src.repositories.shadow import ShadowRepository
            repo = ShadowRepository()
        self._repo = repo
        self._prices = price_lookup or (lambda tickers: {})

    # -- roster --

    def get_roster(self) -> List[Dict]:
        out = []
        for slug, cik in sorted(shadow_engine_filers().items()):
            profile = self._repo.get_filer_profile(cik) or {}
            filed = profile.get("latestFilingDate", "")
            out.append({
                "slug": slug, "cik": cik,
                "name": FILER_NAMES.get(int(cik), slug.title()),
                "latestFilingDate": filed,
                "stale": _is_stale(filed),
            })
        return out

    # -- ingest (EventBridge job; network via edgar/cusip modules) --

    def refresh_filer(self, cik: str) -> Dict:
        """Check EDGAR for a new 13F; persist a target-weight snapshot if so."""
        from src.ingestion import cusip_map, edgar_13f
        filings = edgar_13f.latest_13f_accessions(cik, count=1)
        if not filings:
            return {"cik": cik, "status": "no_filings"}
        accession, filed = filings[0]["accession"], filings[0]["filingDate"]
        profile = self._repo.get_filer_profile(cik)
        if profile and profile.get("latestAccession") == accession:
            return {"cik": cik, "status": "unchanged", "accession": accession}

        holdings = edgar_13f.fetch_quarter_holdings(cik, accession)
        holdings.sort(key=lambda h: h.value_usd, reverse=True)
        candidates = holdings[:shadow_engine.TOP_N_POSITIONS * 2]
        mapping = cusip_map.map_cusips(
            [h.cusip for h in candidates],
            issuers={h.cusip: h.issuer for h in candidates})
        rows = [{"ticker": mapping.get(h.cusip, {}).get("ticker", ""),
                 "value_usd": h.value_usd, "provenance": accession}
                for h in candidates]
        targets = shadow_engine.target_weights_from_holdings(rows)
        name = FILER_NAMES.get(int(cik), str(cik))
        self._repo.put_filer_snapshot(
            cik, name, accession, filed,
            [{"ticker": t.ticker, "weight": t.weight, "provenance": t.provenance}
             for t in targets])
        return {"cik": cik, "status": "updated", "accession": accession,
                "targets": len(targets)}

    # -- user flows --

    def follow(self, user_id: str, cik: int, allocation: float) -> Dict:
        profile = self._repo.get_filer_profile(cik)
        if not profile:
            raise ValueError(f"filer {cik} not ingested")
        accession = profile["latestAccession"]
        snapshot = self._repo.get_filer_holdings(cik, accession) or {}
        targets = _targets_from_rows(snapshot.get("targets", []))
        prices = self._prices([t.ticker for t in targets])
        portfolio, trades = shadow_engine.initialize_shadow(
            allocation, targets, prices, accession)
        self._repo.put_user_shadow(user_id, cik, _portfolio_to_dict(portfolio, cik))
        self._repo.append_shadow_trades(
            user_id, cik, [_trade_to_dict(t) for t in trades])
        return self._view(portfolio, cik, profile, prices)

    def get_shadow(self, user_id: str, cik: int) -> Optional[Dict]:
        """Read a shadow, lazily applying any newer filing first."""
        stored = self._repo.get_user_shadow(user_id, cik)
        if not stored:
            return None
        portfolio = _portfolio_from_dict(stored)
        profile = self._repo.get_filer_profile(cik) or {}
        latest = profile.get("latestAccession", "")

        tickers = [p.ticker for p in portfolio.positions]
        if latest and latest != portfolio.applied_accession:
            snapshot = self._repo.get_filer_holdings(cik, latest) or {}
            targets = _targets_from_rows(snapshot.get("targets", []))
            tickers = sorted({*tickers, *(t.ticker for t in targets)})
            prices = self._prices(tickers)
            trades = shadow_engine.apply_filing(portfolio, targets, prices, latest)
            if trades:
                self._repo.put_user_shadow(
                    user_id, cik, _portfolio_to_dict(portfolio, cik))
                self._repo.append_shadow_trades(
                    user_id, cik, [_trade_to_dict(t) for t in trades])
        else:
            prices = self._prices(tickers)
        return self._view(portfolio, cik, profile, prices)

    def _view(self, portfolio: ShadowPortfolio, cik: int, profile: Dict,
              prices: Dict[str, float]) -> Dict:
        filed = profile.get("latestFilingDate", "")
        positions = []
        for p in sorted(portfolio.positions,
                        key=lambda x: -x.shares * prices.get(x.ticker, x.avg_price)):
            price = prices.get(p.ticker, p.avg_price)
            positions.append({
                "ticker": p.ticker, "shares": round(p.shares, 4),
                "avgPrice": round(p.avg_price, 2), "price": round(price, 2),
                "value": round(p.shares * price, 2),
                "gainLossPercent": round((price / p.avg_price - 1) * 100, 2)
                if p.avg_price else 0.0,
            })
        return {
            "cik": cik,
            "filerName": FILER_NAMES.get(int(cik), str(cik)),
            "allocatedCash": round(portfolio.allocated_cash, 2),
            "cash": round(portfolio.cash, 2),
            "marketValue": round(portfolio.market_value(prices), 2),
            "positions": positions,
            "appliedAccession": portfolio.applied_accession,
            "asOfLabel": f"Based on filings as of {filed} — positions may have "
                         f"changed since." if filed else "",
            "stale": _is_stale(filed),
        }


def shadow_engine_filers() -> Dict[str, str]:
    from src.ingestion.edgar_13f import KNOWN_FILERS
    return KNOWN_FILERS


def _is_stale(filing_date: str) -> bool:
    if not filing_date:
        return True
    try:
        filed = datetime.strptime(filing_date, "%Y-%m-%d").date()
    except ValueError:
        return True
    return (date.today() - filed).days > STALE_DAYS
