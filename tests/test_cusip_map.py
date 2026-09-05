"""Unit tests for CUSIP->ticker mapping (mocked network)."""

import importlib.util
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cusip_map", REPO / "src/ingestion/cusip_map.py")
m = importlib.util.module_from_spec(spec)
sys.modules["cusip_map"] = m
spec.loader.exec_module(m)


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class MapTests(unittest.TestCase):
    def setUp(self):
        m.CACHE_PATH = "/tmp/test_cusip_cache.json"
        pathlib.Path(m.CACHE_PATH).unlink(missing_ok=True)

    def test_throttled_jobs_are_retried(self):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=0):
            calls["n"] += 1
            jobs = json.loads(req.data.decode())
            if calls["n"] == 1:
                # first batch: one hit, one per-job throttle error
                return FakeResp([
                    {"data": [{"ticker": "AAA", "name": "Alpha Corp"}]},
                    {"error": "Rate limit reached"},
                ])
            # retry pass resolves the throttled job
            return FakeResp([{"data": [{"ticker": "BBB", "name": "Beta Inc"}]}])

        with patch("cusip_map.urllib.request.urlopen", fake_urlopen), \
             patch("cusip_map.time.sleep"):
            out = m.map_cusips(["111111111", "222222222"])
        self.assertEqual(out["111111111"]["ticker"], "AAA")
        self.assertEqual(out["222222222"]["ticker"], "BBB")
        self.assertEqual(calls["n"], 2, "one batch + one retry pass")

    def test_cache_prevents_refetch(self):
        def fake_urlopen(req, timeout=0):
            return FakeResp([{"data": [{"ticker": "AAA", "name": "Alpha"}]}])

        with patch("cusip_map.urllib.request.urlopen", fake_urlopen), \
             patch("cusip_map.time.sleep"):
            m.map_cusips(["111111111"])

        def explode(req, timeout=0):
            raise AssertionError("network hit despite cache")

        with patch("cusip_map.urllib.request.urlopen", explode):
            out = m.map_cusips(["111111111"])
        self.assertEqual(out["111111111"]["ticker"], "AAA")

    def test_name_normalization(self):
        self.assertEqual(m._normalize("Bank of Amer Corp"), "BANK OF AMER")
        self.assertEqual(m._normalize("ALPHABET INC CLASS C"), "ALPHABET")


if __name__ == "__main__":
    unittest.main()


class BatchLimitTests(unittest.TestCase):
    def test_keyless_batches_capped_at_10(self):
        """Keyless OpenFIGI rejects >10 jobs with HTTP 413 — every batch must
        respect the limit or nothing ever resolves."""
        import os
        sizes = []
        orig = m._openfigi_batch
        m._openfigi_batch = lambda batch: (sizes.append(len(batch)) or ({c: {"ticker": "T", "name": "N"} for c in batch}, []))
        old_key = os.environ.pop("OPENFIGI_API_KEY", None)
        old_cache, m.CACHE_PATH = m.CACHE_PATH, "/tmp/ts_test_cusip_cache_batch.json"
        try:
            import pathlib
            pathlib.Path(m.CACHE_PATH).unlink(missing_ok=True)
            m.map_cusips([f"CUSIP{i:04d}" for i in range(25)], pause=0)
            self.assertTrue(sizes, "no batches dispatched")
            self.assertLessEqual(max(sizes), 10)
        finally:
            m._openfigi_batch = orig
            m.CACHE_PATH = old_cache
            if old_key:
                os.environ["OPENFIGI_API_KEY"] = old_key

    def test_normalize_strips_suffixes_end_only(self):
        """'CHEVRON CORPORATION' must normalize to 'CHEVRON' — the old substring
        replace produced 'CHEVRON ORATION' and broke the EDGAR name fallback."""
        self.assertEqual(m._normalize("CHEVRON CORPORATION"), "CHEVRON")
        self.assertEqual(m._normalize("CHEVRON CORP"), "CHEVRON")
        self.assertEqual(m._normalize("Sirius XM Holdings Inc."), "SIRIUS XM")
        # interior tokens that merely CONTAIN a suffix are untouched
        self.assertEqual(m._normalize("CORPORATE OFFICE PROPERTIES"), "CORPORATE OFFICE PROPERTIES")
