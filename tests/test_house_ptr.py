"""Unit tests for the House PTR parser (fixtures from real extracted text)."""

import importlib.util
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("house_ptr", REPO / "src/ingestion/house_ptr.py")
m = importlib.util.module_from_spec(spec)
sys.modules["house_ptr"] = m
spec.loader.exec_module(m)

# Verbatim shape of pypdf-extracted e-filed PTR text (doc 20035370).
SINGLE = """
Name: Hon. Jonathan Jackson
Status: Member
State/District: IL01
ID Owner Asset Transaction Type Date Notification Date Amount Cap. Gains > $200?
JT ViaSat, Inc. - Common Stock (VSAT)
[ST]
S (partial) 08/28/2026 09/02/2026 $1,001 - $15,000
Filing ID #20035370
"""

MULTI = """
ID Owner Asset Transaction Type Date Notification Date Amount Cap. Gains > $200?
Apple Inc. (AAPL) [ST] P 08/14/2026 08/15/2026 $1,001 - $15,000
SP Microsoft Corporation (MSFT)
[ST]
S 08/14/2026 08/15/2026 $15,001 - $50,000
NVIDIA Corporation (NVDA) [ST] E 08/20/2026 08/21/2026 $50,001 - $100,000
"""


class ParseTests(unittest.TestCase):
    def test_single_trade_with_joint_owner(self):
        trades = m.parse_ptr(SINGLE)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t.ticker, "VSAT")
        self.assertEqual(t.owner, "JT")
        self.assertEqual(t.action, "sell_partial")
        self.assertEqual(t.transaction_date, "08/28/2026")
        self.assertEqual(t.notification_date, "09/02/2026")
        self.assertEqual((t.amount_low, t.amount_high), (1001, 15000))

    def test_multi_trade_actions_and_owners(self):
        trades = m.parse_ptr(MULTI)
        self.assertEqual([t.ticker for t in trades], ["AAPL", "MSFT", "NVDA"])
        self.assertEqual([t.action for t in trades], ["buy", "sell", "exchange"])
        self.assertEqual(trades[1].owner, "SP")
        self.assertEqual(trades[0].owner, "")
        self.assertEqual(trades[2].amount_high, 100000)

    def test_untickered_assets_skipped(self):
        trades = m.parse_ptr(
            "US Treasury Bill 4.5% [GS] P 08/01/2026 08/02/2026 $1,001 - $15,000")
        self.assertEqual(trades, [])


class FilingTests(unittest.TestCase):
    def test_efiled_detection(self):
        e = m.PTRFiling("20035370", "Jackson", "Jonathan", "IL01", "9/3/2026", 2026)
        paper = m.PTRFiling("9116311", "Rogers", "Harold", "KY05", "8/20/2026", 2026)
        self.assertTrue(e.is_efiled)
        self.assertFalse(paper.is_efiled)
        self.assertEqual(e.member, "Jonathan Jackson")


if __name__ == "__main__":
    unittest.main()
