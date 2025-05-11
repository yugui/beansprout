"""Unit tests for the cache manager."""

import datetime
import os
import pickle
import tempfile
import unittest
from unittest import mock

from beansprout.quoter.sources import cache_manager


class DBMCacheManagerTest(unittest.TestCase):
    """Tests for DBMCacheManager."""

    def setUp(self):
        """Set up test environment."""
        # Create a temporary file for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = os.path.join(self.temp_dir.name, 'test-cache.gdbm')

    def tearDown(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_cache_key_generation(self):
        """Test that cache keys are generated correctly."""
        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)
        date = datetime.date(2025, 5, 10)

        key = manager._get_cache_key('AAPL', 'USD', date)
        self.assertEqual('AAPL:USD:2025-05-10', key)

        # Test with different types of inputs
        key = manager._get_cache_key('BTC', 'JPY', date)
        self.assertEqual('BTC:JPY:2025-05-10', key)

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    def test_get_cache_hit(self, mock_dbm):
        """Test retrieving an item from cache that exists and is not expired."""
        mock_db = mock.MagicMock()
        # Mock that the key exists in the DB
        mock_db.__contains__.return_value = True
        mock_db.__getitem__.return_value = cache_manager.pickle.dumps(
            (datetime.datetime.now().timestamp(), {
                'price': 150.25,
                'currency': 'USD'
            }))
        mock_dbm.open.return_value = mock_db

        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)
        date = datetime.date(2025, 5, 10)

        result = manager.get('AAPL', 'USD', date)

        self.assertEqual({'price': 150.25, 'currency': 'USD'}, result)
        # Verify the key format used for lookup
        mock_db.__contains__.assert_called_with(b'AAPL:USD:2025-05-10')
        mock_db.__getitem__.assert_called_with(b'AAPL:USD:2025-05-10')

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    def test_get_cache_miss(self, mock_dbm):
        """Test retrieving an item from cache that doesn't exist."""
        mock_db = mock.MagicMock()
        # Mock that the key does not exist in the DB
        mock_db.__contains__.return_value = False
        mock_dbm.open.return_value = mock_db

        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)
        date = datetime.date(2025, 5, 10)

        result = manager.get('AAPL', 'USD', date)

        self.assertIsNone(result)
        mock_db.__contains__.assert_called_with(b'AAPL:USD:2025-05-10')
        # Ensure __getitem__ was not called
        mock_db.__getitem__.assert_not_called()

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    def test_get_expired_entry(self, mock_dbm):
        """Test retrieving an expired item from cache."""
        mock_db = mock.MagicMock()
        # Mock that the key exists in the DB but with expired timestamp
        mock_db.__contains__.return_value = True
        # Create a timestamp from 48 hours ago (beyond the default 24h TTL)
        expired_time = datetime.datetime.now().timestamp() - 2 * 86400
        mock_db.__getitem__.return_value = cache_manager.pickle.dumps(
            (expired_time, {
                'price': 150.25,
                'currency': 'USD'
            }))
        mock_dbm.open.return_value = mock_db

        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)
        date = datetime.date(2025, 5, 10)

        result = manager.get('AAPL', 'USD', date)

        self.assertIsNone(result)  # Should return None for expired entries
        mock_db.__contains__.assert_called_with(b'AAPL:USD:2025-05-10')
        mock_db.__getitem__.assert_called_with(b'AAPL:USD:2025-05-10')

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    def test_put_new_entry(self, mock_dbm):
        """Test storing a new entry in the cache."""
        mock_db = mock.MagicMock()
        mock_dbm.open.return_value = mock_db

        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)
        date = datetime.date(2025, 5, 10)
        quote_data = {'price': 150.25, 'currency': 'USD'}

        manager.put('AAPL', 'USD', date, quote_data)

        # Verify that __setitem__ was called with the right key
        mock_db.__setitem__.assert_called_once()
        call_args = mock_db.__setitem__.call_args[0]
        self.assertEqual(b'AAPL:USD:2025-05-10', call_args[0])

        # Verify that the data was pickled with timestamp
        pickled_data = pickle.loads(call_args[1])
        self.assertIsInstance(pickled_data, tuple)
        self.assertEqual(2, len(pickled_data))
        self.assertIsInstance(pickled_data[0], float)  # Timestamp
        self.assertEqual(quote_data, pickled_data[1])  # Quote data

        # Verify that sync was called to ensure data was written
        mock_db.sync.assert_called_once()

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    @mock.patch('beansprout.quoter.sources.cache_manager.os.path.exists')
    @mock.patch('beansprout.quoter.sources.cache_manager.os.makedirs')
    def test_creates_cache_directory(self, mock_makedirs, mock_exists,
                                     mock_dbm):
        """Test that the cache directory is created if it doesn't exist."""
        mock_exists.return_value = False
        mock_db = mock.MagicMock()
        mock_dbm.open.return_value = mock_db

        cache_file = '/non/existent/path/cache.gdbm'
        cache_manager.DBMCacheManager(cache_file_path=cache_file)

        mock_exists.assert_called_with('/non/existent/path')
        mock_makedirs.assert_called_with('/non/existent/path', exist_ok=True)

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    def test_cache_corruption_handling(self, mock_dbm):
        """Test handling of corrupted cache file."""
        # First call raises an exception to simulate corruption
        mock_dbm.open.side_effect = [
            Exception("Simulated corruption"),
            mock.MagicMock()  # Second call returns a valid mock
        ]

        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)

        # Verify that open was called twice - once with 'c' and once with 'n'
        self.assertEqual(2, mock_dbm.open.call_count)
        mock_dbm.open.assert_has_calls([
            mock.call(self.cache_file, 'c'),  # First attempt
            mock.call(self.cache_file, 'n')  # Second attempt (create new)
        ])

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    def test_enforces_size_limit(self, mock_dbm):
        """Test that the cache enforces the size limit."""
        mock_db = mock.MagicMock()
        # Mock a dictionary with more items than the limit
        mock_items = [(f'KEY{i}'.encode(), f'VALUE{i}'.encode())
                      for i in range(12)]
        mock_db.items.return_value = mock_items
        mock_dbm.open.return_value = mock_db

        # Set max_entries to 10 to test eviction
        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file, max_entries=10)

        # Trigger size limit enforcement
        manager._enforce_size_limit()

        # Verify that items were deleted (oldest 2 items to get down to 10)
        self.assertEqual(2, mock_db.__delitem__.call_count)
        mock_db.__delitem__.assert_has_calls(
            [mock.call(b'KEY0'), mock.call(b'KEY1')])

    @mock.patch('beansprout.quoter.sources.cache_manager.dbm')
    @mock.patch('beansprout.quoter.sources.cache_manager.logging')
    def test_logs_hit_and_miss(self, mock_logging, mock_dbm):
        """Test that cache hits and misses are logged."""
        mock_db = mock.MagicMock()
        # Set up for a hit
        mock_db.__contains__.return_value = True
        mock_db.__getitem__.return_value = cache_manager.pickle.dumps(
            (datetime.datetime.now().timestamp(), {
                'price': 150.25
            }))
        mock_dbm.open.return_value = mock_db

        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)
        date = datetime.date(2025, 5, 10)

        # Test a cache hit
        result = manager.get('AAPL', 'USD', date)
        self.assertIsNotNone(result)
        mock_logging.debug.assert_any_call("Cache hit for key %s",
                                           'AAPL:USD:2025-05-10')

        # Set up for a miss
        mock_db.__contains__.return_value = False

        # Test a cache miss
        result = manager.get('MSFT', 'USD', date)
        self.assertIsNone(result)
        mock_logging.debug.assert_any_call("Cache miss for key %s",
                                           'MSFT:USD:2025-05-10')

    def test_get_stats(self):
        """Test that cache statistics are tracked correctly."""
        manager = cache_manager.DBMCacheManager(
            cache_file_path=self.cache_file)

        # Mock internal stats
        manager._stats = {'hits': 5, 'misses': 3}

        stats = manager.get_stats()
        self.assertEqual(5, stats['hits'])
        self.assertEqual(3, stats['misses'])
        self.assertAlmostEqual(0.625, stats['hit_ratio'], places=3)


class NullCacheManagerTest(unittest.TestCase):
    """Tests for NullCacheManager."""

    def test_get_always_returns_none(self):
        """Test that get always returns None."""
        manager = cache_manager.NullCacheManager()
        date = datetime.date(2025, 5, 10)

        result = manager.get('AAPL', 'USD', date)
        self.assertIsNone(result)

        # Get should still return None for any input
        result = manager.get('NONEXISTENT', 'EUR', date)
        self.assertIsNone(result)

    def test_put_is_noop(self):
        """Test that put is a no-op."""
        manager = cache_manager.NullCacheManager()
        date = datetime.date(2025, 5, 10)
        quote_data = {'price': 150.25, 'currency': 'USD'}

        # This should not raise any exceptions
        manager.put('AAPL', 'USD', date, quote_data)

        # And get should still return None
        result = manager.get('AAPL', 'USD', date)
        self.assertIsNone(result)

    def test_stats_tracking(self):
        """Test that statistics are tracked correctly."""
        manager = cache_manager.NullCacheManager()
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


if __name__ == '__main__':
    unittest.main()
