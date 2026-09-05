"""Offline tests for the House Clerk -> CongressTrade adapter."""

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.ingestion.house_clerk import to_congress_trade  # noqa: E402
from src.ingestion.house_ptr import PTRFiling, PTRTrade  # noqa: E402
from src.models.congress import Chamber, PoliticalParty, TransactionType  # noqa: E402

FILING = PTRFiling("20035370", "Jackson", "Jonathan", "IL01", "9/3/2026", 2026)
TRADE = PTRTrade(owner="JT", asset="ViaSat, Inc. - Common Stock", ticker="VSAT",
                 action="sell_partial", transaction_date="08/28/2026",
                 notification_date="09/02/2026", amount_low=1001, amount_high=15000)


class AdapterTests(unittest.TestCase):
    def test_maps_all_fields(self):
        t = to_congress_trade(FILING, TRADE, 0)
        self.assertEqual(t.memberName, "Jonathan Jackson")
        self.assertEqual(t.chamber, Chamber.HOUSE)
        self.assertEqual(t.state, "IL")
        self.assertEqual(t.party, PoliticalParty.UNKNOWN)
        self.assertEqual(t.ticker, "VSAT")
        self.assertEqual(t.transactionType, TransactionType.SALE_PARTIAL)
        self.assertEqual(t.transactionDate.strftime("%Y-%m-%d"), "2026-08-28")
        self.assertEqual(t.disclosureDate.strftime("%Y-%m-%d"), "2026-09-03")
        self.assertEqual((t.amountRangeLow, t.amountRangeHigh), (1001, 15000))
        self.assertEqual(t.daysToDisclose, 6)

    def test_id_unique_per_row(self):
        a = to_congress_trade(FILING, TRADE, 0)
        b = to_congress_trade(FILING, TRADE, 1)
        self.assertNotEqual(a.id, b.id)
        self.assertIn("20035370", a.id)

    def test_single_digit_index_date_parses(self):
        filing = PTRFiling("20035371", "Case", "Ed", "HI01", "8/18/2026", 2026)
        t = to_congress_trade(filing, TRADE, 0)
        self.assertEqual(t.disclosureDate.strftime("%Y-%m-%d"), "2026-08-18")

    def test_unparseable_dates_return_none(self):
        bad = PTRTrade(owner="", asset="X Corp", ticker="X", action="buy",
                       transaction_date="not-a-date", notification_date="also-bad",
                       amount_low=1, amount_high=2)
        filing = PTRFiling("1", "A", "B", "TX01", "bad", 2026)
        self.assertIsNone(to_congress_trade(filing, bad, 0))


if __name__ == "__main__":
    unittest.main()
