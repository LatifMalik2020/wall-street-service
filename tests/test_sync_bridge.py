"""Regression tests for the sync-over-async bridge (PolygonMarketClient._run).

Each `_run` call creates a fresh event loop and closes it on exit. Any httpx
AsyncClient cached on the instance is bound to that loop, so it MUST be torn
down inside the same `_run` call — a client surviving into the next call
explodes with "RuntimeError: Event loop is closed" (seen in prod as
"Mover spark fetch failed" on every sparkline after the first bulk snapshot).
"""

import httpx

from src.ingestion.alpaca_market import AlpacaMarketClient


def test_run_tears_down_all_cached_transports():
    client = AlpacaMarketClient()

    async def fake_call():
        # Simulate what _alpaca_get and the base-class `client` property do:
        # lazily cache loop-bound transports on the instance.
        client._alpaca_http = httpx.AsyncClient()
        _ = client.client
        return 42

    assert client._run(fake_call()) == 42
    assert client._alpaca_http is None, "Alpaca transport must not outlive its loop"
    assert client._client is None, "Polygon transport must not outlive its loop"


def test_run_supports_repeated_calls_on_one_instance():
    # get_movers() makes several sequential sync calls on one client instance;
    # every call after the first used to fail before the teardown fix.
    client = AlpacaMarketClient()

    async def fake_call(n):
        client._alpaca_http = httpx.AsyncClient()
        return n

    assert client._run(fake_call(1)) == 1
    assert client._run(fake_call(2)) == 2
