#!/usr/bin/env python3
"""Tests for the dispatching module."""

import unittest
import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from beancount.core import data
from beanprice.source import SourcePrice

from beansprout.quoter.sources.dispatching import SourceDispatcher
from beansprout.quoter.sources.cache_manager import NullCacheManager
from beansprout.quoter.expression_parser import SourceSpec


class TestSourceDispatcher(unittest.TestCase):
    """Tests for SourceDispatcher."""

    def setUp(self):
        """Set up the test environment."""
        self.cache_manager = NullCacheManager()
        self.source = SourceDispatcher(self.cache_manager)

    def test_fetch_latest_prices_batch_basic(self):
        """Test basic batch latest price fetching."""
        spec_commodity_pairs = [(SourceSpec('USD', 'mock_source', 'AAPL',
                                            False), 'AAPL')]

        # Mock source that returns a price
        mock_source = MagicMock()
        mock_source.get_latest_prices_batch.return_value = {
            'AAPL': SourcePrice(Decimal('150.00'), datetime.datetime.now(),
                                'USD')
        }

        with patch.object(self.source,
                          '_get_or_create_source',
                          return_value=mock_source):
            results = self.source.fetch_latest_prices_batch(
                spec_commodity_pairs)

        # Verify results
        self.assertEqual(len(results), 1)
        self.assertIn('AAPL', results)
        price = results['AAPL']
        self.assertEqual(price.currency, 'AAPL')
        self.assertEqual(price.amount.number, Decimal('150.00'))
        self.assertEqual(price.amount.currency, 'USD')

    def test_fetch_latest_prices_batch_inversion(self):
        """Test batch latest price fetching with inversion."""
        spec_commodity_pairs = [(SourceSpec('USD', 'mock_source', 'CADUSD=X',
                                            True), 'CAD')]

        # Mock source that returns a price
        mock_source = MagicMock()
        mock_source.get_latest_prices_batch.return_value = {
            'CADUSD=X':
            SourcePrice(Decimal('0.75'), datetime.datetime.now(), 'USD')
        }

        with patch.object(self.source,
                          '_get_or_create_source',
                          return_value=mock_source):
            results = self.source.fetch_latest_prices_batch(
                spec_commodity_pairs)

        # Verify results - price should be inverted
        self.assertEqual(len(results), 1)
        self.assertIn('CADUSD=X', results)
        price = results['CADUSD=X']
        self.assertEqual(price.currency, 'CAD')
        # 1/0.75 = 1.333...
        self.assertAlmostEqual(float(price.amount.number),
                               1.3333333333333333,
                               places=10)
        self.assertEqual(price.amount.currency, 'USD')

    def test_fetch_latest_prices_batch_empty_specs(self):
        """Test batch latest price fetching with empty specs."""
        results = self.source.fetch_latest_prices_batch([])
        self.assertEqual(len(results), 0)

    def test_fetch_latest_prices_batch_no_source(self):
        """Test batch latest price fetching when source not found."""
        spec_commodity_pairs = [(SourceSpec('USD', 'nonexistent_source',
                                            'AAPL', False), 'AAPL')]

        with patch.object(self.source,
                          '_get_or_create_source',
                          return_value=None):
            results = self.source.fetch_latest_prices_batch(
                spec_commodity_pairs)

        self.assertEqual(len(results), 0)

    def test_fetch_historical_prices_batch_basic(self):
        """Test basic batch historical price fetching."""
        spec_commodity_pairs = [(SourceSpec('USD', 'mock_source', 'AAPL',
                                            False), 'AAPL')]
        test_time = datetime.datetime(2023, 1, 15, 10, 0, 0)

        # Mock source that returns a price
        mock_source = MagicMock()
        mock_source.get_historical_prices_batch.return_value = {
            'AAPL': SourcePrice(Decimal('145.00'), test_time, 'USD')
        }

        with patch.object(self.source,
                          '_get_or_create_source',
                          return_value=mock_source):
            results = self.source.fetch_historical_prices_batch(
                spec_commodity_pairs, test_time)

        # Verify results
        self.assertEqual(len(results), 1)
        self.assertIn('AAPL', results)
        price = results['AAPL']
        self.assertEqual(price.currency, 'AAPL')
        self.assertEqual(price.amount.number, Decimal('145.00'))
        self.assertEqual(price.amount.currency, 'USD')

    def test_fetch_prices_series_batch_basic(self):
        """Test basic batch price series fetching."""
        spec_commodity_pairs = [(SourceSpec('USD', 'mock_source', 'AAPL',
                                            False), 'AAPL')]
        start_time = datetime.datetime(2023, 1, 1, 10, 0, 0)
        end_time = datetime.datetime(2023, 1, 31, 10, 0, 0)

        # Mock source that returns a price series
        mock_source = MagicMock()
        mock_source.get_prices_series_batch.return_value = {
            'AAPL': [
                SourcePrice(Decimal('140.00'),
                            datetime.datetime(2023, 1, 1, 10, 0, 0), 'USD'),
                SourcePrice(Decimal('145.00'),
                            datetime.datetime(2023, 1, 15, 10, 0, 0), 'USD'),
                SourcePrice(Decimal('150.00'),
                            datetime.datetime(2023, 1, 31, 10, 0, 0), 'USD'),
            ]
        }

        with patch.object(self.source,
                          '_get_or_create_source',
                          return_value=mock_source):
            results = self.source.fetch_prices_series_batch(
                spec_commodity_pairs, start_time, end_time)

        # Verify results
        self.assertEqual(len(results), 1)
        self.assertIn('AAPL', results)
        price_list = results['AAPL']
        self.assertEqual(len(price_list), 3)

        # Check prices are sorted by date
        dates = [price.date for price in price_list]
        self.assertEqual(dates, sorted(dates))

        # Check first and last prices
        self.assertEqual(price_list[0].amount.number, Decimal('140.00'))
        self.assertEqual(price_list[-1].amount.number, Decimal('150.00'))

    def test_fetch_prices_series_batch_inversion(self):
        """Test batch price series fetching with inversion."""
        spec_commodity_pairs = [(SourceSpec('USD', 'mock_source', 'CADUSD=X',
                                            True), 'CAD')]
        start_time = datetime.datetime(2023, 1, 1, 10, 0, 0)
        end_time = datetime.datetime(2023, 1, 31, 10, 0, 0)

        # Mock source that returns a price series
        mock_source = MagicMock()
        mock_source.get_prices_series_batch.return_value = {
            'CADUSD=X': [
                SourcePrice(Decimal('0.75'),
                            datetime.datetime(2023, 1, 1, 10, 0, 0), 'USD'),
                SourcePrice(Decimal('0.80'),
                            datetime.datetime(2023, 1, 15, 10, 0, 0), 'USD'),
            ]
        }

        with patch.object(self.source,
                          '_get_or_create_source',
                          return_value=mock_source):
            results = self.source.fetch_prices_series_batch(
                spec_commodity_pairs, start_time, end_time)

        # Verify results - prices should be inverted
        self.assertEqual(len(results), 1)
        self.assertIn('CADUSD=X', results)
        price_list = results['CADUSD=X']
        self.assertEqual(len(price_list), 2)

        # Check inverted prices: 1/0.75 = 1.333..., 1/0.80 = 1.25
        self.assertAlmostEqual(float(price_list[0].amount.number),
                               1.3333333333333333,
                               places=10)
        self.assertAlmostEqual(float(price_list[1].amount.number),
                               1.25,
                               places=10)

    def test_source_wrapping(self):
        """Test that sources are properly wrapped with batch capability."""
        # Mock a source without batch methods
        mock_source = MagicMock()
        # Remove batch method to simulate old source
        if hasattr(mock_source, 'get_latest_prices_batch'):
            del mock_source.get_latest_prices_batch

        with patch('beansprout.quoter.sources.dispatching.get_source',
                   return_value=mock_source):
            wrapped_source = self.source._get_or_create_source('test_source')

        # Should have batch method after wrapping
        self.assertTrue(hasattr(wrapped_source, 'get_latest_prices_batch'))
        self.assertTrue(hasattr(wrapped_source, 'get_historical_prices_batch'))
        self.assertTrue(hasattr(wrapped_source, 'get_prices_series_batch'))

    def test_source_caching(self):
        """Test that sources are cached properly."""
        mock_source = MagicMock()

        with patch('beansprout.quoter.sources.dispatching.get_source',
                   return_value=mock_source) as mock_get:
            # First call should get source
            source1 = self.source._get_or_create_source('test_source')
            # Second call should use cache
            source2 = self.source._get_or_create_source('test_source')

        # Should only call get_source once due to caching
        mock_get.assert_called_once_with(source_name='test_source')
        # Should return same instance
        self.assertIs(source1, source2)


if __name__ == "__main__":
    unittest.main()
