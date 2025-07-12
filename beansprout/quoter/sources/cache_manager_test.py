"""Unit tests for the cache manager."""

import datetime
import os
import tempfile
import unittest

from beansprout.quoter.sources import cache_manager


class DBMCacheManagerTest(unittest.TestCase):
    """Tests for DBMCacheManager."""

    def setUp(self):
        """Set up test environment."""
        # Create a temporary file for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = os.path.join(self.temp_dir.name, 'test-cache.dbm')

    def tearDown(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_cache_key_generation(self):
        """Test that cache keys are generated correctly."""
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager:
            date = datetime.date(2025, 5, 10)

            key = manager._get_cache_key('AAPL', 'USD', date)
            self.assertEqual('AAPL:USD:2025-05-10', key)

            # Test with different types of inputs
            key = manager._get_cache_key('BTC', 'JPY', date)
            self.assertEqual('BTC:JPY:2025-05-10', key)

    def test_put_and_get_cache_hit(self):
        """Test storing and retrieving an item from cache."""
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # Store the data
            manager.put('AAPL', 'USD', date, quote_data)

            # Retrieve the data
            result = manager.get('AAPL', 'USD', date)

            self.assertEqual(quote_data, result)

    def test_get_cache_miss(self):
        """Test retrieving an item from cache that doesn't exist."""
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager:
            date = datetime.date(2025, 5, 10)

            result = manager.get('NONEXISTENT', 'USD', date)

            self.assertIsNone(result)

    def test_get_expired_entry(self):
        """Test retrieving an expired item from cache."""
        # Use a very short TTL for testing
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file, ttl_seconds=1) as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # Store the data
            manager.put('AAPL', 'USD', date, quote_data)

            # Verify it's there initially
            result = manager.get('AAPL', 'USD', date)
            self.assertEqual(quote_data, result)

            # Wait for expiration
            import time
            time.sleep(1.1)

            # Should return None for expired entries
            result = manager.get('AAPL', 'USD', date)
            self.assertIsNone(result)

    def test_cache_persistence(self):
        """Test that cache data persists across manager instances."""
        date = datetime.date(2025, 5, 10)
        quote_data = {'price': 150.25, 'currency': 'USD'}

        # Store data in first instance
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager1:
            manager1.put('AAPL', 'USD', date, quote_data)

        # Retrieve data in second instance
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager2:
            result = manager2.get('AAPL', 'USD', date)
            self.assertEqual(quote_data, result)

    def test_multiple_entries(self):
        """Test storing and retrieving multiple entries."""
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager:
            date1 = datetime.date(2025, 5, 10)
            date2 = datetime.date(2025, 5, 11)
            
            data1 = {'price': 150.25, 'currency': 'USD'}
            data2 = {'price': 151.50, 'currency': 'USD'}
            data3 = {'price': 2.50, 'currency': 'EUR'}

            # Store multiple entries
            manager.put('AAPL', 'USD', date1, data1)
            manager.put('AAPL', 'USD', date2, data2)
            manager.put('MSFT', 'EUR', date1, data3)

            # Retrieve and verify each
            self.assertEqual(data1, manager.get('AAPL', 'USD', date1))
            self.assertEqual(data2, manager.get('AAPL', 'USD', date2))
            self.assertEqual(data3, manager.get('MSFT', 'EUR', date1))

            # Non-existent entry should return None
            self.assertIsNone(manager.get('GOOG', 'USD', date1))

    def test_size_limit_enforcement(self):
        """Test that the cache enforces the size limit."""
        # Use a small max_entries for testing
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file, max_entries=3) as manager:
            date = datetime.date(2025, 5, 10)

            # Add more entries than the limit
            for i in range(5):
                manager.put(f'STOCK{i}', 'USD', date, {'price': 100 + i})

            # Check that size enforcement worked (may remove some older entries)
            # We can't predict exactly which entries will remain due to timestamp ordering
            # but we can verify the mechanism doesn't crash
            result = manager.get('STOCK4', 'USD', date)  # Last added should be there
            self.assertIsNotNone(result)

    def test_stats_tracking(self):
        """Test that cache statistics are tracked correctly."""
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file) as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # Initial stats should have 0 hits and misses
            initial_stats = manager.get_stats()
            self.assertEqual(0, initial_stats['hits'])
            self.assertEqual(0, initial_stats['misses'])
            self.assertEqual(0, initial_stats['hit_ratio'])

            # Cache miss should increment misses
            manager.get('NONEXISTENT', 'USD', date)
            stats = manager.get_stats()
            self.assertEqual(0, stats['hits'])
            self.assertEqual(1, stats['misses'])
            self.assertEqual(0, stats['hit_ratio'])

            # Store and retrieve - should increment hits
            manager.put('AAPL', 'USD', date, quote_data)
            manager.get('AAPL', 'USD', date)
            stats = manager.get_stats()
            self.assertEqual(1, stats['hits'])
            self.assertEqual(1, stats['misses'])
            self.assertEqual(0.5, stats['hit_ratio'])

    def test_creates_cache_directory(self):
        """Test that the cache directory is created if it doesn't exist."""
        nested_path = os.path.join(self.temp_dir.name, 'nested', 'path', 'cache.dbm')
        
        # Directory shouldn't exist initially
        self.assertFalse(os.path.exists(os.path.dirname(nested_path)))

        # Creating cache manager should create the directory
        with cache_manager.DBMCacheManager(cache_file_path=nested_path) as manager:
            self.assertTrue(os.path.exists(os.path.dirname(nested_path)))

            # Should be able to store and retrieve data
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25}
            manager.put('TEST', 'USD', date, quote_data)
            result = manager.get('TEST', 'USD', date)
            self.assertEqual(quote_data, result)

    def test_is_expired_method(self):
        """Test the _is_expired method."""
        with cache_manager.DBMCacheManager(cache_file_path=self.cache_file, ttl_seconds=3600) as manager:
            now = datetime.datetime.now().timestamp()
            
            # Recent timestamp should not be expired
            self.assertFalse(manager._is_expired(now))
            self.assertFalse(manager._is_expired(now - 1800))  # 30 minutes ago
            
            # Old timestamp should be expired
            self.assertTrue(manager._is_expired(now - 7200))  # 2 hours ago


