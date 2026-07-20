"""Tests for the SQLite cache and the CachedClient decorator."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from insightflow.services.cache import CachedClient, PayloadCache
from insightflow.services.errors import RateLimitError
from insightflow.tests.fixtures import alpha_vantage_payload


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "cache.sqlite3"
        self.cache = PayloadCache(self.db_path, ttl_seconds=3600)
        self.addCleanup(self.cache.close)
        self.payload = alpha_vantage_payload([100.0, 101.0, 102.0], symbol="TEST")


class TestPayloadCache(CacheTestCase):
    def test_miss_then_hit(self):
        self.assertIsNone(self.cache.get("TEST"))
        self.cache.set("TEST", self.payload)
        self.assertEqual(self.cache.get("TEST"), self.payload)

    def test_key_is_case_insensitive(self):
        self.cache.set("test", self.payload)
        self.assertEqual(self.cache.get("TEST"), self.payload)

    def test_expired_entry_is_a_miss(self):
        self.cache.set("TEST", self.payload, now=0.0)
        self.assertIsNone(self.cache.get("TEST", now=10_000.0))

    def test_fresh_entry_within_ttl_is_a_hit(self):
        self.cache.set("TEST", self.payload, now=0.0)
        self.assertIsNotNone(self.cache.get("TEST", now=100.0))

    def test_set_overwrites(self):
        self.cache.set("TEST", self.payload)
        newer = alpha_vantage_payload([1.0], symbol="TEST")
        self.cache.set("TEST", newer)
        self.assertEqual(self.cache.get("TEST"), newer)
        self.assertEqual(self.cache.symbols(), ["TEST"])

    def test_delete_and_clear(self):
        self.cache.set("A", self.payload)
        self.cache.set("B", self.payload)
        self.cache.delete("A")
        self.assertEqual(self.cache.symbols(), ["B"])
        self.cache.clear()
        self.assertEqual(self.cache.symbols(), [])

    def test_corrupt_row_degrades_to_a_miss(self):
        self.cache.set("TEST", self.payload)
        self.cache._conn.execute("UPDATE payloads SET payload = '{not json'")
        self.cache._conn.commit()
        self.assertIsNone(self.cache.get("TEST"))

    def test_cache_survives_reopening_the_file(self):
        self.cache.set("TEST", self.payload)
        self.cache.close()
        reopened = PayloadCache(self.db_path, ttl_seconds=3600)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get("TEST"), self.payload)


class TestCachedClient(CacheTestCase):
    def setUp(self):
        super().setUp()
        self.inner = Mock()
        self.inner.fetch_stock_data.return_value = self.payload
        self.client = CachedClient(self.inner, self.cache)

    def test_repeat_lookup_spends_no_api_call(self):
        first = self.client.fetch_stock_data("TEST")
        second = self.client.fetch_stock_data("TEST")
        self.assertEqual(first, second)
        self.inner.fetch_stock_data.assert_called_once_with("TEST")

    def test_provenance_is_reported(self):
        self.client.fetch_stock_data("TEST")
        self.assertEqual(self.client.last_source, "network")
        self.client.fetch_stock_data("TEST")
        self.assertEqual(self.client.last_source, "cache")

    def test_demo_source_is_not_labelled_network(self):
        from insightflow.services.api_client import DemoClient

        client = CachedClient(DemoClient(), self.cache)
        client.fetch_stock_data("AAPL")
        self.assertEqual(client.last_source, "sample data")

    def test_distinct_symbols_each_cost_one_call(self):
        self.client.fetch_stock_data("AAA")
        self.client.fetch_stock_data("BBB")
        self.assertEqual(self.inner.fetch_stock_data.call_count, 2)

    def test_errors_propagate_and_are_not_cached(self):
        self.inner.fetch_stock_data.side_effect = RateLimitError("throttled")
        with self.assertRaises(RateLimitError):
            self.client.fetch_stock_data("TEST")
        self.assertIsNone(self.cache.get("TEST"))

    def test_recovers_after_a_rate_limit(self):
        self.inner.fetch_stock_data.side_effect = [RateLimitError("throttled"), self.payload]
        with self.assertRaises(RateLimitError):
            self.client.fetch_stock_data("TEST")
        self.assertEqual(self.client.fetch_stock_data("TEST"), self.payload)

    def test_interface_is_interchangeable_with_a_plain_client(self):
        # The UI calls exactly this and nothing else.
        self.assertTrue(callable(self.client.fetch_stock_data))
        self.assertEqual(self.client.fetch_stock_data("TEST"), self.payload)


if __name__ == "__main__":
    unittest.main()
