"""Tests for the memory cache manager."""

import datetime
import time
import unittest
from unittest import mock

from beansprout.quoter.sources import cache_manager


class MemoryCacheManagerTest(unittest.TestCase):
    """Tests for MemoryCacheManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = cache_manager.MemoryCacheManager(ttl_seconds=3600,
                                                        max_entries=100)

    def test_initial_state(self):
        """Test that the cache starts empty with proper stats."""
        stats = self.manager.get_stats()
        self.assertEqual(0, stats['hits'])
        self.assertEqual(0, stats['misses'])
        self.assertEqual(0, stats['hit_ratio'])

    def test_cache_miss(self):
        """Test that cache returns None when entry not present."""
        ticker = "TEST"
        base_ticker = "USD"
        date = datetime.date(2025, 5, 1)

        result = self.manager.get(ticker, base_ticker, date)

        self.assertIsNone(result)
        stats = self.manager.get_stats()
        self.assertEqual(0, stats['hits'])
        self.assertEqual(1, stats['misses'])

    def test_get_put_get(self):
        """Test that put stores data and get retrieves it."""
        ticker = "TEST"
        base_ticker = "USD"
        date = datetime.date(2025, 5, 1)
        test_data = {"price": 123.45}

        # First get should be a miss
        self.assertIsNone(self.manager.get(ticker, base_ticker, date))

        # Put the data
        self.manager.put(ticker, base_ticker, date, test_data)

        # Second get should be a hit
        result = self.manager.get(ticker, base_ticker, date)
        self.assertEqual(test_data, result)

        stats = self.manager.get_stats()
        self.assertEqual(1, stats['hits'])
        self.assertEqual(1, stats['misses'])

    def test_expiry(self):
        """Test that cache entries expire after TTL."""
        ticker = "TEST"
        base_ticker = "USD"
        date = datetime.date(2025, 5, 1)
        test_data = {"price": 123.45}

        # Use a custom mock for datetime.now instead of sleep
        original_datetime = datetime.datetime

        # Mock the datetime.datetime
        class MockDateTime:
            mock_now = original_datetime.now()

            @classmethod
            def now(cls):
                return cls.mock_now

        # Create a manager for testing
        manager = cache_manager.MemoryCacheManager(ttl_seconds=3600,
                                                   max_entries=100)

        # Keep the original implementation but replace the datetime object temporarily
        cache_manager.datetime.datetime = MockDateTime

        # Store with current timestamp
        manager.put(ticker, base_ticker, date, test_data)

        # Verify it's retrievable
        self.assertEqual(test_data, manager.get(ticker, base_ticker, date))

        # Advance time beyond TTL
        MockDateTime.mock_now += datetime.timedelta(seconds=4000)

        # Entry should now be expired
        self.assertIsNone(manager.get(ticker, base_ticker, date))

        # Check that misses was incremented on expired entry retrieval
        stats = manager.get_stats()
        self.assertEqual(1, stats['hits'])
        self.assertEqual(1, stats['misses'])

        # Restore original datetime
        cache_manager.datetime.datetime = original_datetime

    def test_max_entries(self):
        """Test that cache enforces the max entries limit."""
        # Fill cache to max
        max_entries = 5
        manager = cache_manager.MemoryCacheManager(ttl_seconds=3600,
                                                   max_entries=max_entries)

        for i in range(max_entries + 3):  # Add 3 more than max
            ticker = f"TEST{i}"
            date = datetime.date(2025, 5, 1)
            test_data = {"price": 100 + i}

            manager.put(ticker, "USD", date, test_data)

        # Verify size is maintained
        cache_size = len(manager._cache)
        self.assertEqual(max_entries, cache_size)

        # Verify oldest entries were removed (TEST0, TEST1, TEST2)
        for i in range(3):
            ticker = f"TEST{i}"
            date = datetime.date(2025, 5, 1)
            self.assertIsNone(manager.get(ticker, "USD", date))

        # Verify newest entries are still there
        for i in range(3, max_entries + 3):
            ticker = f"TEST{i}"
            date = datetime.date(2025, 5, 1)
            expected_data = {"price": 100 + i}
            self.assertEqual(expected_data, manager.get(ticker, "USD", date))


if __name__ == '__main__':
    unittest.main()