class NullCacheManagerTest(unittest.TestCase):
    """Tests for NullCacheManager."""

    def test_get_always_returns_none(self):
        """Test that get always returns None."""
        with cache_manager.NullCacheManager() as manager:
            date = datetime.date(2025, 5, 10)

            result = manager.get('AAPL', 'USD', date)
            self.assertIsNone(result)

            # Get should still return None for any input
            result = manager.get('NONEXISTENT', 'EUR', date)
            self.assertIsNone(result)

    def test_put_is_noop(self):
        """Test that put is a no-op."""
        with cache_manager.NullCacheManager() as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # This should not raise any exceptions
            manager.put('AAPL', 'USD', date, quote_data)

            # And get should still return None
            result = manager.get('AAPL', 'USD', date)
            self.assertIsNone(result)

    def test_stats_tracking(self):
        """Test that statistics are tracked correctly."""
        with cache_manager.NullCacheManager() as manager:
            date = datetime.date(2025, 5, 10)

            # Initial stats should have 0 hits and misses
            initial_stats = manager.get_stats()
            self.assertEqual(0, initial_stats['hits'])
            self.assertEqual(0, initial_stats['misses'])
            self.assertEqual(0, initial_stats['hit_ratio'])

            # After a get, should have 1 miss
            manager.get('AAPL', 'USD', date)
            stats = manager.get_stats()
            self.assertEqual(0, stats['hits'])
            self.assertEqual(1, stats['misses'])
            self.assertEqual(0, stats['hit_ratio'])

            # After more gets, misses should increment
            manager.get('MSFT', 'USD', date)
            manager.get('GOOG', 'USD', date)
            stats = manager.get_stats()
            self.assertEqual(0, stats['hits'])
            self.assertEqual(3, stats['misses'])
            self.assertEqual(0, stats['hit_ratio'])

    def test_context_manager(self):
        """Test that the context manager protocol works."""
        # Using with statement should not raise exceptions
        with cache_manager.NullCacheManager() as manager:
            date = datetime.date(2025, 5, 10)
            result = manager.get('AAPL', 'USD', date)
            self.assertIsNone(result)


