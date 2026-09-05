"""Offline tests for SEC company-facts ratio computation (fixture-based)."""

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.ingestion import sec_facts  # noqa: E402


def fixture_facts():
    def duration(form, start, end, val):
        return {"form": form, "start": start, "end": end, "val": val}
    def instant(end, val, form="10-Q"):
        return {"form": form, "end": end, "val": val}
    return {"facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            instant("2026-06-30", 1_000_000_000)]}}},
        "us-gaap": {
            "EarningsPerShareDiluted": {"units": {"USD/shares": [
                duration("10-Q", "2025-07-01", "2025-09-28", 1.00),
                duration("10-Q", "2025-09-29", "2025-12-28", 2.00),
                duration("10-Q", "2025-12-29", "2026-03-29", 1.50),
                duration("10-Q", "2026-03-30", "2026-06-28", 1.50),
                duration("10-K", "2024-10-01", "2025-09-30", 5.25),
            ]}},
            "NetIncomeLoss": {"units": {"USD": [
                duration("10-K", "2024-10-01", "2025-09-30", 6_000_000_000)]}},
            "Revenues": {"units": {"USD": [
                duration("10-K", "2024-10-01", "2025-09-30", 50_000_000_000)]}},
            "StockholdersEquity": {"units": {"USD": [
                instant("2026-06-30", 20_000_000_000)]}},
            "Assets": {"units": {"USD": [instant("2026-06-30", 60_000_000_000)]}},
            "AssetsCurrent": {"units": {"USD": [instant("2026-06-30", 15_000_000_000)]}},
            "LiabilitiesCurrent": {"units": {"USD": [instant("2026-06-30", 10_000_000_000)]}},
        },
    }}


class RatioTests(unittest.TestCase):
    def test_trailing_eps_sums_last_four_quarters(self):
        self.assertEqual(sec_facts.trailing_eps_from_facts(fixture_facts()), 6.0)

    def test_ratios_computed_from_facts(self):
        r = sec_facts.ratios_from_facts(fixture_facts(), "test", price=120.0)
        self.assertEqual(r["earnings_per_share"], 6.0)
        self.assertEqual(r["price_to_earnings"], 20.0)
        self.assertEqual(r["market_cap"], 120.0 * 1_000_000_000)
        self.assertEqual(r["price_to_book"], 6.0)      # 120B / 20B
        self.assertEqual(r["return_on_equity"], 0.3)   # 6B / 20B
        self.assertEqual(r["current"], 1.5)
        self.assertIsNone(r["ev_to_ebitda"])           # unsourced -> None, never faked

    def test_eps_computed_fallback_from_net_income(self):
        facts = fixture_facts()
        del facts["facts"]["us-gaap"]["EarningsPerShareDiluted"]
        facts["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"] = {
            "units": {"shares": [{"form": "10-K", "start": "2024-10-01",
                                  "end": "2025-09-30", "val": 1_200_000_000}]}}
        r = sec_facts.ratios_from_facts(facts, "test", price=100.0)
        self.assertEqual(r["earnings_per_share"], 5.0)  # 6B / 1.2B

    def test_no_price_no_marketcap(self):
        r = sec_facts.ratios_from_facts(fixture_facts(), "test", price=None)
        self.assertIsNone(r["market_cap"])
        self.assertIsNone(r["price_to_earnings"])
        self.assertEqual(r["earnings_per_share"], 6.0)


if __name__ == "__main__":
    unittest.main()
