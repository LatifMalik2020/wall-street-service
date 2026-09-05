"""Unit tests for the EDGAR 13F parser + diff (synthetic data, no network)."""

import importlib.util
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("edgar_13f", REPO / "src/ingestion/edgar_13f.py")
m = importlib.util.module_from_spec(spec)
sys.modules["edgar_13f"] = m  # dataclass resolution on py3.14 needs this
spec.loader.exec_module(m)

NS = 'xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"'


def table(rows: str) -> bytes:
    return f'<informationTable {NS}>{rows}</informationTable>'.encode()


def row(issuer, cusip, value, shares, put_call=""):
    pc = f"<putCall>{put_call}</putCall>" if put_call else ""
    return (f"<infoTable><nameOfIssuer>{issuer}</nameOfIssuer><cusip>{cusip}</cusip>"
            f"<value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt>"
            f"<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>{pc}</infoTable>")


class ParserTests(unittest.TestCase):
    def test_parses_and_aggregates_duplicate_cusips(self):
        xml = table(row("ACME CORP", "000111222", 5_000_000, 100)
                    + row("ACME CORP", "000111222", 3_000_000, 50))
        holdings = m.parse_info_table(xml)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].shares, 150)
        self.assertEqual(holdings[0].value_usd, 8_000_000)

    def test_skips_put_call_rows(self):
        xml = table(row("ACME CORP", "000111222", 5_000_000, 100)
                    + row("HEDGE CO", "999888777", 9_000_000, 200, put_call="Put"))
        holdings = m.parse_info_table(xml)
        self.assertEqual([h.cusip for h in holdings], ["000111222"])


class DiffTests(unittest.TestCase):
    def H(self, cusip, shares, value=10_000_000, issuer="X"):
        return m.Holding(issuer, cusip, value, shares)

    def test_detects_all_change_kinds(self):
        prev = [self.H("A", 100), self.H("B", 100), self.H("C", 100)]
        curr = [self.H("A", 150), self.H("B", 40), self.H("D", 70)]
        kinds = {c.cusip: c.kind for c in m.diff_holdings(prev, curr)}
        self.assertEqual(kinds, {"A": "increased", "B": "decreased",
                                 "C": "exited", "D": "opened"})

    def test_small_positions_filtered(self):
        prev = []
        curr = [self.H("TINY", 10, value=50_000)]
        self.assertEqual(m.diff_holdings(prev, curr), [])

    def test_pct_change(self):
        prev = [self.H("A", 100)]
        curr = [self.H("A", 145)]
        change = m.diff_holdings(prev, curr)[0]
        self.assertAlmostEqual(change.pct_change, 45.0)


if __name__ == "__main__":
    unittest.main()