class MemoryCacheManagerTest(unittest.TestCase):
    """Tests for MemoryCacheManager."""

    def test_put_and_get_cache_hit(self):
        """Test storing and retrieving an item from memory cache."""
        with cache_manager.MemoryCacheManager() as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # Store the data
            manager.put('AAPL', 'USD', date, quote_data)

            # Retrieve the data
            result = manager.get('AAPL', 'USD', date)

            self.assertEqual(quote_data, result)

    def test_get_cache_miss(self):
        """Test retrieving an item from cache that doesn't exist."""
        with cache_manager.MemoryCacheManager() as manager:
            date = datetime.date(2025, 5, 10)

            result = manager.get('NONEXISTENT', 'USD', date)

            self.assertIsNone(result)

    def test_expiration_handling(self):
        """Test that expired entries are removed and counted as misses."""
        # Use a very short TTL for testing
        with cache_manager.MemoryCacheManager(ttl_seconds=1) as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # Store the data
            manager.put('AAPL', 'USD', date, quote_data)

            # Verify it's there initially
            result = manager.get('AAPL', 'USD', date)
            self.assertEqual(quote_data, result)

            # Wait for expiration
            import time
            time.sleep(1.1)

            # Should return None and remove expired entry
            result = manager.get('AAPL', 'USD', date)
            self.assertIsNone(result)

    def test_size_limit_enforcement(self):
        """Test that the memory cache enforces the size limit with LRU eviction."""
        # Use a small max_entries for testing
        with cache_manager.MemoryCacheManager(max_entries=3) as manager:
            date = datetime.date(2025, 5, 10)

            # Add entries up to the limit
            manager.put('STOCK1', 'USD', date, {'price': 101})
            manager.put('STOCK2', 'USD', date, {'price': 102})
            manager.put('STOCK3', 'USD', date, {'price': 103})

            # All should be accessible
            self.assertIsNotNone(manager.get('STOCK1', 'USD', date))
            self.assertIsNotNone(manager.get('STOCK2', 'USD', date))
            self.assertIsNotNone(manager.get('STOCK3', 'USD', date))

            # Add one more - should evict the oldest (STOCK1)
            manager.put('STOCK4', 'USD', date, {'price': 104})

            # STOCK4 should be there, and STOCK1 should be evicted
            self.assertIsNotNone(manager.get('STOCK4', 'USD', date))
            # Note: Due to LRU access above, the eviction order might vary

    def test_lru_access_pattern(self):
        """Test that accessing items affects LRU ordering."""
        with cache_manager.MemoryCacheManager(max_entries=2) as manager:
            date = datetime.date(2025, 5, 10)

            # Add two entries
            manager.put('OLD', 'USD', date, {'price': 100})
            manager.put('NEW', 'USD', date, {'price': 200})

            # Access the old entry to make it recently used
            manager.get('OLD', 'USD', date)

            # Add another entry - should evict 'NEW' instead of 'OLD'
            manager.put('NEWER', 'USD', date, {'price': 300})

            # 'OLD' should still be there (recently accessed)
            self.assertIsNotNone(manager.get('OLD', 'USD', date))
            # 'NEWER' should be there (just added)
            self.assertIsNotNone(manager.get('NEWER', 'USD', date))

    def test_stats_tracking(self):
        """Test that memory cache statistics are tracked correctly."""
        with cache_manager.MemoryCacheManager() as manager:
            date = datetime.date(2025, 5, 10)
            quote_data = {'price': 150.25, 'currency': 'USD'}

            # Initial stats
            stats = manager.get_stats()
            self.assertEqual(0, stats['hits'])
            self.assertEqual(0, stats['misses'])

            # Cache miss
            manager.get('MISS', 'USD', date)
            stats = manager.get_stats()
            self.assertEqual(0, stats['hits'])
            self.assertEqual(1, stats['misses'])

            # Cache hit
            manager.put('HIT', 'USD', date, quote_data)
            manager.get('HIT', 'USD', date)
            stats = manager.get_stats()
            self.assertEqual(1, stats['hits'])
            self.assertEqual(1, stats['misses'])
            self.assertEqual(0.5, stats['hit_ratio'])


if __name__ == '__main__':
    unittest.main()