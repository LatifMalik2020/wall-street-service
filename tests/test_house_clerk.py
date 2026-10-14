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


class EnrichmentTests(unittest.TestCase):
    def test_member_info_fills_party_and_canonical_name(self):
        info = {"party": "D", "fullName": "Jonathan L. Jackson"}
        t = to_congress_trade(FILING, TRADE, 0, member_info=info)
        self.assertEqual(t.party, PoliticalParty.DEMOCRAT)
        self.assertEqual(t.memberName, "Jonathan L. Jackson")

    def test_no_info_stays_unknown(self):
        t = to_congress_trade(FILING, TRADE, 0, member_info=None)
        self.assertEqual(t.party, PoliticalParty.UNKNOWN)

    def test_lookup_by_district_then_state(self):
        from src.ingestion.legislators import lookup
        index = {"IL:01:jackson": {"party": "D", "fullName": "Jonathan L. Jackson"},
                 "OK:hern": {"party": "R", "fullName": "Kevin Hern"}}
        self.assertEqual(lookup(index, "IL01", "Jackson")["party"], "D")
        self.assertEqual(lookup(index, "OK01", "Hern")["party"], "R")
        self.assertIsNone(lookup(index, "TX07", "Nobody"))

    def test_lookup_compound_surname_falls_back_to_sole_district_member(self):
        from src.ingestion.legislators import lookup
        index = {"MD:06:mcclain delaney": {"party": "D", "fullName": "April McClain Delaney"},
                 "MD:mcclain delaney": {"party": "D", "fullName": "April McClain Delaney"}}
        # Clerk files her as Last='Delaney', First='April McClain'
        self.assertEqual(lookup(index, "MD06", "Delaney")["fullName"], "April McClain Delaney")
        index["MD:06:other"] = {"party": "R", "fullName": "Someone Else"}
        self.assertIsNone(lookup(index, "MD06", "Delaney"))  # ambiguous seat: no guess



class FetchLatestTests(unittest.TestCase):
    """fetch_latest_sync downloads PTRs concurrently; order and failure
    accounting must match the old serial loop."""

    def test_parallel_fetch_keeps_docid_order_and_skips_failures(self):
        import time
        from unittest import mock

        from src.ingestion import house_clerk, house_ptr

        names = ["Adams", "Baker", "Clark", "Davis"]
        filings = [
            PTRFiling(f"2003537{i}", last, "Pat", "IL01", "9/3/2026", 2026)
            for i, last in enumerate(names)
        ]

        def fake_text(doc_id, year):
            i = int(doc_id[-1])
            if i == 2:
                raise IOError("boom")
            time.sleep(0.05 * (4 - i))  # later DocIDs finish first
            return doc_id

        with mock.patch.object(house_ptr, "fetch_index", return_value=filings), \
             mock.patch.object(house_ptr, "fetch_ptr_text", side_effect=fake_text), \
             mock.patch.object(house_ptr, "parse_ptr", return_value=[TRADE]), \
             mock.patch.object(house_clerk.legislators, "load_member_index", return_value={}):
            trades = house_clerk.fetch_latest_sync(year=2026)

        self.assertEqual(
            [t.memberName.split()[-1] for t in trades], ["Adams", "Baker", "Davis"]
        )


if __name__ == "__main__":
    unittest.main()
