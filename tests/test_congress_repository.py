"""Offline regression tests for CongressRepository writes (fake table, no AWS).

Guards the prod bug where every scheduler ingestion run logged
"Failed to save trade: 'str' object has no attribute 'value'": BaseEntity sets
``use_enum_values=True`` so validated enum fields are plain str, and the
repository called ``.value`` on them. Trades were never persisted.
"""

import pathlib
import sys
import unittest
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.models.base import enum_value  # noqa: E402
from src.models.congress import (  # noqa: E402
    Chamber,
    CongressMember,
    CongressTrade,
    PoliticalParty,
    TransactionType,
)
from src.repositories.congress import CongressRepository  # noqa: E402
from src.repositories.cramer import CramerRepository  # noqa: E402
from src.models.cramer import CramerPick, CramerRecommendation  # noqa: E402


class _FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)


def _repo(cls):
    """Build a repository without touching boto3 (skip DynamoDBRepository.__init__)."""
    repo = cls.__new__(cls)
    repo._table = _FakeTable()
    repo._table_name = "test"
    return repo


def _trade(**overrides) -> CongressTrade:
    base = dict(
        id="20260929_josh-gottheimer_MSFT_20031234_001",
        memberId="josh-gottheimer",
        memberName="Josh Gottheimer",
        party=PoliticalParty.DEMOCRAT,
        chamber=Chamber.HOUSE,
        state="NJ",
        ticker="MSFT",
        companyName="Microsoft",
        transactionType=TransactionType.PURCHASE,
        transactionDate=datetime(2026, 9, 15),
        disclosureDate=datetime(2026, 9, 29),
        amountRangeLow=1001,
        amountRangeHigh=15000,
        daysToDisclose=14,
    )
    base.update(overrides)
    return CongressTrade(**base)


class EnumValueTests(unittest.TestCase):
    def test_validated_model_fields_are_plain_values(self):
        trade = _trade()
        self.assertIsInstance(trade.party, str)
        self.assertEqual(trade.party, PoliticalParty.DEMOCRAT.value)

    def test_enum_value_accepts_enum_and_plain(self):
        self.assertEqual(enum_value(PoliticalParty.REPUBLICAN), "R")
        self.assertEqual(enum_value("R"), "R")
        self.assertIsNone(enum_value(None))


class CongressRepositorySaveTests(unittest.TestCase):
    def test_save_trade_writes_item_with_plain_enum_values(self):
        repo = _repo(CongressRepository)
        repo.save_trade(_trade())

        # save_trade writes the global feed item plus a per-member copy.
        items = repo._table.items
        self.assertGreaterEqual(len(items), 1)
        for item in items:
            self.assertEqual(item["party"], "D")
            self.assertEqual(item["chamber"], Chamber.HOUSE.value)
            self.assertEqual(item["transactionType"], TransactionType.PURCHASE.value)
        feed = next(i for i in items if i["PK"] == CongressRepository.PK_CONGRESS)
        self.assertTrue(feed["SK"].startswith(CongressRepository.SK_TRADE_PREFIX))
        self.assertEqual(feed["GSI1PK"], "TICKER#MSFT")

    def test_save_trade_accepts_enum_members_from_model_construct(self):
        # model_construct() skips validation, so fields stay Enum members.
        repo = _repo(CongressRepository)
        trade = CongressTrade.model_construct(**_trade().model_dump())
        trade.party = PoliticalParty.REPUBLICAN
        trade.chamber = Chamber.SENATE
        trade.transactionType = TransactionType.SALE
        repo.save_trade(trade)
        item = repo._table.items[0]
        self.assertEqual(item["party"], "R")
        self.assertEqual(item["chamber"], Chamber.SENATE.value)
        self.assertEqual(item["transactionType"], TransactionType.SALE.value)

    def test_save_member_writes_item_with_plain_enum_values(self):
        repo = _repo(CongressRepository)
        member = CongressMember(
            id="josh-gottheimer",
            name="Josh Gottheimer",
            party=PoliticalParty.DEMOCRAT,
            chamber=Chamber.HOUSE,
            state="NJ",
            totalTrades=3,
        )
        repo.save_member(member)
        item = repo._table.items[0]
        self.assertEqual(item["party"], "D")
        self.assertEqual(item["chamber"], Chamber.HOUSE.value)
        self.assertEqual(item["totalTrades"], 3)


class CramerRepositorySaveTests(unittest.TestCase):
    def test_save_pick_writes_plain_recommendation(self):
        repo = _repo(CramerRepository)
        pick = CramerPick(
            id="2026-09-29#NVDA",
            ticker="NVDA",
            companyName="NVIDIA",
            recommendation=CramerRecommendation.BUY,
            priceAtPick=100.0,
            currentPrice=110.0,
            returnPercent=10.0,
            inverseReturnPercent=-10.0,
            pickDate=datetime(2026, 9, 29),
            showName="Mad Money",
        )
        repo.save_pick(pick)
        item = repo._table.items[0]
        self.assertEqual(item["recommendation"], CramerRecommendation.BUY.value)


if __name__ == "__main__":
    unittest.main()
