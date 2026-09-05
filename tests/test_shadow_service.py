"""Offline tests for ShadowService (fake repo + fixed prices, no AWS/network)."""

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.services.shadow import ShadowService, _is_stale  # noqa: E402


class FakeRepo:
    def __init__(self):
        self.profiles, self.holdings, self.shadows, self.trades = {}, {}, {}, []

    def put_filer_snapshot(self, cik, name, accession, filing_date, targets):
        self.profiles[cik] = {"name": name, "latestAccession": accession,
                              "latestFilingDate": filing_date}
        self.holdings[(cik, accession)] = {"targets": targets}

    def get_filer_profile(self, cik):
        return self.profiles.get(cik)

    def get_filer_holdings(self, cik, accession):
        return self.holdings.get((cik, accession))

    def put_user_shadow(self, user_id, cik, portfolio):
        self.shadows[(user_id, cik)] = portfolio

    def get_user_shadow(self, user_id, cik):
        return self.shadows.get((user_id, cik))

    def append_shadow_trades(self, user_id, cik, trades):
        self.trades.extend(trades)

    def list_shadow_trades(self, user_id, limit=50):
        return self.trades[-limit:]


PRICES = {"AAPL": 100.0, "MSFT": 200.0, "NVDA": 50.0}


def make_service():
    repo = FakeRepo()
    repo.put_filer_snapshot(
        1067983, "Berkshire", "acc-1", "2026-08-14",
        [{"ticker": "AAPL", "weight": 0.6, "provenance": "acc-1"},
         {"ticker": "MSFT", "weight": 0.4, "provenance": "acc-1"}])
    return ShadowService(repo=repo, price_lookup=lambda tickers: PRICES), repo


class FollowTests(unittest.TestCase):
    def test_follow_initializes_and_persists(self):
        service, repo = make_service()
        view = service.follow("u1", 1067983, 10_000)
        self.assertEqual(view["marketValue"], 10_000)
        self.assertEqual(len(view["positions"]), 2)
        self.assertEqual(view["appliedAccession"], "acc-1")
        self.assertIn(("u1", 1067983), repo.shadows)
        self.assertEqual(len(repo.trades), 2)
        self.assertIn("2026-08-14", view["asOfLabel"])

    def test_follow_unknown_filer_raises(self):
        service, _ = make_service()
        with self.assertRaises(ValueError):
            service.follow("u1", 999, 10_000)


class LazyRebalanceTests(unittest.TestCase):
    def test_new_filing_rebalances_on_read(self):
        service, repo = make_service()
        service.follow("u1", 1067983, 10_000)
        # filer files a new quarter: MSFT out, NVDA in
        repo.put_filer_snapshot(
            1067983, "Berkshire", "acc-2", "2026-11-14",
            [{"ticker": "AAPL", "weight": 0.5, "provenance": "acc-2"},
             {"ticker": "NVDA", "weight": 0.5, "provenance": "acc-2"}])
        before = len(repo.trades)
        view = service.get_shadow("u1", 1067983)
        self.assertEqual(view["appliedAccession"], "acc-2")
        tickers = {p["ticker"] for p in view["positions"]}
        self.assertEqual(tickers, {"AAPL", "NVDA"})
        self.assertGreater(len(repo.trades), before)
        self.assertAlmostEqual(view["marketValue"], 10_000, places=0)

    def test_second_read_is_idempotent(self):
        service, repo = make_service()
        service.follow("u1", 1067983, 10_000)
        repo.put_filer_snapshot(
            1067983, "Berkshire", "acc-2", "2026-11-14",
            [{"ticker": "AAPL", "weight": 1.0, "provenance": "acc-2"}])
        service.get_shadow("u1", 1067983)
        count = len(repo.trades)
        service.get_shadow("u1", 1067983)
        self.assertEqual(len(repo.trades), count, "re-read must not re-trade")

    def test_unknown_shadow_returns_none(self):
        service, _ = make_service()
        self.assertIsNone(service.get_shadow("u1", 1067983))


class StalenessTests(unittest.TestCase):
    def test_stale_rules(self):
        self.assertTrue(_is_stale(""))
        self.assertTrue(_is_stale("2024-01-01"))
        self.assertTrue(_is_stale("not-a-date"))


if __name__ == "__main__":
    unittest.main()
