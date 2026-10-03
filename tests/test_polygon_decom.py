"""Polygon decommission: with Alpaca credentials configured, NO market-data
method may reach api.polygon.io — even when POLYGON_API_KEY is still set and
even when the primary source errors. Plus offline tests for the FINRA short
interest and SEC shares-outstanding parsers."""

import asyncio
import pathlib
import sys
from unittest import mock

import httpx
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.ingestion import alpaca_market, finra, sec_facts  # noqa: E402
from src.ingestion.alpaca_market import AlpacaMarketClient  # noqa: E402
from src.ingestion.polygon_client import PolygonMarketClient  # noqa: E402
from src.utils.errors import ExternalAPIError  # noqa: E402


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    c = AlpacaMarketClient()
    c.api_key = "polygon-key-still-set"

    def forbidden(self):
        raise AssertionError("Polygon transport touched")

    monkeypatch.setattr(PolygonMarketClient, "client", property(forbidden))
    return c


def _http_error(*_a, **_kw):
    raise httpx.ConnectError("boom")


def test_factory_always_returns_alpaca_facade(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    assert isinstance(alpaca_market.market_data_client(), AlpacaMarketClient)


def test_price_failures_never_fall_back_to_polygon(client, monkeypatch):
    monkeypatch.setattr(client, "_alpaca_get", mock.AsyncMock(side_effect=_http_error))
    with pytest.raises(ExternalAPIError):
        run(client.get_quote("AAPL"))
    assert run(client.batch_quotes(["AAPL"])) == {}
    with pytest.raises(ExternalAPIError):
        run(client.get_bulk_snapshot(["AAPL"]))
    assert run(client.get_market_movers()) == ([], [])
    with pytest.raises(ExternalAPIError):
        run(client.get_index_aggregates("SPY", 1, "day", "2026-01-01", "2026-02-01"))
    with pytest.raises(ExternalAPIError):
        run(client.get_index_aggregates("SPY", 1, "month", "2026-01-01", "2026-02-01"))


def test_fundamental_failures_never_fall_back_to_polygon(client, monkeypatch):
    monkeypatch.setattr(client, "_alpaca_get", mock.AsyncMock(side_effect=_http_error))
    boom = mock.AsyncMock(side_effect=RuntimeError("sec down"))
    monkeypatch.setattr(sec_facts, "get_ratios", boom)
    monkeypatch.setattr(sec_facts, "get_income_statements", boom)
    monkeypatch.setattr(sec_facts, "get_filings", boom)
    monkeypatch.setattr(sec_facts, "shares_outstanding_record", boom)
    monkeypatch.setattr(finra, "get_short_volume", mock.AsyncMock(return_value=[]))
    monkeypatch.setattr(finra, "get_short_interest", mock.AsyncMock(return_value=[]))
    assert run(client.get_ratios("AAPL")) is None
    assert run(client.get_income_statements("AAPL")) == []
    assert run(client.get_filings("AAPL")) == []
    assert run(client.get_float("AAPL")) is None
    assert run(client.get_short_volume("AAPL")) == []
    assert run(client.get_short_interest("AAPL")) == []


def test_no_free_source_methods_are_empty_without_network(client):
    assert run(client.get_ipos()) == []
    assert run(client.get_earnings_calendar()) == []
    assert run(client.get_snapshot_all()) == []


def test_stock_detail_uses_finra_short_interest(client, monkeypatch):
    snap = {"latestTrade": {"p": 10.0}, "dailyBar": {"c": 10.0, "v": 5},
            "prevDailyBar": {"c": 8.0}}
    monkeypatch.setattr(client, "_alpaca_get",
                        mock.AsyncMock(return_value={"snapshots": {"AAPL": snap}}))
    monkeypatch.setattr(sec_facts, "get_ratios", mock.AsyncMock(return_value={"ticker": "AAPL"}))
    si = [{"ticker": "AAPL", "short_interest": 1.0, "avg_daily_volume": 2.0,
           "days_to_cover": 0.5, "settlement_date": "2026-08-31"}]
    monkeypatch.setattr(finra, "get_short_interest", mock.AsyncMock(return_value=si))
    out = run(client.get_stock_detail("AAPL"))
    assert out["snapshot"]["price"] == 10.0
    assert out["ratios"] == {"ticker": "AAPL"}
    assert out["shortInterest"] == si[0]


def test_float_reports_shares_outstanding_not_float(client, monkeypatch):
    monkeypatch.setattr(sec_facts, "shares_outstanding_record",
                        mock.AsyncMock(return_value={"value": 100.0, "date": "2026-07-17"}))
    out = run(client.get_float("aapl"))
    assert out == {"ticker": "AAPL", "effective_date": "2026-07-17",
                   "free_float": None, "free_float_percent": None,
                   "shares_outstanding": 100.0}


def test_finra_short_interest_rows_desc_and_shaped():
    recs = [
        {"symbolCode": "AAPL", "settlementDate": "2026-08-14",
         "currentShortPositionQuantity": 116327753, "averageDailyVolumeQuantity": 46065396,
         "daysToCoverQuantity": 2.53},
        {"symbolCode": "AAPL", "settlementDate": "2026-08-31",
         "currentShortPositionQuantity": 139749097, "averageDailyVolumeQuantity": 39537335,
         "daysToCoverQuantity": None},
        {"symbolCode": "AAPLX", "settlementDate": "2026-08-31",
         "currentShortPositionQuantity": 1},
    ]
    rows = finra.short_interest_rows_from_finra("aapl", recs, limit=5)
    assert [r["settlement_date"] for r in rows] == ["2026-08-31", "2026-08-14"]
    assert rows[0] == {"ticker": "AAPL", "short_interest": 139749097.0,
                       "avg_daily_volume": 39537335.0,
                       "days_to_cover": round(139749097 / 39537335, 2),
                       "settlement_date": "2026-08-31"}
    assert finra.short_interest_rows_from_finra("AAPL", recs, limit=1)[0][
        "settlement_date"] == "2026-08-31"


def test_finra_short_interest_http_failure_is_empty(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(finra.httpx, "AsyncClient", Boom)
    assert run(finra.get_short_interest("AAPL")) == []


def test_shares_outstanding_record_latest_filing_sums_classes():
    def v(end, val, accn, filed):
        return {"end": end, "val": val, "accn": accn, "filed": filed}
    facts = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        v("2026-04-20", 900, "A1", "2026-05-01"),
        v("2026-07-17", 500, "A2", "2026-08-01"),
        v("2026-07-17", 400, "A2", "2026-08-01"),
    ]}}}}}
    assert sec_facts.shares_outstanding_record_from_facts(facts) == {
        "value": 900.0, "date": "2026-07-17"}
    assert sec_facts.shares_outstanding_record_from_facts({"facts": {}}) is None
