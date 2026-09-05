"""Unit tests for the shadow-portfolio engine (pure functions, no I/O)."""

import importlib.util
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shadow_engine", REPO / "src/services/shadow_engine.py")
m = importlib.util.module_from_spec(spec)
sys.modules["shadow_engine"] = m
spec.loader.exec_module(m)


class TargetWeightTests(unittest.TestCase):
    def test_top_n_and_normalization(self):
        holdings = [{"ticker": f"T{i}", "value_usd": 1000 * (30 - i)} for i in range(30)]
        targets = m.target_weights_from_holdings(holdings, top_n=20)
        self.assertLessEqual(len(targets), 20)
        self.assertAlmostEqual(sum(t.weight for t in targets), 1.0, places=6)

    def test_unmapped_rows_excluded_before_normalizing(self):
        holdings = [
            {"ticker": "AAPL", "value_usd": 6000},
            {"ticker": "", "value_usd": 94_000},      # bond / unmapped CUSIP
            {"ticker": "MSFT", "value_usd": 4000},
        ]
        targets = m.target_weights_from_holdings(holdings)
        weights = {t.ticker: t.weight for t in targets}
        self.assertAlmostEqual(weights["AAPL"], 0.6, places=6)
        self.assertAlmostEqual(weights["MSFT"], 0.4, places=6)


class InitTests(unittest.TestCase):
    def test_initialize_allocates_by_weight(self):
        targets = [m.TargetWeight("AAPL", 0.6), m.TargetWeight("MSFT", 0.4)]
        prices = {"AAPL": 100.0, "MSFT": 200.0}
        p, trades = m.initialize_shadow(10_000, targets, prices, "acc-1")
        self.assertEqual(len(trades), 2)
        aapl = p.position("AAPL")
        self.assertAlmostEqual(aapl.shares, 60.0)          # $6k @ $100
        self.assertAlmostEqual(p.position("MSFT").shares, 20.0)  # $4k @ $200
        self.assertAlmostEqual(p.cash, 0.0, places=6)
        self.assertAlmostEqual(p.market_value(prices), 10_000, places=6)

    def test_missing_price_stays_as_cash(self):
        targets = [m.TargetWeight("AAPL", 0.5), m.TargetWeight("XXXX", 0.5)]
        p, trades = m.initialize_shadow(10_000, targets, {"AAPL": 100.0}, "acc-1")
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(p.cash, 5_000)              # unpriced weight -> cash


class FilingTests(unittest.TestCase):
    def setUp(self):
        self.prices = {"AAPL": 100.0, "MSFT": 200.0, "NVDA": 50.0}
        targets = [m.TargetWeight("AAPL", 0.5), m.TargetWeight("MSFT", 0.5)]
        self.p, _ = m.initialize_shadow(10_000, targets, self.prices, "acc-1")

    def test_exit_and_open(self):
        # New filing: MSFT gone, NVDA opened.
        new = [m.TargetWeight("AAPL", 0.5), m.TargetWeight("NVDA", 0.5)]
        trades = m.apply_filing(self.p, new, self.prices, "acc-2")
        kinds = {(t.ticker, t.kind) for t in trades}
        self.assertIn(("MSFT", "exited"), kinds)
        self.assertIn(("NVDA", "opened"), kinds)
        self.assertIsNone(self.p.position("MSFT"))
        self.assertIsNotNone(self.p.position("NVDA"))
        # Value is conserved (no price moves in this test).
        self.assertAlmostEqual(self.p.market_value(self.prices), 10_000, places=2)

    def test_rebalance_weights(self):
        new = [m.TargetWeight("AAPL", 0.8), m.TargetWeight("MSFT", 0.2)]
        trades = m.apply_filing(self.p, new, self.prices, "acc-2")
        kinds = {(t.ticker, t.kind) for t in trades}
        self.assertIn(("MSFT", "decreased"), kinds)
        self.assertIn(("AAPL", "increased"), kinds)
        total = self.p.market_value(self.prices)
        aapl_value = self.p.position("AAPL").shares * 100.0
        self.assertAlmostEqual(aapl_value / total, 0.8, places=2)

    def test_idempotent_per_accession(self):
        new = [m.TargetWeight("AAPL", 1.0)]
        first = m.apply_filing(self.p, new, self.prices, "acc-2")
        second = m.apply_filing(self.p, new, self.prices, "acc-2")
        self.assertTrue(first)
        self.assertEqual(second, [], "same accession must not rebalance twice")

    def test_provenance_carried_on_trades(self):
        new = [m.TargetWeight("AAPL", 1.0)]
        trades = m.apply_filing(self.p, new, self.prices, "acc-2")
        self.assertTrue(all(t.provenance == "acc-2" for t in trades))


if __name__ == "__main__":
    unittest.main()


class PTRNudgeTests(unittest.TestCase):
    def test_buy_nudges_weight_by_range_midpoint(self):
        targets = m.nudge_targets_from_ptr(
            [], [{"ticker": "NVDA", "action": "buy",
                  "amount_low": 15_001, "amount_high": 50_000,
                  "provenance": "doc-1"}])
        self.assertEqual(len(targets), 1)
        self.assertAlmostEqual(targets[0].weight, 32_500.5 / 1_000_000, places=6)
        self.assertEqual(targets[0].provenance, "doc-1")

    def test_full_sell_exits_partial_reduces(self):
        base = [m.TargetWeight("AAPL", 0.10), m.TargetWeight("MSFT", 0.10)]
        targets = m.nudge_targets_from_ptr(base, [
            {"ticker": "AAPL", "action": "sell", "amount_low": 1, "amount_high": 1},
            {"ticker": "MSFT", "action": "sell_partial",
             "amount_low": 15_001, "amount_high": 50_000},
        ])
        weights = {t.ticker: t.weight for t in targets}
        self.assertNotIn("AAPL", weights)             # full sale -> exit
        self.assertAlmostEqual(weights["MSFT"], 0.10 - 32_500.5 / 1_000_000, places=6)

    def test_cap_and_floor(self):
        capped = m.nudge_targets_from_ptr(
            [], [{"ticker": "SPY", "action": "buy",
                  "amount_low": 500_000, "amount_high": 1_000_000}])
        self.assertAlmostEqual(capped[0].weight, m.PTR_MAX_WEIGHT)
        gone = m.nudge_targets_from_ptr(
            [m.TargetWeight("KO", 0.004)],
            [{"ticker": "KO", "action": "sell_partial",
              "amount_low": 1_001, "amount_high": 15_000}])
        self.assertEqual(gone, [])                    # below sliver -> dropped
